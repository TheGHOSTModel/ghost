# Live Simulation — Design Document

## Purpose

The Live Simulation is a multiplayer TicTacToe harness purpose-built to validate the G.H.O.S.T model. It is **not a game** — the TicTacToe mechanic exists solely to generate realistic, attributable telemetry that the GHOST evaluation engine can reason over.

Two browser windows join the same session, play moves, exchange chat messages, and trigger GHOST AI analysis. Every interaction emits structured telemetry events. The GHOST Score panel shows in real time how observable each domain is.

---

## Architecture

```
Browser (Player X)              Browser (Player O)
      │                                │
      │  WebSocket /ws/{sid}           │  WebSocket /ws/{sid}
      │                                │
      └──────────────┬─────────────────┘
                     │
              server.py (port 8080)
                     │
         ┌───────────┼───────────────┐
         │           │               │
   SessionManager  TelemetryBuffer  ghost_ai.py
   (in-memory)                      (Cerebras LLM)
         │
    ┌────┴──────────────────────────┐
    │  GHOST Rule Evaluation Engine │
    │  G-GAME-001, G-GAME-002       │
    │  H-HARM-001                   │
    │  O-SESSION-001                │
    │  S-CHAT-001                   │
    └───────────────────────────────┘
```

---

## Component Reference

### `server.py` — FastAPI Backend

**Responsibilities:**
- Hosts WebSocket connections for real-time game events
- Maintains in-memory `SessionManager` (sessions, board state, telemetry)
- Validates every move server-side (server authority invariant)
- Evaluates GHOST rules against accumulated telemetry
- Triggers GHOST AI for harm analysis on chat messages

**Key endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serves `index.html` |
| `WebSocket` | `/ws/{session_id}` | Real-time game connection |
| `POST` | `/api/sessions` | Create a new game session |
| `GET` | `/api/sessions` | List all sessions |
| `GET` | `/api/sessions/{id}/ghost` | GHOST rule evaluation results |
| `GET` | `/api/sessions/{id}/telemetry` | Raw telemetry event stream |
| `GET/POST` | `/api/sessions/{id}/toggles` | Read/write GHOST mode toggles |
| `GET/POST` | `/api/config/ghost-ai` | Read/inject Cerebras API key |
| `GET` | `/api/debug-ghost-ai` | Test AI with a synthetic payload |

### `ghost_ai.py` — Harm Detection Module

Wraps the Cerebras LLM (`llama3.1-8b`) to classify chat messages for harm signals.

**Activation conditions** (all must be true):
1. A player has `minor_flag = true` (minor present in session)
2. GHOST AI mode is enabled via toggle
3. The chat message is non-empty

**Output schema:**
```json
{
  "analysis_triggered": true,
  "abusive_language_detected": false,
  "risk_level": "medium",
  "detected_categories": ["grooming/trust-building", "boundary violations"],
  "evidence_snippets": ["don't tell your parents"],
  "system_action": "send_minor_nudge"
}
```

**Risk levels:** `low` | `medium` | `high` | `critical`

**System actions:** `none` | `send_minor_nudge` | `warn_adult` | `escalate`

### `index.html` — Live Simulation Frontend

Single-file SPA providing:
- Dual-pane game boards (Session A and Session B side by side)
- WebSocket connection management with reconnect logic
- GHOST Score panel — G·H·O·S·T letter metrics with evidence bars
- GHOST AI panel — real-time harm analysis results
- Telemetry panel — raw event stream with counts
- GHOST Mode toggle (enables AI monitoring)
- Debug toggles for GHOST validation scenarios

---

## Telemetry Events

Every player action emits one or more structured events to the `TelemetryBuffer`:

| Event | Trigger | Domain |
|-------|---------|--------|
| `game.session.created` | Player joins | O |
| `game.move.attempted` | Any move attempt | G |
| `game.move.accepted` | Valid move played | G |
| `game.move.rejected` | Invalid move (wrong turn, occupied, etc.) | G |
| `game.win.detected` | Winning line found | G |
| `chat.message.sent` | Chat message sent | S |
| `ghost_ai.analysis` | Cerebras analysis triggered | H |
| `rate_limit.hit` | Move or chat rate limit exceeded | O |
| `input.validation.error` | Schema or boundary violation | O |

Each event carries: `seq_num`, `event_name`, `player_id`, `domain`, `metadata`, `timestamp`.

---

## GHOST Rule Evaluation Engine

The engine evaluates accumulated telemetry against five rules on demand (`GET /api/sessions/{id}/ghost`):

### G-GAME-001 — Gameplay violations observable
- **Evidence 0:** No moves attempted
- **Evidence 1:** Moves attempted
- **Evidence 2:** Rejections observed
- **Evidence 3 (PASS):** Rejections with reason metadata

### G-GAME-002 — Replay / turn abuse observable
- **Evidence 0:** No moves
- **Evidence 1:** Moves attempted
- **Evidence 2 (WEAK):** Rejections observed
- Cannot reach PASS — no `game.move_replay_detected` event exists (intentional gap)

### H-HARM-001 — Harmful content detectable
- **Evidence 0 (BLIND):** No AI analysis triggered
- **Evidence 1:** AI triggered, no abusive content
- **Evidence 2 (WEAK):** Abusive content detected
- **Evidence 3 (PASS):** High-risk content with escalation action

### O-SESSION-001 — Cross-session leakage detectable
- Evaluates `input.validation.error` and cross-session error events
- Cannot reach PASS — no dedicated `session.leak_detected` event (intentional gap)

### S-CHAT-001 — Chat attributable to players
- Evaluates `chat.message.sent` and `rate_limit.hit` counts
- Cannot reach PASS — no `chat.spam_classification` event (intentional gap)

### GHOST Score Metrics Bar
Each letter (G·H·O·S·T) shows the count of PASS rules in that domain:
- 🟢 Green = all rules PASS
- 🟡 Amber = some rules PASS
- 🔴 Red = no rules PASS (BLIND)

---

## GHOST Mode Toggles

The simulation exposes toggles to deliberately create GHOST validation failures:

| Toggle | Effect | GHOST test |
|--------|--------|-----------|
| Disable turn validation | Allows players to move out of turn | G-GAME-001 |
| Allow move replay | Allows replaying the last move | G-GAME-002 |
| Allow cross-session | Enables cross-session state access | O-SESSION-001 |
| Disable chat rate limit | Removes chat throttling | S-CHAT-001 |
| Suppress events | Drops specific telemetry events | All |

---

## Local Setup

```bash
# From the src/ directory
python -m uvicorn server:app --host 127.0.0.1 --port 8080 --reload

# Open two browser tabs:
# Tab A: http://localhost:8080/  (join as Player X)
# Tab B: http://localhost:8080/  (join as Player O)

# Inject Cerebras key for GHOST AI:
curl -X POST http://localhost:8080/api/config/ghost-ai \
  -H "Content-Type: application/json" \
  -d '{"provider":"cerebras","model":"llama3.1-8b","api_key":"YOUR_KEY"}'
```

---

## Known Design Gaps (intentional)

These gaps are **by design** — they demonstrate what GHOST invariants look like when telemetry is absent:

- No `game.move_replay_detected` event → G-GAME-002 cannot reach PASS
- No `session.leak_detected` event → O-SESSION-001 cannot reach PASS
- No `chat.spam_classification` event → S-CHAT-001 cannot reach PASS
- T domain has no rules in the harness (TicTacToe has no economy)

This is the point: the evaluation engine surfaces gaps, not just passes.
