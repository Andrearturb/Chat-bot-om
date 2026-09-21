"""
Configurações principais da aplicação.
"""

import os

from dotenv import load_dotenv

load_dotenv()

APP_NAME = "CHAT Bot APP O&M"
APP_VERSION = "0.1.0"

DATABASE_URL = os.getenv("DATABASE_URL", "")
API_KEY = os.getenv("API_KEY", "")