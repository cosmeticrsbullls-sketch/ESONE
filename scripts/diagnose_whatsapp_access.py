"""Read-only Meta WhatsApp access diagnostics. Never prints access tokens or customer data.

Run locally with WHATSAPP_ACCESS_TOKEN set in the process environment:
    python scripts/diagnose_whatsapp_access.py

No messages are sent and no account settings are changed.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

API = os.getenv("WHATSAPP_API_VERSION", "v23.0")
TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
BUSINESS_ID = "1095265266448561"
PHONE_ID = "1364782060053556"
# IDs surfaced in Meta Business UI; their API type must be verified, not assumed.
CANDIDATES = ("1130462776031942", "1109727761640830", "1795964765014179", "2166488204242273")


def get(path, fields=None):
    url = "https://graph.facebook.com/" + API + "/" + path
    if fields:
        url += "?" + urllib.parse.urlencode(fields)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            detail = json.load(error).get("error", {})
        except (ValueError, OSError):
            detail = {}
        return {"http": error.code, "code": detail.get("code"), "subcode": detail.get("error_subcode")}
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return {"network_error": type(error).__name__}


def report(label, data):
    if "data" in data:
        print(label + ":", [(v.get("id"), v.get("name")) for v in data["data"]])
    elif "http" in data or "network_error" in data:
        print(label + ":", data)
    else:
        print(label + ":", {k: data.get(k) for k in ("id", "name", "display_phone_number", "verified_name", "whatsapp_business_account") if k in data})


def main():
    if not TOKEN:
        print("WHATSAPP_ACCESS_TOKEN is missing; set it locally. Never paste it into chat.")
        return
    if not API.startswith("v") or not API[1:].replace(".", "").isdigit():
        print("Invalid WHATSAPP_API_VERSION")
        return
    report("Business-owned WABAs", get(BUSINESS_ID + "/owned_whatsapp_business_accounts", {"fields": "id,name", "limit": "100"}))
    report("Business-client WABAs", get(BUSINESS_ID + "/client_whatsapp_business_accounts", {"fields": "id,name", "limit": "100"}))
    report("Production phone", get(PHONE_ID, {"fields": "id,display_phone_number,verified_name,whatsapp_business_account"}))
    for candidate in CANDIDATES:
        report("Candidate " + candidate, get(candidate, {"fields": "id,name"}))
    print("Read-only diagnostic complete. Do not share tokens or full provider responses.")


if __name__ == "__main__":
    main()
