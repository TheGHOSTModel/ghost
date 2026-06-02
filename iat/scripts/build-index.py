"""Build CATALOG.md and dist/invariants.json from invariants/*.md."""
import json, os, re, sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
INV_DIR = ROOT / "invariants"
CATALOG_PATH = ROOT / "CATALOG.md"
DIST_DIR = ROOT / "dist"
DIST_JSON = DIST_DIR / "invariants.json"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
HEADING_RE = re.compile(r"^#\s+([^\n]+)", re.MULTILINE)

DOMAINS = [
    ("G", "Gameplay"),
    ("H", "Harm & Safety"),
    ("O", "Operations"),
    ("S", "Social Systems"),
    ("T", "Trade & Economy"),
]

STATUS_BADGE = {
    "Active":         "🟢",
    "Latent":         "🟡",
    "Collapsed":      "🔵",
    "Inactive (N/A)": "⚪",
    "":               "▫️",
    None:             "▫️",
}

def load_invariant(path):
    text = path.read_text()
    m = FRONTMATTER_RE.match(text)
    fm = yaml.safe_load(m.group(1))
    heading_m = HEADING_RE.search(text[m.end():])
    short = fm["invariant"]
    if heading_m:
        h = heading_m.group(1).strip()
        if "—" in h:
            short = h.split("—", 1)[1].strip()
    fm["_short"] = short
    fm["_file"] = path.name
    return fm

def build_catalog(invs):
    by_dom = {l: [] for l, _ in DOMAINS}
    for i in invs:
        by_dom[i["id"][0]].append(i)
    for l in by_dom:
        by_dom[l].sort(key=lambda x: x["id"])

    lines = []
    lines.append("<!--")
    lines.append("  GENERATED FILE - do not edit by hand.")
    lines.append("  Source: invariants/*.md")
    lines.append("  Regenerate with: python scripts/build-index.py")
    lines.append("-->")
    lines.append("")
    lines.append("# Invariants Catalog")
    lines.append("")
    lines.append("Fifty universal invariants across five domains. Each cell links to the detailed page with definition, telemetry, detection signal, threats, status guidance, and test cases. Status badges reflect the per-application status set in each file's frontmatter — `▫️` means status is not yet set.")
    lines.append("")
    lines.append("| " + " | ".join(f"{name} ({l})" for l, name in DOMAINS) + " |")
    lines.append("|" + "|".join(["---"] * len(DOMAINS)) + "|")
    for i in range(10):
        cells = []
        for l, _ in DOMAINS:
            items = by_dom[l]
            if i < len(items):
                inv = items[i]
                badge = STATUS_BADGE.get(inv.get("status") or "", "▫️")
                cells.append(f"{badge} [`{inv['id']}`](invariants/{inv['_file']}) {inv['_short']}")
            else:
                cells.append(" ")
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## Status legend")
    lines.append("")
    lines.append("| Badge | Status | Meaning |")
    lines.append("|-------|--------|---------|")
    lines.append("| ▫️ | (blank) | Not yet decided for this application. |")
    lines.append("| 🟢 | Active | Telemetry exists, is queryable, threat catalog binds to it. |")
    lines.append("| 🟡 | Latent | Telemetry specified but not emitted, or emitted but not queryable. |")
    lines.append("| 🔵 | Collapsed | Observability fully covered by another invariant's signals. |")
    lines.append("| ⚪ | Inactive (N/A) | No surface exists, so no telemetry required. |")
    lines.append("")
    counts = {"": 0, "Active": 0, "Latent": 0, "Collapsed": 0, "Inactive (N/A)": 0}
    for i in invs:
        counts[i.get("status") or ""] = counts.get(i.get("status") or "", 0) + 1
    lines.append("## Status summary")
    lines.append("")
    lines.append(f"**Total invariants:** {len(invs)}    ")
    parts = []
    for label, key in [("Active", "Active"), ("Latent", "Latent"), ("Collapsed", "Collapsed"), ("Inactive (N/A)", "Inactive (N/A)"), ("Unset", "")]:
        badge = STATUS_BADGE[key if key else ""]
        parts.append(f"{badge} **{label}:** {counts.get(key, 0)}")
    lines.append("    ".join(parts))
    lines.append("")
    return "\n".join(lines)

def build_json(invs):
    out = []
    for i in invs:
        d = {k: v for k, v in i.items() if not k.startswith("_")}
        d["short_title"] = i["_short"]
        d["file"] = i["_file"]
        out.append(d)
    return {"version": "1.0.0", "invariants": out}

def main():
    files = sorted(INV_DIR.glob("*.md"))
    invs = [load_invariant(p) for p in files]
    CATALOG_PATH.write_text(build_catalog(invs))
    print(f"OK Wrote {CATALOG_PATH.relative_to(ROOT)} ({len(invs)} invariants)")
    DIST_DIR.mkdir(exist_ok=True)
    DIST_JSON.write_text(json.dumps(build_json(invs), indent=2))
    print(f"OK Wrote {DIST_JSON.relative_to(ROOT)}")

if __name__ == "__main__":
    main()
