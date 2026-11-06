"""Twilio Verify REST adapter. Never log response bodies, codes or credentials."""
import httpx
from fastapi import HTTPException
from app.config import settings


def ready():
    return bool(settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_verify_service_sid)


def request(path, data):
    try:
        response = httpx.post(
            "https://verify.twilio.com/v2/Services/" + settings.twilio_verify_service_sid + "/" + path,
            auth=(settings.twilio_account_sid, settings.twilio_auth_token), data=data, timeout=15)
        if response.status_code == 429:
            try:
                provider_code = int(response.json().get("code", 0))
            except (ValueError, TypeError, AttributeError):
                provider_code = 0
            # Verify send/check limits use a verification lifecycle, normally 10 minutes.
            retry = 600 if provider_code in (60202, 60203, 60245) else 60
            try:
                retry = max(retry, min(3600, int(response.headers.get("Retry-After", retry))))
            except ValueError:
                pass
            raise HTTPException(429, "The SMS provider has temporarily limited verification. Wait for the countdown before retrying.",
                                headers={"Retry-After": str(retry)})
        if response.status_code == 404 and path == "VerificationCheck":
            return {"status": "expired"}
        if response.status_code >= 400:
            try:
                provider_code = int(response.json().get("code", 0))
            except (ValueError, TypeError, AttributeError):
                provider_code = 0
            if provider_code == 21608:
                raise HTTPException(422, "This phone number is not enabled for SMS on the clinic's Twilio trial. Ask the clinic to verify this recipient in Twilio.")
            raise HTTPException(503, "SMS verification is unavailable. Try later or contact your clinic.",
                                headers={"Retry-After": "60"})
        return response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "SMS verification is unavailable. Try later or contact your clinic.",
                            headers={"Retry-After": "60"}) from None


def send(phone):
    result = request("Verifications", {"To": phone, "Channel": "sms"})
    sid = result.get("sid", "")
    if result.get("status") != "pending" or not sid.startswith("VE") or len(sid) != 34:
        raise HTTPException(503, "Could not start SMS verification. Try later.")
    return sid


def check(sid, code):
    return request("VerificationCheck", {"VerificationSid": sid, "Code": code}).get("status") == "approved"
