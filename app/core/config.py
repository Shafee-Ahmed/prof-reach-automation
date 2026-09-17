"""Environment-backed application configuration."""

import os

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "").strip()
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
PROFESSOR_OUTREACH_CONTACT_EMAIL = os.getenv(
    "PROFESSOR_OUTREACH_CONTACT_EMAIL",
    "contact@example.com",
).strip()
