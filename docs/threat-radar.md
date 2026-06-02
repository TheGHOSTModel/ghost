# Live Threat Radar — Design Document

## Purpose

The Live Threat Radar is a real-time global threat intelligence visualisation. It pulls from 11+ open-source threat feeds, classifies each event against the five GHOST domains, and plots them on an interactive 3D globe.

It demonstrates the **Observability** and **Threat Intelligence** layers of the GHOST framework — showing that the same threat categories that affect gaming platforms (phishing, botnet C2, account takeover, fraud, harassment) are active and measurable in the real world, right now.

---

## Architecture

```
                    ┌─────────────────────────────────┐
                    │  Threat Feed Sources (external)  │
                    │  CISA · SANS · Kaspersky         │
                    │  OpenPhish · Abuse.ch · Feodo    │
                    │  Spamhaus · TheRecord · HelpNet  │
                    │  BleepingComputer · StopForumSpam│
                    └──────────────┬──────────────────┘
                                   │  httpx (HTTPS)
                                   ▼
              GlobalThreats/backend/main.py  (port 8081)
                    │
         ┌──────────┼──────────────────────┐
         │          │                      │
   Feed parsers  GHOST classifier    Geo resolver
   RSS/CSV/text  (keyword → domain)  (country → lat/lng)
         │          │                      │
         └──────────┴──────────────────────┘
                    │
              threats.json (disk / S3)
                    │
         ┌──────────┴──────────────────────┐
         │   REST API                       │
         │   GET /api/threats               │
         │   GET /api/status                │
         │   GET /api/refresh               │
         └──────────┬──────────────────────┘
                    │
              GlobalThreats/frontend/
                    │
              Globe.gl (Three.js)
              3D globe + HUD stats
```

---

## Backend Reference

### `GlobalThreats/backend/main.py`

**Responsibilities:**
- Fetches all configured threat feeds on startup and every 4 hours
- Classifies each event by GHOST domain via keyword matching
- Infers severity (critical / high / medium / low)
- Geo-locates threats by country anchor
- Persists results to `data/threats.json`
- Serves the frontend and REST API

**Key endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serves the globe frontend |
| `GET` | `/api/threats` | All threat events (supports `window` and `ghost` filters) |
| `GET` | `/api/status` | Last refresh timestamp + total event count |
| `GET` | `/api/refresh` | Trigger an immediate live refresh |

**Query parameters for `/api/threats`:**

| Parameter | Values | Description |
|-----------|--------|-------------|
| `window` | `24h`, `7d`, `30d` | Filter by time window |
| `ghost` | `G`, `H`, `O`, `S`, `T` (comma-separated) | Filter by GHOST domain |

---

## Threat Feed Sources

| Source ID | Type | GHOST Domains | URL |
|-----------|------|---------------|-----|
| `cisa` | RSS | G | cisa.gov/news.xml |
| `bsi` | RSS | G | bsi.bund.de |
| `openphish` | Plain text | H, T | openphish.com/feed.txt |
| `kaspersky` | RSS | H, T | kaspersky.com/blog/rss |
| `sans` | RSS | O | isc.sans.edu/rssfeed.xml |
| `abusech` | CSV | O, T, S | urlhaus.abuse.ch |
| `feodo` | Plain text | O | feodotracker.abuse.ch |
| `spamhaus` | Plain text | S, H | spamhaus.org/drop/drop.txt |
| `stopforumspam` | Plain text | S | stopforumspam.com |
| `therecord` | RSS | T, G | therecord.media/feed |
| `helpnet` | RSS | H, O, T | helpnetsecurity.com/feed |
| `bleeping` | RSS | H, O, T | bleepingcomputer.com/feed |

---

## GHOST Domain Classification

Events are classified by keyword matching on title + description:

| Keyword | GHOST Domains |
|---------|---------------|
| `phishing`, `scam` | H, T |
| `harassment` | H, S |
| `ddos`, `botnet`, `infra_attack`, `c2` | O |
| `account_takeover`, `impersonation` | S |
| `fraud`, `asset_theft`, `ransomware` | T |
| `api_abuse`, `policy_failure`, `vulnerability` | G |
| `malware`, `exploit` | H, O |
| `data_breach` | H, T, G |
| `spam` | S, H |

If no keyword matches, the source-level default domain is used.

---

## Threat Event Schema

Each event in `threats.json` follows this structure:

```json
{
  "event_id": "uuid",
  "timestamp": "2026-06-01T12:00:00+00:00",
  "geo": {
    "lat": 51.16,
    "lng": 10.45
  },
  "source": {
    "name": "CISA",
    "country_anchor": "USA",
    "url": "https://..."
  },
  "threat": {
    "title": "Advisory: ...",
    "description": "...",
    "ghost": ["G", "O"],
    "type": "vulnerability"
  },
  "risk": {
    "severity": "high"
  },
  "indicators": {
    "domains": [],
    "ip_addresses": [],
    "urls": [],
    "hashes": []
  }
}
```

---

## Frontend Reference

### `GlobalThreats/frontend/index.html`

Globe container page. Loads Globe.gl from CDN or local lib, and `app.js`.

### `GlobalThreats/frontend/app.js`

Manages the globe, HUD stats, filters, and data refresh:

**Globe rendering:**
- Points coloured by first GHOST domain: G=blue, H=red, O=orange, S=purple, T=green
- Point altitude and radius scaled by severity
- Arcs drawn between high/critical threat origins
- Auto-rotates; stops on hover

**HUD stats:**
- Today / This Month event counts
- Per-domain counts (G · H · O · S · T)
- Live status message

**Controls:**
- Time window filter: All / 24h / 7d / 30d
- Domain filter: ALL / G / H / O / S / T
- Timeline slider: scrub through events by timestamp
- Refresh button: triggers `/api/refresh` and polls until `last_refresh` changes
- Export: JSON and CSV downloads of filtered events

**Tooltip / Side panel:**
- Hover shows threat title, domain, type, country, severity
- Click opens side panel with full description, source link, indicators

---

## Severity Classification

| Level | Conditions |
|-------|-----------|
| `critical` | Title/description contains: `critical`, `zero-day`, `ransomware`, `worm` |
| `high` | Domain includes H + 3 or more domains |
| `medium` | Domain includes H or T |
| `low` | All other cases |

---

## Refresh Behaviour

- **On startup:** Immediate refresh triggered as background task; seed data shown instantly
- **Scheduled:** APScheduler fires every 4 hours (CloudWatch Events on AWS)
- **Manual:** `GET /api/refresh` starts a background fetch; client polls `/api/status` until `last_refresh` changes
- **Full refresh time:** ~30–45 seconds (Kaspersky RSS is slowest)
- **Typical event count:** 250–300 events per refresh

---

## Seed Data

12 static seed events are always included to ensure the globe has content even if all live feeds fail. Seed events cover all five GHOST domains and multiple geographic regions.

---

## SSL / Corporate Proxy Note

On corporate networks with SSL inspection (e.g. Allianz), Python's bundled certificate store may not trust the proxy certificate. The local deployment uses the `truststore` library to load the Windows certificate store. In AWS Lambda this is not needed — standard SSL verification applies.

---

## Local Setup

```bash
# Install dependencies
pip install fastapi uvicorn httpx feedparser apscheduler truststore

# From the GlobalThreats/ directory
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8081

# Globe available at:
# http://localhost:8081/
```
