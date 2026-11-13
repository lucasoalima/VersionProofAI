# Documentation sources

Every remote source is reviewed before it is added to `app/ingestion/remote.ALLOWLIST`. Nothing
outside the allowlist can be fetched. This page records each decision. It is an engineering
record, not legal advice.

## In use

### Salesforce CLI release notes
| | |
|---|---|
| Location | `github.com/forcedotcom/cli`, `releasenotes/README.md` (fetched from `raw.githubusercontent.com`) |
| Licence | Apache-2.0, Copyright (c) Salesforce, Inc. (`LICENSE.txt` in that repository, checked 2026-11-12) |
| Automated access | The Salesforce CLI itself reads its release notes from this path |
| Snapshot | `data/real/salesforce-cli/` with `SOURCE.json` (URL, fetch time, SHA-256) and `NOTICE.md` |
| Coverage | 157 released versions, 2.0.2 (2023-07-19) to 2.158.7 (2026-11-04); release candidates skipped |
| Refresh | `python backend/scripts/fetch_source.py` |

Mapping: one document per version; one chunk per top-level entry (NEW / CHANGE / FIX);
`effective_from` = the version in the heading, open-ended, provenance `verified`; release date
from the heading, `verified`.

**What this source cannot tell us.** A release note is a delta. It says what changed in a version,
not when that statement stops being true. A note announcing a command stays "applicable" by range
after a later note removes the command. The engine compensates with one rule for changelog
content: among applicable entries that cover the question, the most recent release leads. That
is a heuristic about deltas, not a verified applicability range.

## Reviewed and not used

### help.salesforce.com / developer.salesforce.com (platform release notes, product docs)
The Salesforce website Terms of Service state that site content may not be used without
permission from Salesforce or its owner unless otherwise permitted by law. VersionProof therefore
does not crawl these sites and does not redistribute their text. Platform documentation can be
ingested locally from files a user supplies (`POST /api/ingestion/local`); such files must stay
out of the repository.

## Adding a source
1. Find the licence and the terms governing automated access; record both here.
2. Add an `AllowedSource` (exact host + path prefix) and a loader implementing `DocumentLoader`.
3. Keep provenance (`SOURCE.json`) with any committed snapshot, and include the upstream licence.
