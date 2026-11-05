# Optional Baidu OCR experiment

**Release default: `OCR_PROVIDER=local` (Tesseract). Baidu is not required and is not enabled by the normal Compose stack.**

The optional `compose.baidu.yml`, `compose.baidu-gpu.yml`, `ops/baidu-ocr` and `unlimited_ocr.py` adapter are retained for future research. They require separately downloaded model weights, substantial disk/RAM and a compatible inference runtime. Model files and source archives must not be committed.

Local experiments with a quantized Unlimited-OCR model produced useful synthetic printed-document extraction, but unconstrained output also produced incorrect preambles and blank-page hallucinations. The adapter adds blank-image checks, required layout format and truncated-output rejection. These checks do not establish medical accuracy. A complete live Baidu patient-to-clinic flow was not accepted for this release.

The user chose Tesseract to complete the project. Keep `OCR_PROVIDER=local`; do not start the optional profile for ordinary setup. Clear printed documents are the supported OCR test cases. Handwritten prescriptions and medication details require human confirmation regardless of provider.
