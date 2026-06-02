# GHOST Web Application — Architecture

## Overview

The GHOST web application is a five-tab single-page application that demonstrates the G.H.O.S.T framework in action. It is served by two independent FastAPI backends and a static frontend shell.

---

## System Schematic

```
Browser
└── app.html  (GHOST shell — 5 tabs)
     │
     ├── Tab 01: Framework      ──► iat.html#framework   (static)
     ├── Tab 02: Invariants     ──► iat.html#catalog      (static)
     ├── Tab 03: Live Sim       ──► iframe → localhost:8080/  ──► server.py
     ├── Tab 04: Threat Radar   ──► iframe → localhost:8081/  ──► GlobalThreats/backend/main.py
     └── Tab 05: About          (static)

Backend A — server.py (port 8080)
├── FastAPI + Uvicorn
├── WebSocket: /ws/{session_id}          — real-time game events
├── REST: /api/sessions/*                — session management
├── REST: /api/config/ghost-ai           — AI key injection
├── REST: /api/sessions/{id}/ghost       — GHOST rule evaluation
├── REST: /api/sessions/{id}/telemetry   — telemetry stream
├── Static: serves index.html, iat.html, assets
├── In-memory SessionManager            — game state + telemetry buffer
└── ghost_ai.py                         — Cerebras LLM harm detection

Backend B — GlobalThreats/backend/main.py (port 8081)
├── FastAPI + Uvicorn
├── REST: /api/threats                   — filtered threat events
├── REST: /api/status                    — last refresh + event count
├── REST: /api/refresh                   — trigger live feed fetch
├── APScheduler: every 4 hours           — auto-refresh feeds
├── File: data/threats.json              — persisted threat cache
└── Static: serves GlobalThreats/frontend/
```

---

## Component Map

### Frontend Shell (`app.html`)

Single HTML file containing:
- Full CSS design system (dark theme, GHOST brand colours)
- Landing/hero page with mouse-spotlight reveal mechanic
- Tab navigation shell (Framework, Invariants, Live Sim, Threat Radar, About)
- JavaScript tab router with iframe lifecycle management
- IAT data embedded inline (50 invariants, 5 domains) for the Invariants tab

**Key design decisions:**
- Tabs 01/02 use `<iframe src="iat.html">` for the framework content
- Tabs 03/04 use `<iframe>` pointing to the two backend servers
- The hero page uses a CSS `clip-path` spotlight effect following the cursor
- All state is URL-hash-free; tab switches are JS-only

### IAT Frontend (`iat.html`)

Static single-file app rendering the full 50-invariant catalog with:
- Domain filter buttons (G / H / O / S / T)
- Expandable invariant rows showing telemetry schema and detection signal
- Test case display per invariant
- Hash-based navigation (`#framework` vs `#catalog`)

---

## Data Flow

```
Player Action (browser click)
  │
  ▼
WebSocket message → server.py
  │
  ├── Validate move (server authority)
  ├── Emit telemetry events to TelemetryBuffer
  ├── Evaluate GHOST rules → evidence_level per rule
  └── If chat + minor_flag → ghost_ai.py (Cerebras LLM)
        └── Returns: risk_level, abusive_detected, system_action
  │
  ▼
Browser receives state update
  ├── Renders board + scores
  ├── Updates GHOST Score panel (G·H·O·S·T letter metrics)
  └── Updates GHOST AI panel (harm analysis results)
```

```
Scheduled/Manual Trigger
  │
  ▼
GlobalThreats/backend/main.py
  ├── Fetches 11 live threat feeds (RSS, CSV, plain-text)
  ├── Classifies each event against GHOST domains
  ├── Infers severity (critical / high / medium / low)
  ├── Geo-locates each event
  └── Writes threats.json to disk (S3 on AWS)
  │
  ▼
Threat Radar frontend (Globe.gl)
  ├── Loads threats via GET /api/threats
  ├── Renders 3D globe with coloured points per GHOST domain
  └── Updates HUD stats (today / month / per-domain counts)
```

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend framework | FastAPI + Uvicorn |
| Real-time comms | WebSockets (local) / REST polling (cloud) |
| LLM harm detection | Cerebras (`llama3.1-8b`) / Anthropic (optional) |
| Threat feeds | httpx + feedparser + standard CSV/text parsing |
| Feed scheduling | APScheduler (local) / CloudWatch Events (AWS) |
| Globe visualisation | Globe.gl (Three.js) |
| Frontend | Vanilla HTML/CSS/JS — no build step required |
| Cloud deployment | AWS Lambda + DynamoDB + S3 + API Gateway (SAM) |

---

## Security Notes

- All game state is server-authoritative — clients cannot forge outcomes
- GHOST AI only activates when a minor player flag is set (by design)
- Chat rate limiting prevents spam (configurable via toggle)
- CORS is open (`*`) in development; should be restricted to known origin in production
- Cerebras API key is injected at runtime via `POST /api/config/ghost-ai` — never stored in frontend

---

## Local Ports

| Service | Port | URL |
|---------|------|-----|
| Main app + game backend | 8080 | http://localhost:8080/app.html |
| Threat Radar backend | 8081 | http://localhost:8081/ |

---

## Cloud Architecture (AWS)

See [cloudlaunch deployment](../src/cloudlaunch/) for the full SAM template. Key differences from local:

- Single Lambda function handles all API routes (game + threats)
- DynamoDB replaces in-memory SessionManager
- S3 replaces local `threats.json`
- CloudWatch Events replaces APScheduler
- S3 static website serves frontend (no Lambda for static files)
- REST polling replaces WebSockets (API Gateway HTTP API)
