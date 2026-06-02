# GHOST IAT

**Invariant-Anchored Telemetry framework** — a game-agnostic catalog of fifty universal invariants that any interactive platform should consider preserving, together with the telemetry that proves whether each one is upheld.

**→ [Browse the full catalog](CATALOG.md)**

## What this is

A platform is safe and fair to the extent it preserves a small set of universal properties: authoritative outcomes, validated inputs, attributable economic actions, observable harm, and so on. Each property is an *invariant*. Each invariant is anchored to a *telemetry event* whose absence, shape, or pattern reveals whether the property holds.

This repository hosts the framework. It is **deliberately application-agnostic** — every invariant is described in general terms, and the per-application `status` field starts blank. Adopting teams choose which invariants apply, which need work, which are covered by another invariant, and which have no surface to apply to.

## How to adopt the framework for an application

1. **Read** [`CATALOG.md`](CATALOG.md) and the individual invariant pages.
2. **Decide a status for each invariant** using the "Status guidance" section on each page. Every page tells you exactly when to mark `Active`, `Latent`, `Collapsed`, or `Inactive (N/A)`.
3. **Edit the frontmatter** of each invariant file: set `status`, set `platform_implementation` (a short note on how your application implements or omits this invariant), and set `rationale` for any non-Active status.
4. **Validate** with `python scripts/validate.py`.
5. **Regenerate** the catalog index and JSON with `python scripts/build-index.py`.

The schema requires a rationale for any status of `Latent`, `Collapsed`, or `Inactive (N/A)` — unjustified decisions fail validation.

## Repo layout

```
.
├── README.md                      this file
├── CATALOG.md                     master index (generated)
├── invariants/                    one file per invariant (50 total)
│   ├── G01.md … T10.md
├── schemas/
│   └── invariant.schema.json      JSON Schema for frontmatter
├── scripts/
│   ├── validate.py                CI-friendly validator
│   └── build-index.py             regenerates CATALOG.md + dist/invariants.json
├── dist/
│   └── invariants.json            app-consumable catalog (generated)
└── .github/workflows/validate.yml CI: validates on every PR
```

## Local workflow

```bash
# One-time setup
pip install pyyaml jsonschema

# Adopt: set status on an invariant
$EDITOR invariants/G01.md

# Validate and rebuild before committing
python scripts/validate.py
python scripts/build-index.py

# Commit and push
git add .
git commit -m "G01: marked Active for production server-validated actions"
git push
```

## Contributing

- Each invariant is a single Markdown file with YAML frontmatter. Frontmatter is the source of truth for structured fields; the body is for prose, examples, and platform notes.
- The framework catalog itself (invariant statements, telemetry shapes, status guidance) should rarely change — those are universal. Most edits are per-application status and rationale.
- `CATALOG.md` and `dist/invariants.json` are generated. Do not edit them by hand.
- All changes must pass `scripts/validate.py` before commit. CI enforces this on pull requests.

## Multi-application use

If one team builds multiple distinct applications on top of the framework, the recommended pattern is one repository per application — each repo forks the catalog and fills in its own status per invariant. The framework itself stays a single shared reference (this repo, kept clean), and applications cherry-pick their statuses without mixing.

## License

[Add your license here.]
