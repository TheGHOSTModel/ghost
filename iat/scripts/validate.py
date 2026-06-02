"""Validate all invariant files against schemas/invariant.schema.json.

Enforces additional rules:
  - Filename matches id
  - IDs are unique across catalog
  - Test ids are unique and reference their invariant
  - Any non-blank status that is NOT 'Active' requires a non-empty 'rationale'
"""
import json, os, sys, re
from pathlib import Path

try:
    import yaml
    import jsonschema
except ImportError:
    print("ERROR: install with: pip install pyyaml jsonschema", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
INV_DIR = ROOT / "invariants"
SCHEMA_PATH = ROOT / "schemas" / "invariant.schema.json"
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

def extract_frontmatter(path):
    text = path.read_text()
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    return yaml.safe_load(m.group(1))

def main():
    schema = json.loads(SCHEMA_PATH.read_text())
    files = sorted(INV_DIR.glob("*.md"))
    if not files:
        print(f"ERROR: no invariant files in {INV_DIR}", file=sys.stderr)
        sys.exit(2)

    errors = []
    ids_seen, test_ids_seen = set(), set()

    for path in files:
        fm = extract_frontmatter(path)
        if fm is None:
            errors.append(f"{path.name}: missing or malformed YAML frontmatter")
            continue
        try:
            jsonschema.validate(fm, schema)
        except jsonschema.ValidationError as e:
            errors.append(f"{path.name}: {e.message} (at {'/'.join(str(p) for p in e.path)})")
            continue

        if fm["id"] != path.stem:
            errors.append(f"{path.name}: id '{fm['id']}' does not match filename")
        if fm["id"] in ids_seen:
            errors.append(f"{path.name}: duplicate id {fm['id']}")
        ids_seen.add(fm["id"])

        for t in fm.get("tests", []):
            tid = t["id"]
            if tid in test_ids_seen:
                errors.append(f"{path.name}: duplicate test id {tid}")
            test_ids_seen.add(tid)
            if not tid.startswith(f"T-{fm['id']}-"):
                errors.append(f"{path.name}: test id {tid} does not match invariant id")

        # rationale required for any non-Active, non-blank status
        status = (fm.get("status") or "").strip()
        rationale = (fm.get("rationale") or "").strip() if fm.get("rationale") else ""
        if status and status != "Active" and not rationale:
            errors.append(f"{path.name}: status '{status}' requires a non-empty 'rationale'")

    if errors:
        print(f"FAIL Validation failed with {len(errors)} error(s):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    print(f"OK Validated {len(files)} invariant files.")
    print(f"   IDs: {len(ids_seen)}    Test cases: {len(test_ids_seen)}")

if __name__ == "__main__":
    main()
