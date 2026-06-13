# GHOST Web Application — Architecture

## Overview

The GHOST web application is a five-tab single-page application that demonstrates the G.H.O.S.T framework in action. It is served by two independent FastAPI backends locally, and a single unified Lambda function in production.

---

## System Schematic

```
Browser
└── index.html  (GHOST shell — 5 tabs)
     │
     ├── Tab 01: Framework      ──► iat.html#framework   (static srcdoc)
     ├── Tab 02: Invariants     ──► iat.html#catalog      (static srcdoc)
     ├── Tab 03: Live Sim       ──► srcdoc iframe → /api/sessions/*
     ├── Tab 04: Threat Radar   ──► iframe → /radar/index.html → /api/threats
     └── Tab 05: About          (static)

Backend A — server.py (port 8080)          [local only]
├── FastAPI + Uvicorn
├── WebSocket: /ws/{session_id}            — real-time game events
├── REST: /api/sessions/*                  — session management
├── REST: /api/config/ghost-ai             — AI key injection
├── REST: /api/sessions/{id}/ghost         — GHOST rule evaluation
├── REST: /api/sessions/{id}/telemetry     — telemetry stream
├── In-memory SessionManager              — game state + telemetry buffer
└── ghost_ai.py                           — Cerebras LLM harm detection

Backend B — GlobalThreats/backend/main.py (port 8081)  [local only]
├── FastAPI + Uvicorn
├── REST: /api/threats                     — filtered threat events
├── REST: /api/status                      — last refresh + event count
├── REST: /api/refresh                     — trigger live feed fetch
├── APScheduler: every 4 hours            — auto-refresh feeds
└── File: data/threats.json               — persisted threat cache
```

---

## Component Map

### Frontend Shell (`index.html`)

Single HTML file containing:
- Full CSS design system (dark theme, GHOST brand colours)
- Landing/hero page with mouse-spotlight reveal mechanic
- Tab navigation shell (Framework, Invariants, Live Sim, Threat Radar, About)
- JavaScript tab router with iframe lifecycle management
- IAT data and game UI embedded inline via `srcdoc` for proxy compatibility

**Key design decisions:**
- Tabs 01/02 embed `iat.html` content via `srcdoc` (avoids same-origin proxy issues)
- Tab 03 embeds the game UI via `srcdoc`; communicates with the API over REST polling
- Tab 04 loads the radar from a relative path (`/radar/index.html`) so the iframe origin matches the host, enabling CORS on API calls
- `window.__CLOUDLAUNCH_CONFIG__.apiUrl` is injected at build time so the frontend never hard-codes an endpoint
- Each page load creates a fresh isolated session — no cross-visitor session sharing

### IAT Frontend (`iat.html`)

Static single-file app rendering the full 50-invariant catalog with:
- Domain filter buttons (G / H / O / S / T)
- Expandable invariant rows showing telemetry schema and detection signal
- Test case display per invariant
- Hash-based navigation (`#framework` vs `#catalog`)
- `postMessage` listener for parent-frame tab control (enables deep-linking from outer nav)

---

## Data Flow

```
Player Action (browser click)
  │
  ▼
REST polling → /api/sessions/{id}/...
  │
  ├── Validate move (server authority)
  ├── Emit telemetry events → DynamoDB session record
  ├── Evaluate GHOST rules → evidence_level per rule
  └── If chat + minor_flag → ghost_ai.py (Cerebras LLM)
        └── Returns: risk_level, abusive_detected, system_action
  │
  ▼
Browser polls GET /api/sessions/{id}/state + /chat
  ├── Renders board + scores
  ├── Updates GHOST Score panel (G·H·O·S·T letter metrics)
  └── Updates GHOST AI panel (harm analysis results)
```

```
Scheduled/Manual Trigger (CloudWatch Events / APScheduler)
  │
  ▼
Threat handler (lambda_handler → threats/handler.py)
  ├── Fetches 11 live threat feeds (RSS, CSV, plain-text)
  ├── Classifies each event against GHOST domains
  ├── Infers severity (critical / high / medium / low)
  ├── Geo-locates each event
  └── Writes threats.json → S3 (cloud) / disk (local)
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
| Backend framework | FastAPI + Uvicorn (local) / AWS Lambda Python 3.13 (cloud) |
| Real-time comms | WebSockets (local) / REST polling (cloud) |
| Session storage | In-memory SessionManager (local) / DynamoDB with TTL (cloud) |
| LLM harm detection | Cerebras (`gpt-oss-120b`) |
| Threat feeds | httpx + feedparser + standard CSV/text parsing |
| Feed scheduling | APScheduler (local) / CloudWatch Events rate(4 hours) (cloud) |
| Threat cache | Local file `threats.json` (local) / S3 object (cloud) |
| Globe visualisation | Globe.gl (Three.js) |
| Frontend | Vanilla HTML/CSS/JS — no build step required locally |
| Cloud infrastructure | AWS SAM (CloudFormation) |
| CDN + TLS | CloudFront + ACM certificate |
| DNS | Route53 hosted zone with apex + www alias records |

---

## Security Notes

- All game state is server-authoritative — clients cannot forge outcomes
- GHOST AI only activates when a minor player flag is set (by design)
- Chat rate limiting prevents spam (configurable via toggle)
- CORS reflects the request `Origin` header only when it matches the configured domain — both apex and `www` subdomain are accepted; all other origins receive the configured allowed origin, not a wildcard
- The Cerebras API key is passed as a SAM parameter (NoEcho) at deploy time and stored only in the Lambda environment — never committed to source or embedded in the frontend
- Each visitor gets an isolated session created fresh on page load — no cross-device or cross-visitor sharing
- DynamoDB sessions expire automatically via TTL
- The S3 frontend bucket blocks all public access; assets are served exclusively through CloudFront using Origin Access Control (OAC, sigv4)

---

## Local Ports

| Service | Port | URL |
|---------|------|-----|
| Main app + game backend | 8080 | http://localhost:8080 |
| Threat Radar backend | 8081 | http://localhost:8081 |

---

## Production Deployment (AWS)

The production stack is defined in `src/deploy/template.yaml` and deployed via AWS SAM.

### Architecture Diagram

```
Internet
    │
    ▼
Route53
├── Apex A-alias  ──► CloudFront
└── www   A-alias ──► CloudFront
    │
    ▼
CloudFront Distribution
├── HTTPS redirect enforced (HTTP/2)
├── ACM certificate (must be in us-east-1 regardless of stack region)
├── Default origin: S3 frontend bucket (private, OAC sigv4-signed)
│     └── Serves: index.html, iat.html, radar/*, game/*
├── 403/404 → index.html (SPA fallback)
└── Cache policy: CachingOptimized (assets) / no-store (HTML entry points)
    │
    ▼
API Gateway (HTTP API)
    └── /{proxy+}  ANY  ──►  Lambda
    └── /          ANY  ──►  Lambda
    │
    ▼
Lambda Function  (Python 3.13 — single function, all routes)
    │
    ├── POST /api/sessions              create session
    ├── GET  /api/sessions              list sessions
    ├── GET  /api/sessions/{id}/state   board + players
    ├── POST /api/sessions/{id}/join    join as player
    ├── POST /api/sessions/{id}/move    make move
    ├── POST /api/sessions/{id}/chat    send chat
    ├── GET  /api/sessions/{id}/chat    chat history
    ├── GET  /api/sessions/{id}/ghost   GHOST rule evaluation
    ├── GET  /api/sessions/{id}/telemetry  telemetry events
    ├── GET  /api/sessions/{id}/toggles toggle state
    ├── POST /api/sessions/{id}/toggles update toggles
    ├── GET  /api/config/ghost-ai       AI config
    ├── GET  /api/app-info              runtime info
    ├── GET  /api/threats               threat events (filtered)
    ├── GET  /api/status                last refresh + event count
    ├── POST /api/refresh               trigger feed fetch
    └── EventBridge rate(4h)            scheduled threat refresh
    │
    ├── DynamoDB Table
    │     ├── PK: session_id (string)
    │     ├── BillingMode: PAY_PER_REQUEST
    │     └── TTL: ttl attribute (auto-expiry)
    │
    └── S3 Threat Data Bucket
          └── threats.json  (written by threat handler, read by /api/threats)

S3 Frontend Bucket  (separate from threat bucket)
    ├── BlockPublicAcls: true
    ├── BlockPublicPolicy: true
    ├── IgnorePublicAcls: true
    └── RestrictPublicBuckets: true
```

### Request Flow

```
Browser → [custom domain]
    │
    ├── Static assets (HTML / JS / CSS / textures / globe lib)
    │     └── CloudFront cache hit → served from edge
    │     └── CloudFront cache miss → S3 (OAC-signed GetObject)
    │
    └── API calls  /api/*
          └── API Gateway (HTTP API) → Lambda
                ├── Game routes  → reads/writes DynamoDB
                └── Threat routes → reads/writes S3 threat bucket
```

### Build Pipeline

```
src/deploy/
├── template.yaml            SAM infrastructure definition (single source of truth)
├── deploy.sh                One-command build + deploy script
├── backend/
│   ├── lambda_handler.py    Unified entry point + CORS origin reflection
│   ├── game/
│   │   ├── handler.py       Session logic, GHOST rules, AI invocation
│   │   └── rest.py          REST endpoint handlers
│   └── threats/
│       ├── combined.py      /api/threats + /api/status query layer
│       └── handler.py       Feed fetch, classify, geo-locate, write S3
└── frontend/
    ├── src/                 Source HTML/JS/CSS (edit these)
    ├── build/               Assembled output (git-ignored)
    ├── build_frontend.sh    Copies src → build, runs patches
    ├── patch_game.py        Replaces WebSocket connect with REST polling
    └── patch_srcdoc.py      Inlines game + IAT iframes as srcdoc
```

`deploy.sh` steps:
1. `pip install` Lambda dependencies into `backend/game/` and `backend/threats/`
2. `sam build` — packages Lambda with Python 3.13 runtime
3. `sam deploy` — creates/updates the CloudFormation stack; passes domain, cert ARN, hosted zone, and API key as parameters
4. `build_frontend.sh` — patches source and assembles `frontend/build/`
5. `aws s3 sync` — uploads `build/` to the frontend S3 bucket
6. `aws cloudfront create-invalidation` — purges CDN cache

### Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| Single Lambda for all routes | Simpler ops; cold-start latency acceptable for a demo/showcase tool |
| REST polling instead of WebSockets | API Gateway HTTP API is significantly cheaper and simpler than WebSocket API for this use case |
| `srcdoc` inlining for game and IAT iframes | Proxy layers intercept relative URL navigation inside iframes; inlining the HTML as a `srcdoc` attribute bypasses this |
| Radar loaded via relative path (`/radar/index.html`) | Globe.gl (WebGL) requires a real browser origin — `about:blank` blocks canvas; relative path keeps the iframe origin consistent with the parent so CORS headers are valid |
| Per-visitor session creation on boot | Prevents cross-device contamination; DynamoDB TTL cleans up idle sessions automatically |
| CORS origin reflection (apex + www) | Accepts both `example.com` and `www.example.com` without a wildcard `*` in production — implemented by reflecting the `Origin` header when it matches the configured base domain |
| CloudFront OAC (not OAI) | OAC is the current AWS-recommended approach for S3 origins; OAI is deprecated |
| ACM certificate in us-east-1 | CloudFront requires certificates to be in `us-east-1` regardless of the stack's deployment region |
| API key via SAM NoEcho parameter | Key is stored only in Lambda environment variables, never in source control, git history, or `.gitignore` bypass patterns |
