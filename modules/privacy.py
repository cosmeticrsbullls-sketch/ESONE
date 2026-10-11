"""Public privacy notices; no authentication or database access."""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()
CONTACT = 'cosmeticsrsbulls@gmail.com'


def notice(title, content):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} | ESONE</title><style>
body{{margin:0;background:#f6f7f9;color:#26323d;font:16px/1.7 system-ui,sans-serif}}
main{{max-width:800px;margin:40px auto;padding:32px;background:white;border:1px solid #e2e6eb;border-radius:16px}}
a{{color:#805d20}}h1,h2{{line-height:1.3}}h2{{font-size:21px;margin-top:30px}}
nav{{display:flex;gap:20px;flex-wrap:wrap}}.brand{{color:#805d20;font-weight:700}}
@media(max-width:600px){{main{{margin:16px;padding:22px}}}}
</style></head><body><main><p class="brand">ESONE · Earthshine Professional</p>
<h1>{title}</h1>{content}<hr><nav><a href="/privacy-policy">Privacy Policy</a>
<a href="/data-deletion">Data Deletion</a><a href="/">ESONE Login</a></nav></main></body></html>'''


@router.get('/privacy-policy', response_class=HTMLResponse)
def privacy_policy():
    return notice('Privacy Policy', f'''
<p>Effective date: 11 October 2026</p>
<p>Earthshine Professional operates ESONE, a business workspace for its team and customer operations. This policy covers information processed through ESONE and its WhatsApp messaging integration.</p>
<h2>Information we process</h2>
<ul><li>Team account details, including names, email addresses, roles and password hashes.</li>
<li>Salon and business contact details, including names, telephone and WhatsApp numbers, addresses and assigned team members.</li>
<li>Visits, demonstrations, orders, deliveries, collections, payment references, promises to pay, follow-ups and related notes.</li>
<li>Location coordinates provided during location-based field actions, with check-in and check-out times where recorded. These help verify visits and salon locations.</li>
<li>Verification records and communication logs, including recipient numbers, message purpose, provider identifiers and available message status information.</li></ul>
<h2>How we use information</h2>
<p>We use information to authenticate team members, manage customer relationships, verify field activities, fulfil orders, record collections, arrange demonstrations, provide reminders and service updates, and maintain security and audit records. WhatsApp messages may include verification codes, order confirmations and other transactional or service communications. Promotional messages, if offered, require a separate appropriate permission.</p>
<h2>WhatsApp and service providers</h2>
<p>When WhatsApp messaging is enabled, recipient numbers and message content are processed by Meta/WhatsApp and any messaging provider used for delivery. Hosting and database providers process information needed to operate ESONE. Their own privacy policies also apply to their services. Relevant information may be shared with authorised staff and service partners for customer operations, or when required by applicable law. We do not sell personal information.</p>
<h2>Access and security</h2>
<p>ESONE uses account authentication and role-based access for business records. Location-based actions use the device location permission. You can revoke that permission in your device or browser settings; actions requiring location may then be unavailable. No service can guarantee absolute security.</p>
<h2>Retention</h2>
<p>We retain records as needed for business operations, account administration, security, dispute resolution and applicable record-keeping obligations. A deletion request is reviewed for information that can be removed and records that must be retained; retained information is limited to those purposes.</p>
<h2>Your requests and choices</h2>
<p>To request access, correction or deletion of your information, or to raise a privacy concern, email <a href="mailto:{CONTACT}">{CONTACT}</a>. You can also contact us to stop optional WhatsApp communications. See our <a href="/data-deletion">data deletion instructions</a> for the request process.</p>
<h2>Changes and contact</h2>
<p>We may update this policy as ESONE changes. The effective date above identifies the current version. Contact: Earthshine Professional, Ahmedabad, Gujarat, India; <a href="mailto:{CONTACT}">{CONTACT}</a>.</p>''')


@router.get('/data-deletion', response_class=HTMLResponse)
def data_deletion():
    return notice('Data Deletion Instructions', f'''
<p>You can request deletion of personal information held by Earthshine Professional through ESONE and its WhatsApp integration.</p>
<ol><li>Email <a href="mailto:{CONTACT}?subject=ESONE%20Data%20Deletion%20Request">{CONTACT}</a> with the subject <strong>ESONE Data Deletion Request</strong>.</li>
<li>Include your name, the email address or WhatsApp number associated with the information, and the account or records you want reviewed. Do not send passwords, access tokens or verification codes.</li>
<li>We may ask for information needed to verify that the request concerns your records. After review, we will confirm what was deleted and explain any information retained for business, security, dispute resolution or applicable record-keeping obligations.</li></ol>
<p>Requests may cover team account details, customer contact information and communication records. Removing an app connection in Meta does not by itself delete records already held in ESONE. These instructions cover records controlled by Earthshine Professional; data held independently by Meta/WhatsApp or other providers is subject to their own processes.</p>
<p>For a status update, reply to your original request email. See the <a href="/privacy-policy">Privacy Policy</a> for more information.</p>''')
