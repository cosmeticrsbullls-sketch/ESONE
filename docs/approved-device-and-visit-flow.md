# Approved browser and single-form visits

## Employee flow

1. Sign in. A new browser goes to **Device approval** with a numbered request.
2. Command Center verifies the employee and approves the request. A replacement revokes the employee's previous approved browser.
3. Punch In, then choose **Add Sales Visit** or **Add Collection Visit**.
4. Select an existing business from the GPS-filtered search. A missing business must first be added through **Add Business** on Home.
5. Enter visit details/outcome. Open the rear camera, photograph the salon, and allow a fresh GPS reading.
6. Tap **Finish**. The server saves one completed visit, its private photo, GPS and audit evidence in one transaction, then the browser returns Home. Retrying the same submission does not create another visit.

There is no separate visit Start/Complete step and no measured visit duration. Existing in-progress records remain finishable through their old detail page. Old create/start endpoints return 410 and cannot create new unstarted visits. Existing records are not rewritten.

## Command Center

**Device Approvals** lists pending browsers and allows approve, reject and revoke. Reviewers cannot approve themselves. Approval is serialized with the employee's field submissions through a user-row lock. A rejected or revoked browser can request review again; it does not regain access automatically.

Super Admin is the explicit bootstrap exception: a successful Super Admin password login can approve a new browser to avoid locking all reviewers out. Other previously approved Super Admin browsers are revoked; bootstrap and revocation are audited. Management and Office need another approved reviewer.

Activity Details / Share and visit detail pages expose an authenticated salon-photo link. Other employees cannot view the photo. Command Center can review photo, GPS accuracy, server recording time and device request ID. Photo data is held in the existing database rather than ephemeral Render disk; existing backups/storage capacity must account for its growth.

## Safeguards and limits

- HTTP-only random persistent device cookie; only its SHA-256 hash is stored. Approval is per account and browser, not a hardware fingerprint. Clearing cookies or using a different browser requires approval again.
- No gallery/file-upload control. Camera permission is requested with `getUserMedia`, rear camera preferred. GPS is requested with no cached fix and must report accuracy within 200 metres.
- A five-minute, single-use challenge binds the image to user, approved browser, business and GPS. Finish rechecks duty, approval, registered business and location radius. Invalid data rolls back all visit/business GPS writes.
- JPEG bytes, dimensions and payload size are checked, decoded and re-encoded to remove metadata. Reusing an identical normalized image is rejected. Photos require authenticated ownership/reviewer access and are served with no-store headers.
- Browser camera and GPS are not identity or hardware attestation. A modified client, virtual camera, copied browser cookies or spoofed GPS can bypass some client-side claims. This reduces casual credential sharing; a salon photo does not prove the employee's identity.
- Native mobile camera permission, preview/retake and real GPS must be checked on an HTTPS staging environment before production rollout. Automated tests use fake media APIs and cannot replace that physical check.

## Rollout and rollback

Deploy only after confirming a Super Admin can access approval, then approve Management/Office and employee browsers. Startup `init_db.py` creates the three additive tables; `upgrade_features.py` can also explicitly create them. No existing business rows are migrated. Run the health readiness check after schema creation.

Rollback the application commit to restore the prior workflow; keep additive tables and evidence intact. Do not delete photos or device audit records during rollback.
