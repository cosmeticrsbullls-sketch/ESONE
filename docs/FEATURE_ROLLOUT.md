# Command Center improvements

This branch adds Sales / Collection / Demo home sections, Maps links for registered and visit GPS, mobile report cards, reason-required audited management visit closure, authenticated password change, single-use email reset, and reviewed external document imports.

## Deployment requirements

1. Back up the existing persistent database. Check the service's DATABASE_URL; do not use an ephemeral SQLite database for retained documents.
2. Run `python upgrade_features.py` against that database. This adds only `password_resets` and `document_imports`. The application never migrates at startup. Deploy the code only after these tables exist.
3. Keep the existing stable SESSION_SECRET. Existing sessions without a credential fingerprint must sign in again. Every authenticated request rechecks active status and database role. Changing/resetting the password invalidates other sessions.
4. Set `ESONE_PUBLIC_URL=https://esone.theearthshine.com`, SMTP_HOST, SMTP_PORT (587 by default), SMTP_USERNAME, SMTP_PASSWORD and SMTP_FROM. SMTP uses verified STARTTLS. Secrets must stay in Render environment variables. Email reset reports setup unavailable when unconfigured. A real mailbox delivery test is still required after configuration.
5. Install `tesseract-ocr` and `poppler-utils` in the service runtime. `Dockerfile.ocr` is an optional Docker runtime definition, not an automatic hosting change. Images and scanned PDFs require these executables. Text PDFs need only the added pypdf dependency. OCR uses local English recognition. Gujarati documents require an additional language model and extractor configuration before claiming support.
6. Use UTC on the server (`TZ=UTC`); existing OTP cooldown timestamps compare database UTC with server-local time. The baseline OTP cooldown test fails on a non-UTC server.

## Import behavior and limits

Management can capture a mobile photo or upload JPEG, PNG, WebP or PDF (10 MB maximum; PDF at most 20 pages; images at most 20 megapixels). Original bytes, full extracted text and reviewed details remain in the database. OCR uses no external document service. Reference and total suggestions are heuristic; documents must be checked before confirmation. Item/tax details are retained as reviewed text, not normalized line-item rows. Layout-specific structured extraction needs real anonymized bill and collection samples before it can be validated.

Confirmation atomically creates the linked activity and order or collection. Collection imports require a matching existing bill ID for the selected client; import the old bill first if needed. Original-file digest, invoice reference and client/receipt reference guard duplicates. A confirmed import cannot be posted twice. Historical imports leave the current outstanding balance unchanged by default; management explicitly opts in if these entries are not already in the opening balance.

Administrative visit closure cancels pending end OTPs and records the operator, reason and completion time. It preserves original visit notes, check-in, checkout and coordinates. No customer OTP verification or employee checkout is fabricated.

## Validation

Run `TZ=UTC python -m unittest discover -s tests -q`. Tests use an isolated synthetic SQLite database and mocked SMTP/OCR; no production data or messages are used. New cases cover management closure evidence preservation, role and CSRF rejection, inactive session revocation, password changes, single-use email reset, import review/no early ledger writes, duplicate prevention, atomic confirmation and original retention. Live deployment and real document accuracy remain to be verified.
