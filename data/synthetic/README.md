# Synthetic documentation corpus

Everything under this directory describes **Nimbus CRM**, a fictional product invented for
VersionProof AI. It exists to exercise version-aware retrieval with known ground truth.

It must never be presented as Salesforce documentation or as any vendor's release history.
Release labels follow a seasonal scheme (Winter/Spring/Summer 'YY) purely to test the
`salesforce_seasonal` version-ordering strategy.

| Case | Document(s) |
|---|---|
| 1. Workaround later unnecessary | `bulk-export-batch-workaround` → superseded by `bulk-export-v2-release-note` |
| 2. Feature introduced in a newer release | `async-trigger-framework` (Spring '25) |
| 3. API deprecated in a specific version | `legacy-sync-callouts-deprecation` (Summer '24) |
| 4. Conflicting publication dates | `field-history-retention-a` vs `field-history-retention-b` |
| 5. Not in the knowledge base | no document (see evaluation dataset) |
| 6. Precise error code | `error-limit-exceeded-0427` |
| 7. Version-incompatible recommendation | `record-locking-retry-pattern` |
| 8. Similar wording, different behaviour | `scheduled-jobs-concurrency-winter24` vs `-spring25` |
| Unknown applicability | `community-note-platform-cache` |

`markdown/` holds the same product's documentation in front-matter Markdown to exercise a
second loader. Ingest the whole `synthetic/` directory to load both.
