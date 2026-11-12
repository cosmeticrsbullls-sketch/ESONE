# ESONE WhatsApp activation — verified operational checklist (31 Oct 2026)

## Confirmed from Meta Business UI
- Business portfolio: `1095265266448561`
- ESONE Messaging app ID: `2301333040652858`
- Earthshine sender phone number ID: `1364782060053556`
- Approved Utility template: `esone_order_confirmation` (English), four body values in this order: customer/salon, order reference, date, amount
- WhatsApp number appears Connected; system user "Employee" has Full access to ESONE Messaging and WhatsApp assets.
- Authentication OTP template is **not confirmed approved**; attempts to create it reported permission denied.
- **Do not assume** Meta Business UI Full access proves access token scopes or WABA permissions.

## Production preflight (read-only, no secrets exposed)
In Render environment settings, verify **names and values locally** (do not copy tokens into tickets/screenshots):
- `WHATSAPP_PHONE_NUMBER_ID` equals `1364782060053556`
- `WHATSAPP_ORDER_TEMPLATE` equals `esone_order_confirmation`
- `WHATSAPP_ORDER_LANGUAGE` equals `en_US` (or leave unset to use default)
- `WHATSAPP_API_VERSION` follows `vNN.N` and is currently supported
- `WHATSAPP_ACCESS_TOKEN` exists and is active; never log, paste or commit it
- `WHATSAPP_OTP_TEMPLATE` must **not** be configured to an unapproved template.

No environment changes are authorized by this checklist. Compare values without pressing Save/Deploy.

## Meta Code 10 / template-creation permission issue
Check the token's app ID, expiry and granted scopes using Meta Access Token Debugger **privately**. Required API scopes may include `whatsapp_business_messaging` for sending and `whatsapp_business_management` for management; asset access and permissions are separate. Ensure the sender phone ID and approved template belong to the same intended WABA. If the UI still rejects template creation despite verified permissions, escalate to Meta Support with the following redacted information:
- Portfolio ID `1095265266448561`
- App ID `2301333040652858`
- Phone number ID `1364782060053556`
- Template creation error: "This WhatsApp business account does not have permission to create message template."
- Sending error: HTTP 400, Meta code 10
- Ask Meta to identify the exact permission/restriction or WABA ownership/eligibility issue; do not request unrestricted permissions.
- Never include access tokens, customer numbers, OTPs, or customer order details.

## Rollout gates
1. GitHub Actions offline tests pass.
2. Correct environment values independently verified.
3. Meta support resolves template permission, or supplies a confirmed account-specific cause.
4. Authentication template approved; then conduct a consented test recipient delivery.
5. Order template send tested on an authorized test recipient; confirm actual delivery, not only API acceptance.
6. Only after review/approval, merge and deploy. Production database and existing WhatsApp assets remain untouched until authorized.
