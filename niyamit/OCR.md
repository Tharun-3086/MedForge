# Hybrid medical document reading

Niyamit accepts printed, handwritten and mixed documents. Reading an uploaded
document does not establish that its contents are medically correct. The original
remains the authority for staff review. No extracted medication text becomes a
treatment instruction automatically.

## Pipeline and evidence

1. Upload a photo or PDF and choose writing style (`auto`, `printed`, `handwritten`
   or `mixed`) and document language (`en`, `hi` or `te`). These choices persist with
   the encrypted original through the `20261122_hybrid_ocr` migration.
2. Read PDF text per page. Pages without usable native text use OCR. Hybrid mode
   additionally scans pages with native text so image regions and handwritten
   additions are not skipped. Conflicting text-layer/OCR candidates remain visible.
3. PaddleOCR PP-OCRv5 mobile detection and language-specific recognition produce
   text regions and coordinates. Disjoint table cells on the same baseline join
   into rows. This is conservative row reconstruction, not full PP-StructureV3.
4. For English handwritten/mixed pages, and uncertain regions in automatic mode,
   TrOCR reads individual perspective-corrected line crops. Alternatives retain
   their model name and original coordinates. They never silently replace another
   engine's reading. At most 40 handwriting crops are attempted per document by
   default. Hindi/Telugu handwriting requires manual verification; this English
   TrOCR checkpoint is never applied to those language selections.
5. If PaddleOCR or its weights are unavailable, use Tesseract and mark the fallback
   for review. Low-confidence tokens remain in the source transcription instead
   of disappearing. Tesseract uses the weakest word score for line review routing.
6. Propagate OCR uncertainty and disagreements to extracted fields. Every field
   remains unverified. Handwriting, fallback, conflicting measurements and low
   OCR scores explicitly require clinic verification. OCR scores are heuristic
   routing signals, not calibrated probabilities of medical correctness.
7. Patients can view unverified source text and extraction warnings. Uncertain
   health values do not replace previous usable dashboard readings. A doctor or
   nurse must compare the original and record a verification note or correction.
   Conflicting alternatives must be resolved before a latest value appears.

Medication names, strengths, insulin units, routes, frequency and duration may
appear in raw machine text. This update does not implement a validated structured
medication parser, medication-safety checker, diagnosis or dose recommendation.
The existing follow-up extraction and consent controls remain in force.

## Default installation

`OCR_PROVIDER=local` retains Tesseract/PDF extraction with the improved per-page
PDF handling and review policy. The normal API image does not install Paddle,
PyTorch or Transformers. Existing small Render services can keep this mode.

For Hindi/Telugu printed text, configure the hybrid language models. The default
Tesseract image contains English data only. Selecting a language is routing
metadata, not proof that a fallback engine supports it.

## Optional Docker CPU worker

The heavy models run locally in a separate worker image, not in the Android APK
or frontend. Ensure sufficient RAM/disk for Paddle and CPU PyTorch. Benchmark on
your actual worker; the Render Free API is not a suitable target for this image.

Validated on the test laptop on 22 November after freeing temporary package
caches. The optional image built and ran successfully. Offline container checks
exercised real PaddleOCR, TrOCR and a forced Tesseract fallback. Actual patient
uploads through the local Docker app, clinic source verification and updated
patient readings also passed using synthetic printed and cursive-font fixtures.
This does not establish accuracy on real clinical handwriting.

From `niyamit/`:

```powershell
docker compose -f docker-compose.yml -f docker-compose.ocr.yml build worker
docker compose -f docker-compose.yml -f docker-compose.ocr.yml run --rm --no-deps worker python -m app.prepare_ocr --languages en hi te
docker compose -f docker-compose.yml -f docker-compose.ocr.yml up -d --build
```

Preparation explicitly downloads models to `/data/ocr-models` on the existing
private Docker volume. The running worker defaults to
`OCR_ALLOW_MODEL_DOWNLOADS=false` and uses cached weights only. If preparation
fails, the fallback remains available and flags the result for staff review.
Both API and worker must use `TASKS_EAGER=false` so uploads go to this worker.
The override configures this explicitly. Use a single worker process (`solo`)
to avoid duplicate model memory and competing inference calls. The profile limits
the worker to two CPUs and 2,500 MB RAM. Allow extra time for the first model load;
keep sufficient host disk and memory available for Docker and Windows.

To return to the lightweight worker:

```powershell
docker compose up -d --build backend worker
```

Do not run both Compose stacks as separate projects: they must share the same
database, encrypted artifact volume and encryption key. Back up the database and
stable encryption key before changing a real deployment. No public OCR endpoint
or third-party document upload is introduced by these local models.

## Local Python development

Use a separate Python 3.12 environment. Install the backend requirements and then
the optional CPU packages:

```powershell
python -m pip install -r backend/requirements.txt -c backend/requirements.lock
python -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r backend/requirements-ocr.txt
```

Set `OCR_MODEL_CACHE` to an ignored private directory and run
`python -m app.prepare_ocr --languages en` from `backend/`. Afterwards set
`OCR_PROVIDER=hybrid` with `OCR_ALLOW_MODEL_DOWNLOADS=false` in the worker's local
configuration. Keep weights, uploaded documents and keys out of Git.

## Verification and limits

`tests/test_hybrid_ocr.py` covers per-page PDF routing, native/scanned overlays,
table rows, fallback, handwriting alternatives, regional-language restrictions,
line budgets, consent, role restrictions and patient upload through staff review.
Run it against the separate PostgreSQL test database as described in TESTING.md.

Actual local CPU checks used a synthetic printed lab image and a synthetic
cursive-font image. PaddleOCR extracted BP `120/80 mmHg`, fasting glucose
`110 mg/dL` and HbA1c `6.2 %`. TrOCR ran on cropped cursive text but misread a unit
in one smoke test (`mg/dL` as `mg/d.`), demonstrating why it cannot approve itself.
An isolated PostgreSQL/API run exercised both actual models, patient upload,
uncertainty gating, rejected confirmation without a note, staff correction and
the clinic-reviewed patient reading. No real patient data or SMS was used.

These checks are not clinical handwriting validation. Real prescriptions,
regional-language handwriting, blur, tables and device photographs still need
evaluation using appropriately consented/de-identified examples and clinician
review. Measure exact numeric/unit/dose agreement, disagreements, omissions,
latency, memory and how often the system abstains. Existing hosting remains
unchanged until the code, migration and chosen worker configuration are deployed.

Model references:
- https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html
- https://www.paddleocr.ai/main/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html
- https://huggingface.co/microsoft/trocr-small-handwritten
- https://huggingface.co/docs/transformers/v4.57.1/model_doc/trocr
