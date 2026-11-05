# Security

This release is intended for synthetic-data development and demonstrations. Do not put real patient information in a public demo.

Keep `.env`, credentials, patient artifacts, database dumps, model binaries and backups out of Git. Example credentials in documentation are public demo credentials. Uploaded files are encrypted at rest by the application; preserve the encryption configuration when backing up or migrating.

Development OTP is displayed on screen, restricted to synthetic records and rejected in production. Production startup also requires demo mode off, a strong secret, HTTPS and secure cookies. These controls do not replace a deployment/security review.

Report suspected vulnerabilities privately to the repository owner using an available private reporting channel. Do not post patient data, tokens or credentials in public issues. If a secret was committed, rotate it; deleting it from the current tree does not remove it from Git history.

Run the tests and dependency audits described in `niyamit/TESTING.md`. A clean audit is a point-in-time dependency result, not a guarantee that the application has no vulnerabilities.
