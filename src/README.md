# Source Code

## Overview

The GHOST web application source code. Two FastAPI backends and a set of HTML/JS frontends that together demonstrate the G.H.O.S.T framework in action.

## Files

| File | Description |
|------|-------------|
| `server.py` | Main FastAPI backend — game engine, WebSocket server, telemetry, GHOST rule evaluation |
| `ghost_ai.py` | LLM harm detection module — Cerebras (default) or Anthropic |
| `app.html` | GHOST web app shell — 5-tab SPA (Framework, Invariants, Live Sim, Threat Radar, About) |
| `index.html` | Live Simulation frontend — dual-pane TicTacToe with GHOST Score and AI panels |
| `iat.html` | IAT viewer — Framework walkthrough and full 50-invariant catalog |
| `GlobalThreats/` | Threat Radar — backend feed fetcher + Globe.gl frontend |

## Quick start

```bash
# Install dependencies
pip install fastapi uvicorn httpx feedparser apscheduler truststore

# Start main backend (port 8080)
python -m uvicorn server:app --host 127.0.0.1 --port 8080 --reload

# Start Threat Radar backend (port 8081) — separate terminal
cd GlobalThreats
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8081

# Open app
# http://localhost:8080/app.html
```

## Injecting the GHOST AI key

The Cerebras API key is not stored in any config file. Inject it at runtime:

```bash
curl -X POST http://localhost:8080/api/config/ghost-ai \
  -H "Content-Type: application/json" \
  -d '{"provider":"cerebras","model":"llama3.1-8b","api_key":"YOUR_KEY"}'
```

## Detailed documentation

- [Architecture overview](../docs/architecture.md)
- [Live Simulation design](../docs/live-sim.md)
- [Threat Radar design](../docs/threat-radar.md)
