# Command Center improvements

This branch adds Sales / Collection / Demo home sections, Maps links for registered and visit GPS, mobile report cards, reason-required audited management visit closure, authenticated password change, single-use email reset, and reviewed external document imports.

## Deployment requirements

1. Back up the existing persistent database. Check the service's DATABASE_URL; do not use an ephemeral SQLite database for retained documents.
2. Run `python upgrade_features.py` against that database. This adds only `password_resets` and `document_imports`. The application never migrates at startup. Deploy the code only after these tables exist.
3. Keep the existing stable SESSION_SECRET. Existing sessions without a credential fingerprint must sign in again. Every authenticated request rechecks active status and database role. Changing/resetting the password invalidates other sessions.
4. Set `ESONE_PUBLIC_URL=https://esone.theearthshine.com`, SMTP_HOST, SMTP_PORT (587 by default), SMTP_USERNAME, SMTP_PASSWORD and SMTP_FROM. SMTP uses verified STARTTLS. Secrets must stay in Render environment variables. Email reset reports setup unavailable when unconfigured. A real mailbox delivery test is still required after configuration.
5. Photo/scanned PDF extraction now uses the Python packages RapidOCR, ONNX Runtime and pypdfium2 from requirements.txt. No operating-system packages, Docker migration or paid hosting upgrade is required for installation. Small OCR models are bundled with RapidOCR. Documents stay local. English invoice images have been tested; Gujarati recognition is not validated. Real camera quality and Free-instance resource behavior still need live verification.
6. Use UTC on the server (`TZ=UTC`); existing OTP cooldown timestamps compare database UTC with server-local time. The baseline OTP cooldown test fails on a non-UTC server.

## Import behavior and limits

Management can capture a mobile photo or upload JPEG, PNG, WebP or PDF (10 MB maximum; PDF at most 20 pages (at most five scanned pages per upload); images at most 20 megapixels). Original bytes, full extracted text and reviewed details remain in the database. OCR uses no external document service. Reference and total suggestions are heuristic; documents must be checked before confirmation. The supplied text-invoice format now extracts item name, MRP, quantity, unit, rate and amount into editable review fields. Reviewed items are stored as structured JSON with dates, payment mode and extracted customer/balance details. Separate tax lines are retained when detected; absent GST values are not assumed. Other layouts and photographed documents still require review. Item quantities and row sums are checked against subtotal; original cumulative balances remain separate from the invoice total.

Confirmation atomically creates the linked activity and order or collection. Collection imports require a matching existing bill ID for the selected client; import the old bill first if needed. Original-file digest, invoice reference and client/receipt reference guard duplicates. A confirmed import cannot be posted twice. Historical imports leave the current outstanding balance unchanged by default; management explicitly opts in if these entries are not already in the opening balance.

Administrative visit closure cancels pending end OTPs and records the operator, reason and completion time. It preserves original visit notes, check-in, checkout and coordinates. No customer OTP verification or employee checkout is fabricated.

## Validation

Run `TZ=UTC python -m unittest discover -s tests -q`. Tests use an isolated synthetic SQLite database and mocked SMTP/OCR; no production data or messages are used. New cases cover management closure evidence preservation, role and CSRF rejection, inactive session revocation, password changes, single-use email reset, import review/no early ledger writes, duplicate prevention, atomic confirmation and original retention. Live deployment and real document accuracy remain to be verified.

## Outstanding Excel import

The supplied outstanding format is supported directly as `.xlsx` (25 MB maximum). The parser reads party name, area, contact, bill amount/reference/date, outstanding and remarks. It excludes blank-party subtotal rows and preserves source sheet/row. Read-only streaming is capped at 5,000 rows per sheet because formatting may extend to a million rows; the review shows this cap and requires verification that later business records do not exist. Decompressed ZIP content is capped at 200 MB.

Management selects rows, checks invoice references and registered-client matches, and can explicitly create unmatched clients. All selected rows are validated before any ledger writes. Confirmation stores original bill amounts and reviewed outstanding snapshots. Amount-minus-balance is an unallocated reduction, not a fabricated collection receipt: payment date, mode, receipt and allocation cannot be inferred from this sheet. Existing invoices are rejected rather than overwritten. Adding outstanding to current balances is optional; the default preserves already-entered opening balances. Each uploaded sheet is confirmed once; unselected rows are recorded as skipped.

A payment explicitly shown on an imported invoice is handled separately from an outstanding sheet. Its reviewed received amount can create a linked collection record; current balance changes use invoice total minus received, only when opted in.

## Python OCR safeguards

Document extraction uses a short-lived subprocess with a 90-second deadline and an OS file lock. Only one document job runs at a time across server threads/workers. CPU inference is limited to one thread and batch size one; images are normalized for orientation and bounded to 1,800 pixels per side. Scanned pages are rendered and released sequentially. OCR detection boxes are grouped into rows before invoice parsing, preserving adjacent item/price/quantity columns. Runtime imports/model allocations stay outside the web process and are released on exit.

The supplied text invoice and its rendered PNG each produced all 16 item rows with the correct invoice total in local tests. The lower-memory configuration peaked around 381 MB locally, so live Free-instance behavior still must be checked alongside the web process. Small text PDFs avoid model loading. Other layouts or poor camera images may require manual correction before confirmation. No sample/customer files are included in the repository.
