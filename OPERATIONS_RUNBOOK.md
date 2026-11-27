# Operations runbook

Owners for clinical incidents, privacy incidents and infrastructure operations must be assigned before production.

- Availability: check `/healthz` for API + DB, worker queues/heartbeat, Redis, storage retrieval and frontend API proxy. Healthz does not verify OCR/model correctness.
- Processing failures: inspect sanitized error code/correlation ID, original availability, model cache, memory and queue state. Retry via supported workflow; do not fabricate completed states or approve fields to hide failures.
- Provider outage: preserve original; use local fallback with uncertainty. Never send documents to an unapproved provider or bypass absent consent.
- Duplicate uploads: exact patient/clinic/hash/style/language/source-type matches reuse extraction under a DB transaction lock. Rejected/deleted artifacts do not block a new upload; existing failed proposals require their retry workflow. Legacy duplicate rows are retained.
- Key incident: revoke/rotate exposed provider credentials, preserve encryption-key access and assess affected records; never log keys or patient documents in an incident ticket.
- Rollback: retain deployed commit/image and env-variable names (not values in Git). Roll back application image first; this increment is additive and old consumers tolerate evidence metadata. Restore DB only under an explicit incident plan to avoid overwriting newer clinical reviews.
- Monitoring pending: queue depth/stuck jobs, p95 OCR/provider latency, extraction errors/manual-review fraction, storage/DB capacity and security alerts. Logs must exclude access links, phone numbers, document text and keys.
