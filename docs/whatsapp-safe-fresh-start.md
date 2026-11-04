# ESONE WhatsApp — Safe Fresh Start (isolated experiment)

**Status:** Preparation only. No new Meta App has been created or connected. No messages have been sent from this branch.

## Locked production assets (do not change)
- Business Portfolio ID: `1095265266448561`
- Existing Meta App ID: `2301333040652858` (ESONE Messaging)
- Production WABA ID: `1130462776031942`
- Production Phone Number ID: `1364782060053556`, +91 98249 82419
- Existing approved order template: `esone_order_confirmation`, language `en`
- Existing Haptik credit line and partner links
- Render service ESONE, existing env vars, production database, and custom domain

**Do not** delete, deregister, migrate or re-register the production number; do not remove BSPs, reassign credit lines, change phone PIN/2FA, update webhooks, modify existing app or Render configuration, merge or deploy this branch without fresh approval.

## Known evidence
- Existing System User `Employee` was assigned to the production Messaging Account and WABA and phone-number reads became successful.
- Existing production WABA + phone-number reads and approved-template reads work.
- Template send via standalone Windows script and deployed ESONE returns Meta HTTP 400, code 10, subcode 2593181. This was reproduced outside Render.
- Existing app is Published; Meta Business Support Home shows no account issues for production WABA; a Meta AI assistant asserted an unverified internal block.
- Meta Developer dashboard token-generation workflow requested email verification, but SMS/email codes are not arriving.
- Existing production Render order language is now set to `en`.

## Experiment — no cutover
1. In Meta Developers, select **the existing business portfolio ID 1095265266448561** explicitly. If absent, stop and resolve correct-profile access before proceeding.
2. Create a **separate Meta Business App** for ESONE WhatsApp sandbox evaluation. Do not remove or edit existing App `2301333040652858`. Add the WhatsApp use case.
3. Start only with Meta's provisioned **test WABA/test phone number**. Do not connect, migrate, or register production +91 98249 82419 to the new App during this phase.
4. Create a separate System User for the new App only if required by Meta, and grant minimum needed access to **new test assets**. Never copy permanent tokens into GitHub or chat.
5. Use an allowed, consented test recipient to run a test template from the new Meta test number. Record response code, app ID, sender phone-number ID, test WABA ID, and whether the message was delivered. Keep secrets out of logs and screenshots.
6. Compare new App (test asset) against old App (test asset). A successful sandbox test **does not prove** that the existing BSP-managed production phone can send from the new App.
7. Before trying the existing production phone from the new App, investigate app-to-WABA association and BSP authorization with Meta/Haptik, and obtain separate owner approval for any production asset assignment. No migration or removal.

## Results to capture
- New App ID: _pending_
- New test WABA ID: _pending_
- New test phone-number ID: _pending_
- Test token scopes: _pending_
- Test message HTTP status / error code: _pending_
- Test message delivered: _pending_
- Production sending authorization resolution: _pending_

## Exit criteria
**Success:** new App can send test messages and a separately approved non-disruptive path for the original production sender has been verified.

**Failure:** new App also returns code 10/2593181; stop instead of modifying production and escalate the exact app-to-number authorization failure.

**Roll-back:** no production cutover means nothing to roll back. Leave old App, BSP, phone number, and Render unchanged.
