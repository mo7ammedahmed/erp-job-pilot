"""Shared pytest configuration for the JobPilot backend suite.

The suite talks to a running API over HTTP rather than importing the app, so it needs to know
where that API is and which seeded accounts to sign in as. Reading those from backend/.env
means `pytest` works with no shell setup on any machine, while still allowing explicit
environment variables to override everything (e.g. to run against a hosted preview).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Never let a developer's real .env override an explicit export for the tests.
_env = load_dotenv(BACKEND_DIR / ".env", override=False)

DEFAULTS = {
    "REACT_APP_BACKEND_URL": "http://localhost:8000",
    "ADMIN_EMAIL": "admin@jobpilot.dev",
    "ADMIN_PASSWORD": "JobPilot@Admin2026",
    "TEST_USER_EMAIL": "demo@jobpilot.app",
    "TEST_USER_PASSWORD": "Demo@12345",
}

for key, value in DEFAULTS.items():
    os.environ.setdefault(key, value)
