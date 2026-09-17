"""Environment-backed application configuration."""

import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
PROFESSOR_OUTREACH_CONTACT_EMAIL = os.getenv(
    "PROFESSOR_OUTREACH_CONTACT_EMAIL",
    "contact@example.com",
).strip()
