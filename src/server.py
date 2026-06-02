"""
GHOSTv2 — TicTacToe Simulation Harness
Purpose : Validate GHOST invariants and telemetry coverage.

Run  : uvicorn server:app --host 0.0.0.0 --port 8080 --reload
Open : http://localhost:8080
"""
from __future__ import annotations

import asyncio
import json
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import os

# Load .env if present so CEREBRAS_API_KEY survives reloads
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import ghost_ai

_HERE = os.path.dirname(os.path.abspath(__file__))
from pydantic import BaseModel

app = FastAPI(title="GHOSTv2 TicTacToe Harness")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# ── Constants ──────────────────────────────────────────────────────────────────
WINNING_LINES: List[Tuple[int, int, int]] = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
]
CHAT_RATE_SECS = 1.0
MOVE_RATE_SECS = 0.25


# ── Toggles ───────────────────────────────────────────────────────────────────
@dataclass
class Toggles:
    disable_turn_validation: bool     = False
    allow_move_replay:       bool     = False
    allow_cross_session:     bool     = False
    disable_chat_rate_limit: bool     = False
    suppressed_events:       Set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "disable_turn_validation": self.disable_turn_validation,
            "allow_move_replay":       self.allow_move_replay,
            "allow_cross_session":     self.allow_cross_session,
            "disable_chat_rate_limit": self.disable_chat_rate_limit,
            "suppressed_events":       list(self.suppressed_events),
        }


# ── Telemetry ─────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TelemetryBuffer:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.events: List[dict] = []
        self._seq = 0

    def emit(
        self,
        event_name: str,
        player_id: str,
        category: str,
        metadata: dict,
        toggles: Toggles,
    ) -> Optional[dict]:
        if event_name in toggles.suppressed_events:
            return None
        self._seq += 1
        ev = {
            "seq_num":    self._seq,
            "event_name": event_name,
            "timestamp":  _now_iso(),
            "session_id": self.session_id,
            "player_id":  player_id,
            "category":   category,
            "metadata":   metadata,
        }
        self.events.append(ev)
        if len(self.events) > 500:
            self.events = self.events[-500:]
        return ev

    def since(self, seq: int) -> List[dict]:
        return [e for e in self.events if e["seq_num"] > seq]

    def stats(self) -> dict:
        counts: Dict[str, int] = {}
        for e in self.events:
            counts[e["event_name"]] = counts.get(e["event_name"], 0) + 1
        return {"total": len(self.events), "by_event": counts}


# ── Session ───────────────────────────────────────────────────────────────────
def _winner(board: List) -> Tuple[Optional[str], Optional[Tuple]]:
    for a, b, c in WINNING_LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a], (a, b, c)
    if all(cell is not None for cell in board):
        return "draw", None
    return None, None


class Session:
    def __init__(self, session_id: str, label: str = ""):
        self.session_id  = session_id
        self.label       = label or session_id[:8]
        self.created_at  = _now_iso()

        self.board:        List[Optional[str]] = [None] * 9
        self.turn:         str                 = "X"
        self.winner:       Optional[str]       = None
        self.winning_line: Optional[tuple]     = None
        self.over:         bool                = False
        self.last_move:    Optional[int]       = None
        self.move_count:   int                 = 0

        # player_id -> {name, symbol, last_move_t, last_chat_t}
        self.players:     Dict[str, dict]      = {}
        # player_id -> WebSocket
        self.connections: Dict[str, WebSocket] = {}

        self.chat:      List[dict]    = []
        self.telemetry: TelemetryBuffer = TelemetryBuffer(session_id)
        self.toggles:   Toggles       = Toggles()

    # ── helpers ────────────────────────────────────────────────────────────────
    def assign(self, player_id: str, name: str, minor_flag: bool = False) -> Optional[str]:
        taken = {p["symbol"] for p in self.players.values()}
        for sym in ("X", "O"):
            if sym not in taken:
                self.players[player_id] = {
                    "name":        name,
                    "symbol":      sym,
                    "last_move_t": 0.0,
                    "last_chat_t": 0.0,
                    "minor_flag":  minor_flag,
                }
                return sym
        return None  # spectator

    def player_flags(self) -> Dict[str, dict]:
        return {
            pid: {"name": p["name"], "symbol": p["symbol"], "minor_flag": p.get("minor_flag", False)}
            for pid, p in self.players.items()
        }

    def symbol(self, pid: str) -> Optional[str]:
        return self.players.get(pid, {}).get("symbol")

    def name(self, pid: str) -> str:
        return self.players.get(pid, {}).get("name", "?")

    def is_ready(self) -> bool:
        return sum(1 for p in self.players.values() if p["symbol"] in ("X","O")) == 2

    def state_dict(self) -> dict:
        return {
            "session_id":   self.session_id,
            "label":        self.label,
            "board":        self.board,
            "turn":         self.turn,
            "winner":       self.winner,
            "winning_line": list(self.winning_line) if self.winning_line else None,
            "over":         self.over,
            "move_count":   self.move_count,
            "ready":        self.is_ready(),
            "players": {
                pid: {"name": p["name"], "symbol": p["symbol"]}
                for pid, p in self.players.items()
            },
        }

    def reset(self):
        self.board        = [None] * 9
        self.turn         = "X"
        self.winner       = None
        self.winning_line = None
        self.over         = False
        self.last_move    = None
        self.move_count   = 0


# ── Session manager ───────────────────────────────────────────────────────────
class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, Session] = {}

    def create(self, label: str = "") -> Session:
        sid = str(uuid.uuid4())[:8]
        s   = Session(sid, label)
        self.sessions[sid] = s
        return s

    def get(self, sid: str) -> Optional[Session]:
        return self.sessions.get(sid)

    def summary(self) -> List[dict]:
        return [
            {
                "session_id":  s.session_id,
                "label":       s.label,
                "created_at":  s.created_at,
                "player_count": len([p for p in s.players.values()
                                     if p["symbol"] in ("X","O")]),
                "over":        s.over,
                "winner":      s.winner,
            }
            for s in self.sessions.values()
        ]


mgr = SessionManager()


# ── GHOST rule evaluation ─────────────────────────────────────────────────────
def evaluate_ghost(session: Session) -> List[dict]:
    ev   = session.telemetry.events
    tog  = session.toggles

    def cnt(name: str) -> int:
        return sum(1 for e in ev if e["event_name"] == name)

    rules = []

    # ── G-GAME-001: Gameplay violations observable ────────────────────────────
    attempted = cnt("game.move.attempted")
    rejected  = cnt("game.move.rejected")
    accepted  = cnt("game.move.accepted")

    rej_events = [e for e in ev if e["event_name"] == "game.move.rejected"]
    has_reason = all("reason" in e.get("metadata", {}) for e in rej_events)

    g1_ev = 0
    if attempted:           g1_ev = 1
    if rejected:            g1_ev = 2
    if rejected and has_reason: g1_ev = 3

    g1_missing = [
        "game.turn_violation — MISSING BY DESIGN (fires as generic rejection)",
        "enforcement.outcome — MISSING BY DESIGN",
    ]
    if tog.disable_turn_validation:
        g1_missing.append("WARNING: turn validation DISABLED — violations not enforced")

    rules.append({
        "rule_id":        "G-GAME-001",
        "name":           "Gameplay violations observable",
        "evidence_level": g1_ev,
        "status":         "PASS" if g1_ev >= 3 else "WEAK" if g1_ev >= 2 else "BLIND",
        "supporting":     [f"game.move.attempted x{attempted}",
                           f"game.move.rejected x{rejected}",
                           f"game.move.accepted x{accepted}"],
        "missing":        g1_missing,
        "explanation":    f"{rejected} rejections observed; no specific violation event type",
    })

    # ── G-GAME-002: Replay / turn abuse observable ────────────────────────────
    g2_ev = 0
    if attempted: g2_ev = 1
    if rejected:  g2_ev = 2
    # Cannot reach 3 — no replay detection event exists (intentional gap)

    rules.append({
        "rule_id":        "G-GAME-002",
        "name":           "Replay / turn abuse observable",
        "evidence_level": g2_ev,
        "status":         "WEAK" if g2_ev >= 2 else "BLIND",
        "supporting":     [f"game.move.attempted x{attempted}",
                           f"game.move.rejected x{rejected}"],
        "missing":        [
            "game.move_replay_detected — MISSING BY DESIGN",
            "game.turn_violation — MISSING BY DESIGN",
            "Replay can only be inferred from rejection patterns",
        ],
        "explanation":    "Evidence capped at 2 — detection events intentionally absent",
    })

    # ── S-CHAT-001: Chat attributable to players ──────────────────────────────
    sent      = cnt("chat.message.sent")
    received  = cnt("chat.message.received")
    rate_hits = cnt("rate_limit.hit")

    chat_ev   = [e for e in ev if e["event_name"] == "chat.message.sent"]
    with_pid  = all(bool(e.get("player_id")) for e in chat_ev) if chat_ev else False
    with_sid  = all(bool(e.get("session_id")) for e in chat_ev) if chat_ev else False

    sc_ev = 0
    if sent:                   sc_ev = 1
    if sent and with_pid:      sc_ev = 2
    if sent and with_pid and with_sid: sc_ev = 3

    rules.append({
        "rule_id":        "S-CHAT-001",
        "name":           "Chat attributable to players",
        "evidence_level": sc_ev,
        "status":         "PASS" if sc_ev >= 3 else "WEAK" if sc_ev >= 1 else "BLIND",
        "supporting":     [f"chat.message.sent x{sent}",
                           f"chat.message.received x{received}",
                           f"rate_limit.hit x{rate_hits}"],
        "missing":        [
            "chat.spam_classification — MISSING BY DESIGN",
            "chat.content_categorized — MISSING BY DESIGN",
            "No abuse pattern detection",
        ],
        "explanation":    f"{sent} messages with player+session attribution; no content analysis",
    })

    # ── O-SESSION-001: Cross-session leakage detectable ──────────────────────
    val_errs   = [e for e in ev if e["event_name"] == "input.validation.error"]
    cross_errs = [e for e in val_errs
                  if "cross_session" in str(e.get("metadata", {}))]

    os_ev = 0
    if val_errs:   os_ev = 1
    if cross_errs: os_ev = 2
    # Cannot reach 3 — no session.leak_detected event

    rules.append({
        "rule_id":        "O-SESSION-001",
        "name":           "Cross-session leakage detectable",
        "evidence_level": os_ev,
        "status":         "WEAK" if os_ev >= 2 else "BLIND",
        "supporting":     [f"input.validation.error x{len(val_errs)}",
                           f"cross_session errors x{len(cross_errs)}"],
        "missing":        [
            "session.leak_detected — MISSING BY DESIGN",
            "No dedicated signal for cross-session actions",
            "Leakage only visible as generic validation errors",
        ],
        "explanation":    "Session isolation enforced; no specific leak telemetry",
    })

    # ── H-HARM-001: Harmful content detectable ───────────────────────────────
    ai_events  = [e for e in ev if e["event_name"] == "ghost_ai.analysis"]
    triggered  = len(ai_events)
    harmful    = [e for e in ai_events if e.get("metadata", {}).get("abusive")]
    high_risk  = [e for e in harmful
                  if e.get("metadata", {}).get("risk_level") == "high"]

    h_ev = 0
    if triggered:          h_ev = 1
    if harmful:            h_ev = 2
    if harmful and high_risk: h_ev = 3

    rules.append({
        "rule_id":        "H-HARM-001",
        "name":           "Harmful content detectable",
        "evidence_level": h_ev,
        "status":         "PASS" if h_ev >= 3 else "WEAK" if h_ev >= 1 else "BLIND",
        "supporting":     [f"ghost_ai.analysis x{triggered}",
                           f"abusive detected x{len(harmful)}",
                           f"high risk x{len(high_risk)}"],
        "missing":        [
            "harm.escalation_pattern — MISSING BY DESIGN",
            "harm.actor_identified — MISSING BY DESIGN",
        ] if not harmful else [],
        "explanation":    (
            f"{len(harmful)} harmful analysis result(s) out of {triggered} checks; "
            f"{len(high_risk)} high-risk"
        ) if triggered else "No AI analysis triggered yet — minor player required",
    })

    return rules


# ── WebSocket broadcast ───────────────────────────────────────────────────────
async def _broadcast(session: Session, msg: dict):
    data = json.dumps(msg)
    for ws in list(session.connections.values()):
        try:
            await ws.send_text(data)
        except Exception:
            pass


async def _send(ws: WebSocket, msg: dict):
    try:
        await ws.send_text(json.dumps(msg))
    except Exception:
        pass


# ── WebSocket endpoint ────────────────────────────────────────────────────────
@app.websocket("/ws/{session_id}")
async def ws_handler(ws: WebSocket, session_id: str):
    await ws.accept()

    session = mgr.get(session_id)
    if not session:
        await _send(ws, {"type": "error", "message": "Session not found"})
        await ws.close()
        return

    pid    = str(uuid.uuid4())[:8]
    symbol: Optional[str] = None
    name   = "Anon"

    session.connections[pid] = ws

    try:
        await _send(ws, {"type": "init",          "player_id": pid})
        await _send(ws, {"type": "state",          **session.state_dict()})
        await _send(ws, {"type": "chat_history",   "messages": session.chat[-60:]})
        await _send(ws, {"type": "toggles",        **session.toggles.to_dict()})

        async for raw in ws.iter_text():
            try:
                msg   = json.loads(raw)
                mtype = msg.get("type", "")

                # ── join ──────────────────────────────────────────────────────
                if mtype == "join":
                    raw_name   = (msg.get("name") or "")[:20].strip()
                    minor_flag = bool(msg.get("minor_flag", False))
                    symbol     = session.assign(pid, raw_name or "?", minor_flag)
                    name       = raw_name or (f"Player {symbol}" if symbol else "Spectator")
                    if pid in session.players:
                        session.players[pid]["name"] = name

                    session.telemetry.emit(
                        "game.session.created" if not symbol else "game.session.created",
                        pid, "operations",
                        {"name": name, "symbol": symbol or "spectator"},
                        session.toggles,
                    )

                    await _send(ws, {"type": "you", "player_id": pid,
                                     "symbol": symbol, "name": name})
                    await _broadcast(session, {"type": "state", **session.state_dict()})

                # ── move ──────────────────────────────────────────────────────
                elif mtype == "move":
                    cell = msg.get("cell")

                    # Emit attempt
                    session.telemetry.emit(
                        "game.move.attempted", pid, "gameplay",
                        {"cell": cell, "symbol": symbol or "?", "name": name},
                        session.toggles,
                    )

                    # Rate limit
                    now = time.time()
                    player_rec = session.players.get(pid)
                    if player_rec:
                        since_last = now - player_rec["last_move_t"]
                        if since_last < MOVE_RATE_SECS:
                            session.telemetry.emit(
                                "rate_limit.hit", pid, "operations",
                                {"type": "move", "interval_ms": int(since_last * 1000)},
                                session.toggles,
                            )
                            await _send(ws, {"type": "error", "message": "Move rate limit hit"})
                            continue

                    # Must be a registered player
                    if symbol is None:
                        # Cross-session attempt
                        target = msg.get("target_session", session_id)
                        if target != session_id and not session.toggles.allow_cross_session:
                            session.telemetry.emit(
                                "input.validation.error", pid, "operations",
                                {"reason": "cross_session", "target": target},
                                session.toggles,
                            )
                            await _send(ws, {"type": "error",
                                            "message": "Cross-session actions not allowed"})
                            continue
                        session.telemetry.emit(
                            "input.validation.error", pid, "operations",
                            {"reason": "not_a_player"},
                            session.toggles,
                        )
                        await _send(ws, {"type": "error", "message": "Join the game first"})
                        continue

                    if session.over:
                        session.telemetry.emit(
                            "game.move.rejected", pid, "gameplay",
                            {"cell": cell, "reason": "game_over"},
                            session.toggles,
                        )
                        await _send(ws, {"type": "error", "message": "Game is over"})
                        continue

                    if not session.is_ready():
                        session.telemetry.emit(
                            "game.move.rejected", pid, "gameplay",
                            {"cell": cell, "reason": "waiting_for_opponent"},
                            session.toggles,
                        )
                        await _send(ws, {"type": "error", "message": "Waiting for opponent"})
                        continue

                    # Turn check (honoured unless toggle disabled)
                    if not session.toggles.disable_turn_validation and symbol != session.turn:
                        # NOTE: intentional gap — no game.turn_violation event
                        session.telemetry.emit(
                            "game.move.rejected", pid, "gameplay",
                            {"cell": cell, "reason": "wrong_turn",
                             "expected": session.turn, "got": symbol},
                            session.toggles,
                        )
                        await _send(ws, {"type": "error",
                                        "message": f"Not your turn (waiting for {session.turn})"})
                        continue

                    if not isinstance(cell, int) or not (0 <= cell <= 8):
                        session.telemetry.emit(
                            "game.move.rejected", pid, "gameplay",
                            {"cell": cell, "reason": "out_of_bounds"},
                            session.toggles,
                        )
                        await _send(ws, {"type": "error", "message": "Cell out of range"})
                        continue

                    if session.board[cell] is not None:
                        session.telemetry.emit(
                            "game.move.rejected", pid, "gameplay",
                            {"cell": cell, "reason": "cell_occupied"},
                            session.toggles,
                        )
                        await _send(ws, {"type": "error", "message": "Cell already taken"})
                        continue

                    # Replay check (honoured unless toggle disabled)
                    if (not session.toggles.allow_move_replay
                            and cell == session.last_move):
                        # NOTE: intentional gap — no game.move_replay_detected event
                        session.telemetry.emit(
                            "game.move.rejected", pid, "gameplay",
                            {"cell": cell, "reason": "replay_attempt"},
                            session.toggles,
                        )
                        await _send(ws, {"type": "error", "message": "Cannot replay last move"})
                        continue

                    # Apply move
                    session.board[cell] = symbol
                    session.last_move   = cell
                    session.move_count += 1
                    session.players[pid]["last_move_t"] = time.time()
                    session.turn = "O" if symbol == "X" else "X"

                    session.telemetry.emit(
                        "game.move.accepted", pid, "gameplay",
                        {"cell": cell, "symbol": symbol, "move_num": session.move_count},
                        session.toggles,
                    )

                    w, line = _winner(session.board)
                    if w:
                        session.winner       = w
                        session.winning_line = line
                        session.over         = True
                        session.telemetry.emit(
                            "game.win.detected", pid, "gameplay",
                            {"winner": w,
                             "winning_line": list(line) if line else None,
                             "move_count": session.move_count},
                            session.toggles,
                        )

                    await _broadcast(session, {"type": "state", **session.state_dict()})

                # ── chat ──────────────────────────────────────────────────────
                elif mtype == "chat":
                    text = (msg.get("message") or "").strip()

                    if not text:
                        session.telemetry.emit(
                            "input.validation.error", pid, "operations",
                            {"reason": "empty_chat_message"},
                            session.toggles,
                        )
                        continue

                    if len(text) > 500:
                        text = text[:500]
                        session.telemetry.emit(
                            "input.validation.error", pid, "operations",
                            {"reason": "message_too_long"},
                            session.toggles,
                        )

                    # Rate limit
                    now      = time.time()
                    prec     = session.players.get(pid)
                    if prec and not session.toggles.disable_chat_rate_limit:
                        since_last = now - prec["last_chat_t"]
                        if since_last < CHAT_RATE_SECS:
                            session.telemetry.emit(
                                "rate_limit.hit", pid, "operations",
                                {"type": "chat",
                                 "interval_ms": int(since_last * 1000)},
                                session.toggles,
                            )
                            await _send(ws, {"type": "error",
                                            "message": "Chat rate limit — slow down"})
                            continue

                    if prec:
                        prec["last_chat_t"] = time.time()

                    entry = {
                        "from":       name,
                        "symbol":     symbol,
                        "player_id":  pid,
                        "message":    text,
                        "timestamp":  _now_iso(),
                    }
                    session.chat.append(entry)
                    if len(session.chat) > 200:
                        session.chat = session.chat[-200:]

                    session.telemetry.emit(
                        "chat.message.sent", pid, "chat",
                        {"length": len(text), "name": name},
                        session.toggles,
                    )
                    await _broadcast(session, {"type": "chat", **entry})
                    session.telemetry.emit(
                        "chat.message.received", pid, "chat",
                        {"delivered_to": len(session.connections) - 1},
                        session.toggles,
                    )
                    await _run_ghost_ai(session)

                # ── reset ─────────────────────────────────────────────────────
                elif mtype == "reset":
                    if symbol is None:
                        continue
                    session.reset()
                    await _broadcast(session, {"type": "state", **session.state_dict()})

            except Exception:
                session.telemetry.emit(
                    "server.exception", pid, "operations",
                    {"traceback": traceback.format_exc()[:400]},
                    session.toggles,
                )

    except WebSocketDisconnect:
        pass
    finally:
        session.connections.pop(pid, None)
        session.players.pop(pid, None)   # free the slot so the session is re-joinable
        await _broadcast(session, {"type": "state", **session.state_dict()})


# ── GHOST AI ─────────────────────────────────────────────────────────────────
async def _run_ghost_ai(session: Session):
    import traceback as _tb
    _log = os.path.join(_HERE, "ghost_ai_debug.log")
    try:
        result = await ghost_ai.analyze(session.chat, session.player_flags())
        with open(_log, "a") as _f:
            _f.write(f"[OK] {result}\n")
        if not result.get("analysis_triggered"):
            return
        session.telemetry.emit(
            "ghost_ai.analysis", "server", "operations",
            {"risk_level": result.get("risk_level"), "abusive": result.get("abusive_language_detected")},
            session.toggles,
        )
        await _broadcast(session, {"type": "ghost_ai", **result})
    except Exception as e:
        with open(_log, "a") as _f:
            _f.write(f"[ERR] {e}\n{_tb.format_exc()}\n")


# ── REST endpoints ────────────────────────────────────────────────────────────

class CreateSessionReq(BaseModel):
    label: str = ""


class TogglesUpdate(BaseModel):
    disable_turn_validation: Optional[bool] = None
    allow_move_replay:       Optional[bool] = None
    allow_cross_session:     Optional[bool] = None
    disable_chat_rate_limit: Optional[bool] = None
    suppressed_events:       Optional[List[str]] = None


@app.post("/api/sessions")
def create_session(req: CreateSessionReq = CreateSessionReq()):
    s = mgr.create(req.label)
    s.telemetry.emit("game.session.created", "server", "operations",
                     {"label": s.label}, s.toggles)
    return s.state_dict()


@app.get("/api/sessions")
def list_sessions():
    return {"sessions": mgr.summary()}


@app.get("/api/sessions/{sid}/state")
def get_state(sid: str):
    s = mgr.get(sid)
    if not s:
        return {"error": "not found"}
    return s.state_dict()


@app.get("/api/sessions/{sid}/telemetry")
def get_telemetry(sid: str, since: int = 0):
    s = mgr.get(sid)
    if not s:
        return {"error": "not found"}
    return {"events": s.telemetry.since(since), "stats": s.telemetry.stats()}


@app.get("/api/sessions/{sid}/ghost")
def get_ghost(sid: str):
    s = mgr.get(sid)
    if not s:
        return {"error": "not found"}
    return {"rules": evaluate_ghost(s)}


@app.get("/api/sessions/{sid}/toggles")
def get_toggles(sid: str):
    s = mgr.get(sid)
    if not s:
        return {"error": "not found"}
    return s.toggles.to_dict()


@app.post("/api/sessions/{sid}/toggles")
async def update_toggles(sid: str, req: TogglesUpdate):
    s = mgr.get(sid)
    if not s:
        return {"error": "not found"}
    t = s.toggles
    if req.disable_turn_validation is not None: t.disable_turn_validation = req.disable_turn_validation
    if req.allow_move_replay       is not None: t.allow_move_replay       = req.allow_move_replay
    if req.allow_cross_session     is not None: t.allow_cross_session     = req.allow_cross_session
    if req.disable_chat_rate_limit is not None: t.disable_chat_rate_limit = req.disable_chat_rate_limit
    if req.suppressed_events       is not None: t.suppressed_events       = set(req.suppressed_events)
    asyncio.create_task(_broadcast_toggles(s))
    return t.to_dict()


async def _broadcast_toggles(session: Session):
    await _broadcast(session, {"type": "toggles", **session.toggles.to_dict()})


class GhostAiConfig(BaseModel):
    api_key:  Optional[str] = None
    model:    Optional[str] = None
    provider: Optional[str] = None


@app.get("/api/config/ghost-ai")
def get_ghost_ai_config():
    return {"provider": ghost_ai.config["provider"], "model": ghost_ai.config["model"], "api_key_set": bool(ghost_ai.config["api_key"])}


@app.post("/api/config/ghost-ai")
def configure_ghost_ai(req: GhostAiConfig):
    if req.api_key  is not None: ghost_ai.config["api_key"]  = req.api_key
    if req.model    is not None: ghost_ai.config["model"]    = req.model
    if req.provider is not None: ghost_ai.config["provider"] = req.provider
    return {"provider": ghost_ai.config["provider"], "model": ghost_ai.config["model"], "api_key_set": bool(ghost_ai.config["api_key"])}


@app.get("/api/debug-ghost-ai")
async def debug_ghost_ai():
    import traceback as _tb
    try:
        messages = [{"from":"Bob","symbol":"O","minor_flag":False,"message":"don't tell your parents, keep this secret between us"}]
        flags = {"pid1":{"name":"Alice","symbol":"X","minor_flag":True},"pid2":{"name":"Bob","symbol":"O","minor_flag":False}}
        result = await ghost_ai.analyze(messages, flags)
        return {"config": {"provider": ghost_ai.config["provider"], "model": ghost_ai.config["model"], "api_key_set": bool(ghost_ai.config["api_key"])}, "result": result}
    except Exception as e:
        return {"error": str(e), "traceback": _tb.format_exc()}


@app.get("/")
def index():
    return FileResponse(
        os.path.join(_HERE, "index.html"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"},
    )


@app.get("/app.html")
def app_page():
    return FileResponse(
        os.path.join(_HERE, "app.html"),
        headers={"Cache-Control": "no-store"},
    )


@app.get("/{filename:path}")
def static_file(filename: str):
    path = os.path.join(_HERE, filename)
    if os.path.isfile(path):
        return FileResponse(path)
    from fastapi import HTTPException
    raise HTTPException(status_code=404)
