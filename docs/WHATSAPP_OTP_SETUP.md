# ESONE customer visit OTP

The live app previously had only a local test OTP and no production transport. The app now supports Meta WhatsApp Cloud API authentication templates. Real delivery requires an Earthshine WhatsApp sender and an approved copy-code authentication template.

In the hosting service's Environment settings, configure:

| Variable | Value |
| --- | --- |
| `WHATSAPP_ACCESS_TOKEN` | Server-side access token authorized for the sender |
| `WHATSAPP_PHONE_NUMBER_ID` | Meta sender phone-number ID, not its mobile number |
| `WHATSAPP_OTP_TEMPLATE` | Approved authentication template name with a copy-code button |
| `WHATSAPP_OTP_LANGUAGE` | Approved language code; default `en_US` |
| `WHATSAPP_API_VERSION` | Supported Graph API version, such as the version shown in Meta's current sender setup |

Store the access token only in hosting environment settings, never GitHub, chat, HTML or client scripts. Configure the template expiration to match ESONE's ten-minute OTP validity. Indian ten-digit customer numbers receive country code 91; international numbers require a country code. ESONE uses the saved WhatsApp number, falling back to the saved mobile.

Before rollout, test delivery to an authorized test recipient from a staging visit. Tests in the repository mock the provider; development did not message real customers or create production visits. API acceptance is recorded as ACCEPTED and is not proof of handset delivery. Delivery webhooks are not part of this release.

If configuration or delivery fails, ESONE keeps the visit in progress and gives a clear explanation. A code becomes verifiable only after provider acceptance. Previous pending codes are superseded only after a successful resend. Resends have a 60-second cooldown and five wrong attempts lock a code. Production never exposes a test code, including if `ESONE_ENV=test` is accidentally set on Render. There is no bypass to mark a visit customer-verified.

Official reference: https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/authentication-templates/copy-code-button-authentication-templates/
