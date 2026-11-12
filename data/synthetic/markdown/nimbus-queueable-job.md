---
product: nimbus-crm
product_name: Nimbus CRM (synthetic)
product_is_synthetic: true
version_scheme: salesforce_seasonal
source_name: nimbus-synthetic-markdown
trust_level: synthetic
external_id: queueable-job-guide
title: QueueableJob developer guide
category: developer-guide
source_url: https://docs.nimbus.example/dev/queueable-job
published_at: 2023-10-14
last_updated_at: 2024-06-08
effective_from: "Winter '24"
applicability_provenance: verified
metadata_provenance:
  published_at: verified
  last_updated_at: verified
releases:
  - label: "Winter '24"
---
# QueueableJob developer guide

`QueueableJob` runs a unit of work asynchronously. Implement `QueueableJob` and call `JobQueue.enqueue(new MyJob())`.

## Chaining

A job may enqueue exactly one child job from its `execute()` method. Deeper chains are rejected with `JOB_CHAIN_DEPTH_EXCEEDED`.

## Limits

Up to 50 enqueues per transaction.
