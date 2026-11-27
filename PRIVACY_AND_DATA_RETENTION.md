# Privacy and data retention

Medical documents are sensitive personal data. Only use real records with appropriate authorization, notice/consent and safeguards. A file uploaded into a synthetic clinic remains real personal information if its contents identify someone.

Implemented: patient AI-processing/reminder consent events; local processing when external AI consent is absent; clinic/patient-scoped document access; private encrypted originals; retention dates and scheduler purge; access/review audit. Structured AI metadata and summary exports remain patient-scoped.

Not yet complete: patient-requested comprehensive export/deletion, identity verification for such requests, legal holds, deletion of derived values/provider copies/backups, retention exceptions, documented subprocessors/transfers and incident/grievance procedures. Retention purge currently deletes originals and marks artifacts; it is not proof all personal information has been erased.

Before production define purposes, supported languages/notices, responsible entity/contact, patient rights workflow, age/guardian requirements, data minimization, provider processing terms/retention, access logging, retention periods and backup expiry. Never promise immediate irreversible erasure where a legal hold or backup cycle applies; disclose the actual process.

Assess applicability and commencement with qualified advice using [official MeitY Rules](https://www.meity.gov.in/documents/act-and-policies/digital-personal-data-protection-rules-2025-gDOxUjMtQWa?pageTitle=Digital-Personal-Data-Protection-Rules-2025) and [government commencement clarification](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2198217&lang=1&reg=3). This document is an engineering requirements record, not a compliance certification.
