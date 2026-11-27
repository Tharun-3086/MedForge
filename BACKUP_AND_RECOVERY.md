# Backup and recovery

Backup PostgreSQL, encrypted object storage, a protected copy of storage encryption keys, application configuration inventory and deployed image/commit references. A DB-only backup cannot restore originals; ciphertext without the corresponding encryption key is unrecoverable.

Before production define RPO/RTO with the clinic, encrypted backup destination, access/retention owners and incident authorization. Managed-provider backups must be verified, not assumed from a free account.

Restore drill: use an isolated database and private bucket; restore DB and encrypted objects; inject the correct encryption key through a secret manager; run schema/version checks; use synthetic fixtures to verify original retrieval, extraction evidence, field review/audit history and tenant isolation. Record duration, failures and recovery-point loss. Never restore over the live database as a test.

Current status: local backup artifacts exist from prior development, but this increment did not perform or establish a production restore/RPO/RTO test. No backup file or connection secret belongs in Git or an APK release.
