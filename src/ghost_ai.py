"""
GHOST AI — Conditional Harm Monitoring Module
Pluggable LLM backend. Configure via environment variables or the
/api/config/ghost-ai REST endpoint at runtime.

  GHOST_AI_PROVIDER  = "anthropic"  (default)
  GHOST_AI_API_KEY   = "<your key>"
  GHOST_AI_MODEL     = "claude-sonnet-4-6"
"""
from __future__ import annotations

import json
import os
from typing import Dict, List

# ── Runtime-patchable config ──────────────────────────────────────────────────
config: Dict[str, str] = {
    "provider": os.getenv("GHOST_AI_PROVIDER", "cerebras"),
    "api_key":  os.getenv("GHOST_AI_API_KEY",  os.getenv("CEREBRAS_API_KEY", "")),
    "model":    os.getenv("GHOST_AI_MODEL",     "gpt-oss-120b"),
}

# ── System prompt (verbatim from GHOST spec) ──────────────────────────────────
SYSTEM_PROMPT = """You are GHOST AI, a safety monitoring subsystem for a multiplayer game. Activation conditions are already confirmed met — a minor is present. Your job is to analyse the chat and return a JSON assessment.

Classify harmful intent across: harassment/degradation, coercion/manipulation, grooming/trust-building, boundary violations.

Signals to watch (any single clear instance is sufficient to flag):
- Requests for secrecy ("don't tell anyone", "just between us", "keep this secret")
- Flattery targeting minors ("you're so mature", "not like other kids")
- Isolation attempts ("stop talking to them", "only talk to me")
- Insults / humiliation ("stupid", "worthless", "nobody likes you")
- Threats or pressure ("you have to", "or else")
- Inappropriate escalation toward private interaction

Output ONLY this JSON, no prose:
{"analysis_triggered": true, "abusive_language_detected": true|false, "risk_level": "low"|"medium"|"high", "detected_categories": [], "evidence_snippets": [], "system_action": "none"|"send_minor_nudge"}

Rules:
- analysis_triggered is ALWAYS true (conditions already confirmed)
- If nothing harmful: abusive_language_detected=false, risk_level="low", system_action="none"
- If medium or high risk: system_action="send_minor_nudge"
- evidence_snippets: exact quoted phrases from chat only"""


def _activation_check(player_flags: Dict[str, dict]) -> bool:
    """Returns True only if activation conditions are met."""
    has_minor = any(f.get("minor_flag") for f in player_flags.values())
    # AgeExposureRisk = minor present AND at least one other player in session
    age_exposure_risk = has_minor and len(player_flags) >= 2
    return has_minor and age_exposure_risk


def _format_chat(messages: List[dict]) -> str:
    return "\n".join(
        f"[{m['from']} ({'minor' if m.get('minor_flag') else 'player'}, {m['symbol'] or 'spectator'})]: {m['message']}"
        for m in messages[-20:]
    )


async def analyze(messages: List[dict], player_flags: Dict[str, dict]) -> dict:
    """
    messages     : recent chat entries, each with {from, symbol, message, ...}
    player_flags : {player_id: {minor_flag: bool, name: str, symbol: str}}
    Returns the parsed JSON result from the LLM.
    """
    if not _activation_check(player_flags):
        return {"analysis_triggered": False}

    if not config["api_key"]:
        return {"analysis_triggered": False, "error": "no_api_key_configured"}

    flags_summary = {
        pid: {"name": f["name"], "symbol": f["symbol"], "minor_flag": f["minor_flag"]}
        for pid, f in player_flags.items()
    }

    user_message = (
        f"Analyse this game chat for harmful intent toward a minor participant.\n\n"
        f"Player flags:\n{json.dumps(flags_summary, indent=2)}\n\n"
        f"Recent chat (last {min(len(messages), 20)} messages):\n{_format_chat(messages)}"
    )

    provider = config["provider"]
    if provider == "cerebras":
        result = await _call_cerebras(user_message)
    elif provider == "anthropic":
        result = await _call_anthropic(user_message)
    else:
        return {"analysis_triggered": False, "error": f"unknown_provider:{provider}"}

    # Activation conditions already confirmed — force analysis_triggered=True
    result["analysis_triggered"] = True
    return result


async def _call_cerebras(user_message: str) -> dict:
    try:
        import asyncio
        import httpx
        from cerebras.cloud.sdk import Cerebras
        http_client = httpx.Client(verify=False)
        client = Cerebras(api_key=config["api_key"], http_client=http_client)
        completion = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.chat.completions.create(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_message},
                ],
                model=config["model"],
                max_completion_tokens=512,
                temperature=0.2,
                top_p=1,
                stream=False,
            )
        )
        text = completion.choices[0].message.content.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as exc:
        return {"analysis_triggered": False, "error": str(exc)[:200]}


async def _call_anthropic(user_message: str) -> dict:
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=config["api_key"])
        response = await client.messages.create(
            model=config["model"],
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        text = response.content[0].text.strip()
        # Strip markdown code fences if the model wraps the JSON
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as exc:
        return {"analysis_triggered": False, "error": str(exc)[:200]}
