"""
Live Threat Radar backend — FastAPI
Fetches threat feeds, normalises to GHOST schema, writes threats.json
Serves frontend + data API on port 8081
"""
import asyncio
import csv
import io
import json
import logging
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import ssl
import httpx
import truststore
import feedparser

# Use the Windows certificate store so the corporate SSL proxy certs are trusted
_SSL_CTX = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ── Paths ────────────────────────────────────────────────────────────────────
BASE       = Path(__file__).parent.parent
DATA_DIR   = BASE / "data"
THREATS    = DATA_DIR / "threats.json"
REGISTRY   = DATA_DIR / "sources_registry_full.json"
MAPPING    = DATA_DIR / "ghost_mapping.json"
FRONT      = BASE / "frontend"

DATA_DIR.mkdir(exist_ok=True)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("LiveThreatRadar")

# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="Live Threat Radar API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_last_refresh: Optional[datetime] = None
_refresh_lock = asyncio.Lock()

# ── GHOST mapping ─────────────────────────────────────────────────────────────
GHOST_MAP = {
    "api_abuse":       ["G"],
    "policy_failure":  ["G"],
    "phishing":        ["H", "T"],
    "harassment":      ["H", "S"],
    "scam":            ["H", "T"],
    "ddos":            ["O"],
    "botnet":          ["O"],
    "infra_attack":    ["O"],
    "account_takeover":["S"],
    "impersonation":   ["S"],
    "fraud":           ["T"],
    "asset_theft":     ["T"],
    "malware":         ["H", "O"],
    "ransomware":      ["H", "T"],
    "vulnerability":   ["O", "G"],
    "data_breach":     ["H", "T", "G"],
    "spam":            ["S", "H"],
    "c2":              ["O"],
    "exploit":         ["O", "H"],
}

# Source-level default GHOST classifications
SOURCE_GHOST: dict[str, list[str]] = {}

# Coarse country → lat/lng lookup (expanded set)
GEO_TABLE: dict[str, tuple[float, float]] = {
    "USA":         (37.09,  -95.71),
    "Russia":      (61.52,   105.32),
    "China":       (35.86,   104.19),
    "Germany":     (51.16,   10.45),
    "UK":          (55.37,   -3.43),
    "Switzerland": (46.82,    8.22),
    "Greece":      (39.07,   21.82),
    "Global":      (20.0,     0.0),
    "Brazil":      (-14.23, -51.93),
    "India":       (20.59,   78.96),
    "France":      (46.23,    2.21),
    "Netherlands": (52.13,    5.29),
    "Canada":      (56.13,  -106.35),
    "Australia":   (-25.27,  133.77),
    "Japan":       (36.20,   138.25),
    "South Korea": (35.91,   127.77),
    "Iran":        (32.42,   53.68),
    "North Korea": (40.34,   127.51),
    "Ukraine":     (48.38,   31.16),
    "Romania":     (45.94,   24.96),
    "Nigeria":     (9.08,     8.67),
}


def _load_registry() -> list[dict]:
    if REGISTRY.exists():
        data = json.loads(REGISTRY.read_text())
        sources = data.get("sources", [])
        for s in sources:
            SOURCE_GHOST[s["id"]] = s.get("ghost", [])
        return sources
    return []


def _infer_ghost(text: str, source_id: str) -> list[str]:
    text_lower = text.lower()
    cats: list[str] = []
    for keyword, letters in GHOST_MAP.items():
        if keyword in text_lower:
            cats.extend(letters)
    if not cats:
        cats = SOURCE_GHOST.get(source_id, ["O"])
    return sorted(set(cats))


def _infer_type(text: str) -> str:
    text_lower = text.lower()
    for keyword in GHOST_MAP:
        if keyword in text_lower:
            return keyword
    return "unknown"


def _infer_severity(ghost: list[str], text: str) -> str:
    text_lower = text.lower()
    if any(w in text_lower for w in ["critical", "zero-day", "ransomware", "worm"]):
        return "critical"
    if "H" in ghost and len(ghost) >= 3:
        return "high"
    if "H" in ghost or "T" in ghost:
        return "medium"
    return "low"


def _geo(country: str) -> dict:
    lat, lng = GEO_TABLE.get(country, GEO_TABLE["Global"])
    # small jitter so points don't exactly stack
    import random
    return {
        "lat": lat + random.uniform(-2.5, 2.5),
        "lng": lng + random.uniform(-2.5, 2.5),
    }


def _make_event(title: str, description: str, source_id: str,
                source_name: str, country: str, url: str = "",
                published: Optional[str] = None) -> dict:
    ghost = _infer_ghost(f"{title} {description}", source_id)
    threat_type = _infer_type(f"{title} {description}")
    return {
        "event_id":  str(uuid.uuid4()),
        "timestamp": published or datetime.now(timezone.utc).isoformat(),
        "geo":       _geo(country),
        "source": {
            "name":           source_name,
            "country_anchor": country,
            "url":            url,
        },
        "threat": {
            "title":       title[:200],
            "description": description[:1000],
            "ghost":       ghost,
            "type":        threat_type,
        },
        "risk": {
            "severity": _infer_severity(ghost, f"{title} {description}"),
        },
        "indicators": {"domains": [], "ip_addresses": [], "urls": [], "hashes": []},
    }


# ── Feed fetchers ─────────────────────────────────────────────────────────────

async def _fetch_rss(client: httpx.AsyncClient, src: dict) -> list[dict]:
    events = []
    try:
        r = await client.get(src["url"], timeout=15, follow_redirects=True)
        feed = feedparser.parse(r.text)
        country = src.get("country", "Global")
        for entry in feed.entries[:30]:
            title = entry.get("title", "Untitled")
            desc  = entry.get("summary", entry.get("description", ""))
            link  = entry.get("link", src["url"])
            pub   = entry.get("published", None)
            if pub:
                try:
                    from email.utils import parsedate_to_datetime
                    pub = parsedate_to_datetime(pub).isoformat()
                except Exception:
                    pub = None
            events.append(_make_event(title, desc, src["id"], src["id"].upper(), country, link, pub))
        log.info(f"RSS {src['id']}: {len(events)} events")
    except Exception as e:
        log.warning(f"RSS {src['id']} failed: {e}")
    return events


async def _fetch_openphish(client: httpx.AsyncClient, src: dict) -> list[dict]:
    events = []
    try:
        r = await client.get(src["url"], timeout=15, follow_redirects=True)
        lines = [l.strip() for l in r.text.splitlines() if l.strip()][:100]
        for line in lines:
            domain = re.sub(r"https?://([^/]+).*", r"\1", line)
            events.append(_make_event(
                f"Phishing URL: {domain}",
                f"Active phishing endpoint: {line}",
                src["id"], "OpenPhish", src.get("country", "USA"), line
            ))
        log.info(f"OpenPhish: {len(events)} events")
    except Exception as e:
        log.warning(f"OpenPhish failed: {e}")
    return events


async def _fetch_abusech_csv(client: httpx.AsyncClient, src: dict) -> list[dict]:
    events = []
    try:
        r = await client.get(src["url"], timeout=20, follow_redirects=True)
        reader = csv.reader(io.StringIO(r.text, newline=''))
        count = 0
        for row in reader:
            if not row or row[0].startswith("#"):
                continue
            url_val = row[2] if len(row) > 2 else row[0]
            domain = re.sub(r"https?://([^/]+).*", r"\1", url_val)
            events.append(_make_event(
                f"Malware URL: {domain}",
                f"URLhaus malicious URL: {url_val}",
                src["id"], "Abuse.ch URLhaus", src.get("country", "Switzerland"), url_val
            ))
            count += 1
            if count >= 80:
                break
        log.info(f"Abuse.ch: {len(events)} events")
    except Exception as e:
        log.warning(f"Abuse.ch failed: {e}")
    return events


async def _fetch_feodo(client: httpx.AsyncClient, src: dict) -> list[dict]:
    events = []
    try:
        r = await client.get(src["url"], timeout=15, follow_redirects=True)
        count = 0
        for line in r.text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            events.append(_make_event(
                f"C2 Botnet IP: {line.split(',')[0]}",
                f"Feodo Tracker confirmed C2/botnet IP: {line}",
                src["id"], "Feodo Tracker", "Global"
            ))
            count += 1
            if count >= 50:
                break
        log.info(f"Feodo: {len(events)} events")
    except Exception as e:
        log.warning(f"Feodo failed: {e}")
    return events


async def _fetch_spamhaus(client: httpx.AsyncClient, src: dict) -> list[dict]:
    events = []
    try:
        r = await client.get(src["url"], timeout=15, follow_redirects=True)
        count = 0
        for line in r.text.splitlines():
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            ip_block = line.split(";")[0].strip()
            events.append(_make_event(
                f"Spam/DROP block: {ip_block}",
                f"Spamhaus DROP listed CIDR block: {ip_block}",
                src["id"], "Spamhaus", "Global"
            ))
            count += 1
            if count >= 50:
                break
        log.info(f"Spamhaus: {len(events)} events")
    except Exception as e:
        log.warning(f"Spamhaus failed: {e}")
    return events


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def fetch_all_feeds() -> list[dict]:
    sources = _load_registry()
    if not sources:
        log.warning("No sources registry found — using seed data only")
        return []

    all_events: list[dict] = []
    async with httpx.AsyncClient(headers={"User-Agent": "LiveThreatRadar/1.0"}, verify=_SSL_CTX) as client:
        tasks = []
        for src in sources:
            sid = src["id"]
            url = src.get("url", "")
            if sid == "openphish":
                tasks.append(_fetch_openphish(client, src))
            elif sid == "abusech":
                tasks.append(_fetch_abusech_csv(client, src))
            elif sid == "feodo":
                tasks.append(_fetch_feodo(client, src))
            elif sid == "spamhaus":
                tasks.append(_fetch_spamhaus(client, src))
            elif url.endswith((".xml", "/rss", "/feed", "feed/", "rss/")):
                tasks.append(_fetch_rss(client, src))
            elif "rss" in url or "feed" in url or "news.xml" in url:
                tasks.append(_fetch_rss(client, src))
            else:
                log.info(f"Skipping {sid} (no fetcher for URL pattern)")

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_events.extend(r)

    log.info(f"Total raw events fetched: {len(all_events)}")
    return all_events


def _seed_events() -> list[dict]:
    """Deterministic seed data so the globe always has something to show."""
    seeds = [
        ("Steam account harvesting campaign", "Credential phishing targeting Steam users via fake login portals.", "phishing", "H", "USA", 37.09, -95.71),
        ("DDoS spike on EU game servers", "Coordinated volumetric attack on Frankfurt CDN nodes.", "ddos", "O", "Germany", 51.16, 10.45),
        ("Fake Roblox currency scam", "Social engineering campaign selling fake Robux on Discord.", "scam", "S", "Brazil", -14.23, -51.93),
        ("Botnet C2 activity — East Asia", "Feodo-tracked C2 beacons from South Korean hosting.", "botnet", "O", "South Korea", 35.91, 127.77),
        ("Ransomware targeting game studios", "LockBit affiliate observed deploying ransomware against indie studios.", "ransomware", "H", "Russia", 61.52, 105.32),
        ("Item duplication exploit sold on forums", "Trade-layer exploit listing for a major MMO asset dupe bug.", "asset_theft", "T", "China", 35.86, 104.19),
        ("CISA advisory: gaming API abuse", "Governance alert on unauthenticated gaming platform API endpoints.", "api_abuse", "G", "USA", 38.89, -77.03),
        ("Fake gaming VPN phishing", "Phishing kit mimicking popular gaming VPN providers.", "phishing", "H", "Ukraine", 50.45, 30.52),
        ("Coordinated review bombing campaign", "Organised social manipulation targeting indie game reviews.", "impersonation", "S", "India", 20.59, 78.96),
        ("Account marketplace fraud", "Underground market trading verified gaming accounts.", "fraud", "T", "Netherlands", 52.37, 4.89),
        ("Game cheat malware dropper", "Cheat tool download laced with infostealer payload.", "malware", "H", "Romania", 45.94, 24.96),
        ("NFT gaming asset fraud", "Fake NFT gaming assets sold on cloned marketplace.", "fraud", "T", "Nigeria", 9.08, 8.67),
    ]
    import random
    now = datetime.now(timezone.utc)
    events = []
    for i, (title, desc, ttype, ghost_letter, country, lat, lng) in enumerate(seeds):
        ghost = _infer_ghost(f"{title} {desc}", "seed")
        if ghost_letter not in ghost:
            ghost.append(ghost_letter)
        ts = (now - timedelta(hours=random.randint(0, 168))).isoformat()
        events.append({
            "event_id":  str(uuid.uuid4()),
            "timestamp": ts,
            "geo":       {"lat": lat + random.uniform(-1, 1), "lng": lng + random.uniform(-1, 1)},
            "source":    {"name": "GHOST Seed", "country_anchor": country, "url": ""},
            "threat":    {"title": title, "description": desc, "ghost": sorted(set(ghost)), "type": ttype},
            "risk":      {"severity": _infer_severity(ghost, f"{title} {desc}")},
            "indicators": {"domains": [], "ip_addresses": [], "urls": [], "hashes": []},
        })
    return events


async def refresh_threats():
    global _last_refresh
    async with _refresh_lock:
        log.info("Refreshing threat data...")
        live = await fetch_all_feeds()
        seed = _seed_events()
        combined = seed + live
        THREATS.write_text(json.dumps(combined, indent=2))
        _last_refresh = datetime.now(timezone.utc)
        log.info(f"threats.json written — {len(combined)} events")


# ── API routes ────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    _load_registry()
    # Write seed immediately so globe loads on first visit
    if not THREATS.exists():
        seed = _seed_events()
        THREATS.write_text(json.dumps(seed, indent=2))
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(refresh_threats, "interval", hours=4, id="refresh")
    scheduler.start()
    # Kick off first live refresh in background
    asyncio.create_task(refresh_threats())


@app.get("/api/threats")
async def get_threats(
    window: Optional[str] = Query(None, description="24h | 7d | 30d"),
    ghost:  Optional[str] = Query(None, description="G,H,O,S,T"),
):
    if not THREATS.exists():
        return JSONResponse([])
    data = json.loads(THREATS.read_text())
    now = datetime.now(timezone.utc)
    if window:
        delta = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}.get(window)
        if delta:
            cutoff = (now - delta).isoformat()
            data = [e for e in data if e.get("timestamp", "") >= cutoff]
    if ghost:
        letters = [g.strip().upper() for g in ghost.split(",")]
        data = [e for e in data if any(g in e["threat"].get("ghost", []) for g in letters)]
    return JSONResponse(data)


@app.get("/api/refresh")
async def trigger_refresh():
    asyncio.create_task(refresh_threats())
    return {"status": "refresh started"}


@app.get("/api/status")
async def status():
    count = 0
    if THREATS.exists():
        count = len(json.loads(THREATS.read_text()))
    return {
        "last_refresh": _last_refresh.isoformat() if _last_refresh else None,
        "total_events": count,
    }


# Serve frontend
app.mount("/", StaticFiles(directory=str(FRONT), html=True), name="frontend")
