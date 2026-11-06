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
            raise HTTPException(429, "Too many SMS attempts. Wait before trying again.")
        if response.status_code == 404 and path == "VerificationCheck":
            return {"status": "expired"}
        if response.status_code >= 400:
            raise HTTPException(503, "SMS verification is unavailable. Try later or contact your clinic.")
        return response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "SMS verification is unavailable. Try later or contact your clinic.") from None


def send(phone):
    result = request("Verifications", {"To": phone, "Channel": "sms"})
    sid = result.get("sid", "")
    if result.get("status") != "pending" or not sid.startswith("VE") or len(sid) != 34:
        raise HTTPException(503, "Could not start SMS verification. Try later.")
    return sid


def check(sid, code):
    return request("VerificationCheck", {"VerificationSid": sid, "Code": code}).get("status") == "approved"
