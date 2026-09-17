"""Environment-backed application configuration."""

import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "").strip()
EMAIL_SEND_MODE = os.getenv("EMAIL_SEND_MODE", "test").strip().lower()
RESEND_API_URL = "https://api.resend.com/emails"
PROFESSOR_OUTREACH_CONTACT_EMAIL = os.getenv(
    "PROFESSOR_OUTREACH_CONTACT_EMAIL",
    "contact@example.com",
).strip()
