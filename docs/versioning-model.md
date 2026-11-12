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

## Version comparison (`app/comparison/engine.py`)
Deterministic, no LLM. Input: product, earlier release, later release, optional topic.

| Basis | When | Classification | Verified when |
|---|---|---|---|
| `explicit_statement` | a sentence names a registered release next to a change verb ("introduced in X", "deprecated as of X", "removed in X") and X is inside (earlier, later] | introduced / deprecated / removed | the source's own verified `effective_from` equals X |
| `paired_documents` | one document stops applying and a similarly titled one (Jaccard >= 0.6) starts applying in the window | modified (with diff + differing numbers) | both ranges verified |
| `applicability_range` | range alone | introduced / unchanged / unknown | range provenance is verified |

Guarantees:
- A document that merely stops applying is reported as **unknown** with the note "absence of
  documentation is not evidence of removal". `removed` requires an explicit statement.
- Unknown applicability is always `unknown`; it is never placed on the timeline.
- Release names in statements are matched against the product's registered releases, so the
  extractor carries no platform-specific vocabulary beyond three English change verbs.

Known gaps: statement extraction is English, pattern-based and sentence-local; "modified" pairing
depends on title similarity; the `Feature`/`FeatureChange` tables are still unpopulated (events
are computed on read), so curated feature histories are future work.

The timeline (`GET /api/products/{slug}/timeline`) lists, per release, explicit statements plus
`documented_from` / `last_documented` range boundaries, each with its source and verified flag.
