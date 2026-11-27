# Security review

Read PROJECT_AUDIT.md for baseline findings. This is a source review, not penetration-test certification.

Implemented controls: HttpOnly/Secure-configurable SameSite cookies, scrypt passwords, staff membership checks, patient-cookie tenant checks, clinical-role verification, consent gates, request header CSRF guard, rate limiting, MIME/page/pixel/byte limits, private Fernet-encrypted originals, short-lived signed retrieval, audit logging and production startup checks. Added summary endpoints use the same current-patient/clinic role guards; duplicate lookup and lock include patient and clinic.

Release blockers: document identity reconciliation; independent authorization/penetration testing; malware/parser isolation; real session-revocation review; provider contracts/data transfer review; operational retention/export/deletion; encrypted DB/backups, tested restore, key rotation; monitoring/incident ownership. Demo access and actual medical data must never be mixed. Source flags are not de-identification.

AI controls: uploaded text is untrusted; schemas are bounded; unknown parameters do not become observations; quotes/units/date evidence are checked; conflicting results remain distinct; AI-derived fields need clinical verification and a note. Evidence grounding does not prove medical correctness.

Indian requirements: assess the DPDP Act/Rules, commencement schedule, applicable legacy IT/privacy obligations and whether the intended medical software functionality brings device/clinical requirements. Use [MeitY official Rules](https://www.meity.gov.in/documents/act-and-policies/digital-personal-data-protection-rules-2025-gDOxUjMtQWa?pageTitle=Digital-Personal-Data-Protection-Rules-2025) and obtain qualified advice on applicability. Notification and phased commencement are not the same thing. This repository does not claim regulatory compliance.


Requested login UX change: a pre-OTP 404 now reveals whether a phone has a clinic record, without clinic/profile details. This is an explicit account-enumeration trade-off. Lookup requests have a separate 600/hour/IP throttle; existing verification, phone quotas and consent behavior remain. Review the production privacy threat model before treating this UX as production-approved.
