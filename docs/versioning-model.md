# Versioning model

## Ordering strategies (`app/versioning/ordering.py`)
| Scheme | Example labels | Sequence |
|---|---|---|
| `semver` | `1.9.3`, `v2`, `1.10.0` | major·10⁶ + minor·10³ + patch |
| `salesforce_seasonal` | `Winter '26`, `spring 26` | year·10 + {Winter 0, Spring 1, Summer 2} |
| `explicit` | anything | supplied by the fixture (`releases[].sequence`) |

Labels are normalised before storage (`spring 25` → `Spring '25`), so lookups by label are
stable. A document referencing a release not registered for its product is a **recorded ingestion
failure**, not an auto-created release: we don't manufacture releases.

Note on seasonal names: a "Winter '26" release ships in late 2025. We order by the label year,
which is how the platform itself sequences releases.

## Applicability (`app/versioning/applicability.py`)
Input: target release sequence, `[from, to]` bounds (either may be open), provenance.

| Provenance | In range | Out of range |
|---|---|---|
| verified | `applies` | `not_applicable` |
| inferred | `inferred_applies` | `inferred_not_applicable` |
| unknown, or both bounds open | `unknown` | `unknown` |
| no target version supplied | `unknown` | `unknown` |

The system never upgrades `inferred` or `unknown` to `applies`.

## What a range does and does not say
- `effective_from = Winter '25`, `effective_to = NULL`, verified → documented from Winter '25
  with no documented end. It does **not** claim the behaviour exists in every future release.
- A newer document that doesn't mention a feature is **not** evidence that the feature was
  removed. Phase 4 will classify such cases as `unknown` unless a source states removal.
- Conflicting sources (e.g. two retention periods) are both returned with their own metadata;
  choosing between them is a job for the answer engine, which must surface the conflict.
