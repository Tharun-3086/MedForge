# Test report

27 November 2026. All new fixtures are synthetic/de-identified text or controlled provider responses. No real patient document was sent to an external provider for these integration tests.

Baseline before this increment: 217 PostgreSQL backend tests and a frontend production build passed.

Structured extraction targeted run: initially 2 failed / 48 passed (unit punctuation handling and OpenAI image path); corrected. Subsequent extraction run: 14 passed. Summary/isolation run initially 1 failed / 18 passed due to a nonexistent demo-clinic test login; corrected to the actual Lakeview fixture. These failures are recorded rather than counted as successful clinical evaluations.

Final full PostgreSQL suite: **242 passed**, 2 expected dependency/image-limit-test warnings, 67.00 seconds. Frontend production build/type validation passed. Browser verification confirmed the English patient summary, source-linked HbA1c explanation and existing reviewed readings display.

A full suite initially found 3 failures / 233 passes in experimental Unlimited-OCR fallback tests after provider selection changed. Corrected routing so explicit DOC_PROVIDER=local never selects an external LLM. Final suite includes those fallback checks.

Live Sarvam smoke tests used generated synthetic text images only. They exposed enum deviations (human-readable test name and generic GLUCOSE). The adapter now canonicalizes explicit parameter labels, refines generic glucose only from an explicit source label, and retains unknown parameters as non-approvable manual-review candidates. Regression tests cover these observed responses.

Final local API acceptance: a newly created fictional patient uploaded a printed image; hybrid OCR + live Sarvam produced fasting glucose 75 mg/dL and HbA1c 7.6%. QA compared the fictional source and approved those fields using a doctor test session. Patient/clinic snapshots matched; JSON summary export worked; duplicate upload reused the same proposal. Upload-through-extraction/review checks took about 22.93 seconds. This is one synthetic smoke test, not p50/p95 or a benchmark. Existing reviewed patient records were not changed.

OpenAI key was not configured; image/schema/provider-selection behavior was verified with controlled responses only. No live OpenAI acceptance claim is made.

Offline benchmark harness: `python -m app.evaluation.medical expected.json predicted.json`. Input is a list of samples with unique id, text, and fields keyed by parameter/unique field ID; each field contains value/unit/date. Predictions may add accepted and needs_review booleans. Outputs include denominators, CER/WER, parameter/numerical/unit/date metrics, false acceptance and manual-review fraction. Run separate labelled cohorts for each style/language. It does not provide ground truth or representative dataset results. Real provider/clinical OCR benchmarking, multi-language handwriting, security penetration testing and production performance remain unmeasured. No OCR accuracy percentages are claimed.


Final frontend trend tests: **2 passed** under Node 22. Final changed/untracked-file scan found zero matches for the configured private API/auth/encryption key values; actual environment files were unchanged. This is not a Git-history secret audit or a penetration test. `git diff --check` passed.


Demo test-patient removal increment: 3 PostgreSQL API tests passed (profile/history removal, phone reuse, stale patient session invalidation, exact-name confirmation, clinical role/tenant/demo guards and protected showcase). Frontend production build passed. These are targeted checks after the prior 242-test full suite; the full suite was not rerun for this small increment. No existing user patient was removed while implementing the feature.


OTP registration-precheck increment: 31 targeted OTP/Twilio/quota/staff-access/removal tests passed, including no provider call or challenge for an unregistered phone and remove/re-add behavior. Existing send-limit tests now explicitly register their synthetic test numbers.
