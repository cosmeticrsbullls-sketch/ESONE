"""Read-only WhatsApp Cloud API diagnostics. Never sends messages or mutates assets.

Run locally with the same environment as ESONE:
    python -m scripts.whatsapp_diagnose
Output never contains access tokens or customer data.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request


def get_json(path, token):
    version = os.getenv("WHATSAPP_API_VERSION", "v23.0")
    if not re.fullmatch(r"v[0-9]+\.[0-9]+", version):
        return {"error": "invalid_api_version"}
    url = "https://graph.facebook.com/" + version + "/" + path
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            return json.loads(response.read(65536))
    except urllib.error.HTTPError as exc:
        try:
            data = json.loads(exc.read(65536)).get("error", {})
            return {"http": exc.code, "code": data.get("code"), "subcode": data.get("error_subcode")}
        except (ValueError, OSError, AttributeError):
            return {"http": exc.code}
    except (urllib.error.URLError, TimeoutError, OSError):
        return {"error": "network_failure"}


def diagnose():
    token = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
    phone = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    if not token or not phone.isdigit():
        return {"status": "missing_credentials"}
    # Both endpoints are GET; no sends, template creation, or account mutations.
    phone_info = get_json(phone + "?fields=id,display_phone_number,verified_name", token)
    if "id" not in phone_info:
        return {"status": "phone_access_failed", "phone_result": phone_info}
    # WABA association: query phone's owning WABA only if API exposes it.
    return {"status": "phone_access_ok", "phone_id_matches": str(phone_info["id"]) == phone,
            "order_template_configured": os.getenv("WHATSAPP_ORDER_TEMPLATE") == "esone_order_confirmation",
            "otp_template_configured": bool(os.getenv("WHATSAPP_OTP_TEMPLATE", "").strip())}


if __name__ == "__main__":
    print(json.dumps(diagnose(), sort_keys=True))
