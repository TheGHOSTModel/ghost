# Templates

## IAT_Template.xlsx

Blank Invariant-Anchored Telemetry (IAT) spreadsheet for adopting teams.

Use this to assess your platform against all 50 GHOST invariants. For each invariant:

1. Set the **Status** column: `Active` | `Latent` | `Collapsed` | `Inactive (N/A)`
2. Add a **Platform Implementation** note describing how your platform handles it
3. Add a **Rationale** for any non-Active status

The spreadsheet mirrors the structure in [`/iat`](../iat/CATALOG.md).

### Status definitions

| Status | Meaning |
|--------|---------|
| Active | Telemetry exists, is queryable, and the threat catalog binds to it |
| Latent | Telemetry specified but not emitted, or emitted but not queryable |
| Collapsed | Fully covered by another invariant's signals |
| Inactive (N/A) | No surface exists — no telemetry required |
