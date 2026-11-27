# Clinical validation and release gates

Status: NOT clinically validated. No printed/handwriting accuracy or clinical outcome claim is supported by the test suite.

## Dataset and protocol required

Use appropriately authorized, de-identified documents across laboratories/layouts, PDF text/scans, camera perspective/blur, printed/handwritten/mixed content and each proposed language. Store consent/license/provenance and independent ground truth outside the public repository. Two qualified reviewers should adjudicate medical values, units, dates, medication names/doses and source boxes. Split development/acceptance sets by patient/laboratory; do not tune on acceptance examples.

Report separately by input style/language and parameter: CER, WER, parameter identification, numerical accuracy, unit accuracy, date accuracy, false acceptance and manual-review rate. Denominators, exclusions, sample size and errors must accompany every metric. Controlled provider fixtures verify integration; they do not establish model performance.

## Draft acceptance gates — require clinical approval before use

- Security: zero cross-patient/tenant disclosures in acceptance tests; no plaintext keys in releases.
- Automation policy: zero automatic approvals of AI-only, uncertain, conflicting, unsupported-unit or unsupported-language medical fields.
- Printed numeric/date/unit extraction target: at least 99% exact match on the held-out evaluation set; report confidence intervals and parameter/laboratory slices. This is a proposed engineering gate, not validated clinical safety evidence.
- Handwriting: mandatory human verification for all medication/dose/insulin instructions and uncertain results; zero false acceptance of a critical incorrect value in the acceptance corpus. That observed zero cannot establish zero real-world risk.
- Latency: benchmark native-text, printed OCR, handwriting and provider fallback separately; publish p50/p95 and document size/hardware. Production budget must be agreed and measured, not assumed from a laptop.
- Qualified clinical reviewer must approve intended use, rules, targets, failure handling and residual risk. A team member being an MBBS student does not by itself establish independent clinical sign-off.

Clinical validation, representative labels and approval are outstanding external work. Do not claim Telugu/Hindi handwriting reliability or clinical readiness.
