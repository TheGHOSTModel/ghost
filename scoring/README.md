# Scoring — AGE-X Matrix

## Overview

The AGE-X Matrix is a weighted prioritisation model for ranking which GHOST invariants to address first on a given platform.

Each invariant is scored across seven dimensions, producing a composite priority score that helps platform teams focus remediation effort where risk is highest.

## Scoring Dimensions

| Dimension | Description | Weight |
|-----------|-------------|--------|
| **UBC** — User Base Coverage | What proportion of the user base is exposed to this threat vector? | High |
| **CIA** — Confidentiality / Integrity / Availability | What is the maximum CIA impact if this invariant collapses? | High |
| **Financial Exposure** | What is the potential financial loss (direct + indirect)? | High |
| **Incident Likelihood** | How likely is this invariant to be tested by a real threat actor? | Medium |
| **Propagation Potential** | Can a single exploit spread to affect many users? | Medium |
| **Youth Exposure** | Are minors disproportionately at risk if this invariant fails? | High |
| **Regulatory Factor** | Are there legal or compliance obligations tied to this invariant? | Medium |

## Score Bands

| Score | Priority | Recommended action |
|-------|----------|--------------------|
| 85–100 | Critical | Address in current sprint |
| 70–84 | High | Address in current quarter |
| 50–69 | Medium | Address in current half-year |
| 30–49 | Low | Address in roadmap |
| 0–29 | Minimal | Monitor only |

## Files

Scoring spreadsheet to be added. Each row represents one invariant (G01–T10) with per-dimension scores and calculated composite.
