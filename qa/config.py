from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
QA_DIR = ROOT_DIR / "qa"
SCENARIOS_DIR = QA_DIR / "scenarios"
REPORTS_DIR = QA_DIR / "reports"

DATABASE_URL = os.getenv("DATABASE_URL", "")
QA_N8N_WEBHOOK_URL = os.getenv("QA_N8N_WEBHOOK_URL", "http://n8n:5678/webhook/9db5ead4-d4ca-4f5c-a1b4-3969e60cb8df/chat")
QA_BACKEND_URL = os.getenv("QA_BACKEND_URL", "http://backend:8000")
API_KEY = os.getenv("API_KEY", "")

DEFAULT_TIMEOUT_SECONDS = 20
MAX_RETRIES = 3
