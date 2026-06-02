# G.H.O.S.T — Gameplay · Harm · Operations · Social · Trade

**G.H.O.S.T** is an open threat-modelling framework for multiplayer gaming platforms. It maps the five domains where harm originates — Gameplay integrity, Harm & Safety, Operations, Social systems, and Trade & Economy — and provides a structured method for assessing whether a platform's telemetry and AI systems can detect, attribute, and respond to threats in real time.

> Most threats in gaming don't break the system — they pass *through* it, using legitimate interactions that cross domain boundaries undetected. GHOST is designed to find them.

---

## The Five Domains

| Letter | Domain | Core question |
|--------|--------|---------------|
| **G** | Gameplay | Are game rules enforced server-side with full observability? |
| **H** | Harm & Safety | Can harmful content and exploitation be detected and attributed? |
| **O** | Operations | Are infrastructure anomalies, floods, and failures observable? |
| **S** | Social | Can coordinated inauthentic behaviour and identity abuse be measured? |
| **T** | Trade & Economy | Are economic actions atomic, attributable, and manipulation-resistant? |

---

## Repository Structure

```
ghost/
├── README.md                    — this file
├── docs/
│   ├── architecture.md          — overall GHOST web application schematic
│   ├── live-sim.md              — Live Simulation harness design
│   └── threat-radar.md         — Live Threat Radar design
├── iat/                         — Invariant-Anchored Telemetry framework
│   ├── README.md                — IAT overview and adoption guide
│   ├── CATALOG.md               — master index of all 50 invariants
│   ├── invariants/              — one .md file per invariant (G01–T10)
│   ├── schemas/                 — JSON Schema for invariant frontmatter
│   ├── scripts/                 — validate.py and build-index.py
│   └── dist/                   — generated invariants.json
├── src/                         — application source code
│   ├── server.py                — FastAPI backend (game engine + telemetry + GHOST AI)
│   ├── ghost_ai.py              — LLM harm detection module
│   ├── app.html                 — GHOST web application shell (5 tabs)
│   ├── index.html               — Live Simulation frontend
│   ├── iat.html                 — Framework & Invariants catalog frontend
│   └── GlobalThreats/          — Threat Radar backend + frontend
├── templates/                   — IAT spreadsheet templates
├── scoring/                     — AGE-X scoring matrix
└── deck/                        — Slides and presentation notes
```

---

## What's in this repo

### `/iat` — Invariant-Anchored Telemetry

Fifty universal invariants across five domains. Each invariant defines:
- A property the platform must preserve
- The telemetry event that proves whether it is upheld
- A detection signal (the filter that fires when the invariant collapses)
- Threat catalogue entries
- Three test cases (EXISTENCE, SCHEMA, FILTER)

[Browse the full catalog →](iat/CATALOG.md)

### `/docs` — Architecture & Design

- [Overall application architecture →](docs/architecture.md)
- [Live Simulation design →](docs/live-sim.md)
- [Threat Radar design →](docs/threat-radar.md)

### `/src` — Application Source

The **GHOST Web Application** is a five-tab single-page app that demonstrates the framework in action:

| Tab | What it does |
|-----|-------------|
| 01 Framework | Interactive walkthrough of the GHOST domains and surfaces |
| 02 Invariants | Full IAT catalog with 50 invariants and telemetry specs |
| 03 Live Sim | Multiplayer TicTacToe harness with real-time GHOST AI monitoring |
| 04 Threat Radar | Live global threat intelligence globe — feeds classified by GHOST domain |
| 05 About | Framework background and links |

### `/templates` — IAT Templates

Blank IAT spreadsheet for adopting teams to assess their platform against the 50 invariants.

### `/scoring` — AGE-X Matrix

Weighted scoring matrix for prioritising which invariants to address first, based on: User Base Coverage, CIA impact, financial exposure, incident likelihood, propagation potential, youth exposure, and regulatory factors.

### `/deck` — Slides

Presentation materials for the GHOST framework.

---

## Getting started

### Run the application locally

**Requirements:** Python 3.12+, pip

```bash
# Install dependencies
pip install fastapi uvicorn httpx feedparser apscheduler truststore

# Start the main app (port 8080)
cd src
python -m uvicorn server:app --host 127.0.0.1 --port 8080 --reload

# Start the Threat Radar (port 8081)
cd src/GlobalThreats
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8081

# Open the app
# http://localhost:8080/app.html
```

### Adopt the IAT framework

```bash
cd iat

# Validate all invariants
python scripts/validate.py

# Regenerate catalog and JSON
python scripts/build-index.py
```

---

## Links

- Website: [theghostmodel.com](https://theghostmodel.com)
- LinkedIn: [harikrishnanss](https://linkedin.com/in/harikrishnanss)

---

## Licence

MIT — see [LICENSE](LICENSE).
