"""Application settings. Every value can be set in backend/.env or as an environment variable."""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-change-me"
PLACEHOLDER_SECRET = "replace-this-with-a-long-random-string"  # the value shipped in .env.example


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- core -------------------------------------------------------------
    app_env: str = "development"  # development | production
    demo_mode: bool = True  # synthetic data, demo logins, test panel, simulated channel
    secret_key: str = DEV_SECRET
    database_url: str = "postgresql+psycopg://niyamit:niyamit@localhost:5432/niyamit"
    redis_url: str = "redis://localhost:6379/0"
    storage_dir: str = "./data/artifacts"
    storage_encryption_key: str = ""  # Fernet key; derived from SECRET_KEY when empty
    public_app_url: str = "http://localhost:3000"  # used in patient links inside messages
    cookie_secure: bool = False  # set true behind HTTPS
    session_hours: int = 12
    patient_otp_provider: str = "development"  # development | twilio | disabled
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_verify_service_sid: str = ""
    tasks_eager: bool = False  # run background jobs inline (tests / no-Redis mode)
    rate_limits_enabled: bool = True
    trusted_proxy_hops: int = 1  # proxies in front of the API that append X-Forwarded-For (the Next.js server)
    inline_scheduler: bool = False  # run periodic jobs inside the API process (no Celery beat)
    log_level: str = "INFO"

    # --- AI providers (see README "Where to paste your keys") -----------------
    llm_provider: str = "sarvam"  # sarvam | openai | rules
    asr_provider: str = "sarvam"  # sarvam | openai | none
    tts_provider: str = "sarvam"  # sarvam | none
    doc_provider: str = "sarvam"  # sarvam | openai | local
    ocr_provider: str = "local"  # local | unlimited (optional, requires a compatible server)
    unlimited_ocr_base_url: str = "http://host.docker.internal:8001/v1"
    unlimited_ocr_model: str = "baidu/Unlimited-OCR"
    unlimited_ocr_runtime: str = "vllm"  # vllm | llamacpp (experimental quantized model)
    unlimited_ocr_timeout_seconds: float = 120.0
    sarvam_api_key: str = ""
    sarvam_base_url: str = "https://api.sarvam.ai"
    sarvam_chat_model: str = "sarvam-105b"
    sarvam_stt_model: str = "saaras:v3"
    sarvam_stt_mode: str = "codemix"
    sarvam_tts_model: str = "bulbul:v4-flash"
    sarvam_tts_speaker_te: str = "kavitha_te_conversation"
    sarvam_tts_speaker_hi: str = "aparna_hi_customer"
    sarvam_tts_speaker_en: str = "simran_en_customer"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5-mini"
    openai_transcribe_model: str = "gpt-4o-mini-transcribe"
    ai_timeout_seconds: float = 30.0
    doc_job_timeout_seconds: float = 120.0
    clarify_confidence_threshold: float = 0.6

    # --- WhatsApp Cloud API (optional real channel) ----------------------------
    whatsapp_enabled: bool = False
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_graph_version: str = "v21.0"
    whatsapp_reminder_template: str = ""  # approved Meta template name for business-initiated reminders

    # --- limits ------------------------------------------------------------
    max_upload_mb: int = 10
    max_audio_mb: int = 3
    max_pdf_pages: int = 10
    max_image_pixels: int = 40_000_000

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def fernet_key(self) -> bytes:
        if self.storage_encryption_key:
            return self.storage_encryption_key.encode()
        digest = hashlib.sha256(("storage:" + self.secret_key).encode()).digest()
        return base64.urlsafe_b64encode(digest)

    @property
    def simulated_webhook_secret(self) -> bytes:
        return hashlib.sha256(("simulated-webhook:" + self.secret_key).encode()).digest()

    def sarvam_ready(self) -> bool:
        return bool(self.sarvam_api_key.strip())

    def openai_ready(self) -> bool:
        return bool(self.openai_api_key.strip())

    def validate_for_startup(self) -> None:
        if self.patient_otp_provider not in ("development", "twilio", "disabled"):
            raise RuntimeError("Unknown PATIENT_OTP_PROVIDER.")
        if self.patient_otp_provider == "twilio" and not (self.twilio_account_sid and self.twilio_auth_token and self.twilio_verify_service_sid):
            raise RuntimeError("Twilio Verify requires account credentials and a Verify service SID.")
        if self.is_production and self.patient_otp_provider == "development":
            raise RuntimeError("Development OTP must be disabled in production.")
        if self.is_production and (self.secret_key in (DEV_SECRET, PLACEHOLDER_SECRET) or len(self.secret_key) < 32):
            raise RuntimeError("SECRET_KEY must be set to a long random value in production.")
        if self.is_production and self.demo_mode:
            raise RuntimeError("DEMO_MODE must be false in production (it enables demo logins).")
        if self.is_production and (not self.cookie_secure or not self.public_app_url.startswith("https://")):
            raise RuntimeError("Production requires COOKIE_SECURE=true and an HTTPS PUBLIC_APP_URL.")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
