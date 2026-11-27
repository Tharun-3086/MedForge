# OCR and structured extraction pipeline

## Actual routing

1. Validate MIME/extension, bytes, pages/pixels; retain encrypted original.
2. Reuse identical patient-scoped uploads when not rejected/deleted; preserve existing reviewed records.
3. For auto/printed PDF with text-only pages and sufficiently explicit supported data: embedded text and local rules. This avoids unnecessary external calls and heavyweight image models.
4. Otherwise optional PaddleOCR detects printed text; optional English TrOCR supplies handwriting alternatives; Tesseract is fallback. Scan/image overlaps and disagreements remain review flags. Wrapped table labels use conservative geometry.
5. With consent, configured Sarvam Vision or LLM/OpenAI receives medical measurement schema as well as administrative dates. OpenAI image uploads include the original image with OCR blocks; PDF path currently supplies extracted blocks. No claim of reliable handwritten interpretation follows from generated text.
6. `medical_validation.py` checks allowed parameters, source quote/block IDs, numeric value + exact source unit, source date, range provenance and model/rule disagreements. Model-only measurements always need clinic review. Unknown units remain visible for correction and cannot become approved readings unchanged.
7. Persist proposals/evidence; clinician approves/corrects with source comparison. Patient/clinic snapshots share the same reading service.

## Provider and validation limits

- Supported structured parameters match the current measurement catalogue: glucose types, HbA1c, BP, creatinine, eGFR, UACR, lipids, weight. Medication doses are not measurements.
- Sarvam schema supports arrays/objects per [official Extract API](https://docs.sarvam.ai/api-reference/doc-ai/job/extract). Provider calls still require a configured account and actual acceptance testing.
- Model confidence and OCR confidence are distinct, uncalibrated scores. Neither measures medical correctness.
- Hindi/Telugu UI and language selection exist. Automatic language detection and validated regional handwriting recognition remain pending.
- No production OCR accuracy numbers exist. Current tests include controlled provider output and synthetic geometry, not a representative clinical benchmark.
