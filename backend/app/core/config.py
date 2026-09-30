"""
Configuração centralizada da aplicação.

Todas as variáveis de ambiente são lidas aqui. Nenhum outro módulo deve
importar os.getenv() diretamente para valores de configuração.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── aplicação ────────────────────────────────────────────────────────────────
APP_NAME = "CHAT Bot APP O&M"
APP_VERSION = "0.1.0"
APP_ENV = os.getenv("APP_ENV", "development")

# ─── banco de dados principal ─────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "")

# ─── chave API legacy (scheduler interno / QA traces) ─────────────────────────
API_KEY = os.getenv("API_KEY", "")

# ─── chave interna server-to-server (n8n → backend) ──────────────────────────
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")

# ─── Tape / scheduler ─────────────────────────────────────────────────────────
TAPE_API_TOKEN = os.getenv("TAPE_API_TOKEN", "")

# ─── n8n ──────────────────────────────────────────────────────────────────────
N8N_HEALTH_URL = os.getenv("N8N_HEALTH_URL", "http://n8n:5678/healthz/readiness")
# Webhook do assistente — NUNCA exposto ao navegador
N8N_CHAT_WEBHOOK_URL = os.getenv("N8N_CHAT_WEBHOOK_URL", "")
# Token opcional para autenticar chamadas backend → n8n
N8N_GATEWAY_TOKEN = os.getenv("N8N_GATEWAY_TOKEN", "")

# ─── storage de documentos ────────────────────────────────────────────────────
ASSET_DOCUMENTS_DIR = os.getenv("ASSET_DOCUMENTS_DIR", "/app/storage/assets_documents")

# ─── OIDC / Keycloak ──────────────────────────────────────────────────────────
OIDC_ISSUER_URL = os.getenv("OIDC_ISSUER_URL", "")
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET", "")
OIDC_REDIRECT_URI = os.getenv("OIDC_REDIRECT_URI", "http://localhost:5173/auth/callback")
OIDC_POST_LOGOUT_REDIRECT_URI = os.getenv("OIDC_POST_LOGOUT_REDIRECT_URI", "http://localhost:5173/login")
# Tempos do fluxo OIDC (valores definidos no spec do Keycloak externo).
OIDC_TOKEN_REFRESH_SECONDS = int(os.getenv("OIDC_TOKEN_REFRESH_SECONDS", "300"))
OIDC_OFFLINE_GRACE_MINUTES = int(os.getenv("OIDC_OFFLINE_GRACE_MINUTES", "15"))
OIDC_CLOCK_SKEW_SECONDS = int(os.getenv("OIDC_CLOCK_SKEW_SECONDS", "30"))
OIDC_LOGIN_REQUEST_TTL_SECONDS = int(os.getenv("OIDC_LOGIN_REQUEST_TTL_SECONDS", "600"))
# Link do console do realm exibido a quem tem users.view. É só um link: o app
# não guarda credencial administrativa do Keycloak.
KEYCLOAK_CONSOLE_URL = os.getenv("KEYCLOAK_CONSOLE_URL", "").strip()

# ─── Keycloak Admin API (gestão de usuários, somente server-side) ─────────────
# Client confidencial com service account e papéis mínimos de realm-management.
# Base URL e realm são derivados do OIDC_ISSUER_URL quando não informados.
KEYCLOAK_ADMIN_CLIENT_ID = os.getenv("KEYCLOAK_ADMIN_CLIENT_ID", "").strip()
KEYCLOAK_ADMIN_CLIENT_SECRET = os.getenv("KEYCLOAK_ADMIN_CLIENT_SECRET", "").strip()
KEYCLOAK_ADMIN_BASE_URL = os.getenv("KEYCLOAK_ADMIN_BASE_URL", "").strip()
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "").strip()
KEYCLOAK_ADMIN_TIMEOUT_SECONDS = float(os.getenv("KEYCLOAK_ADMIN_TIMEOUT_SECONDS", "10"))
# Validade do link de definição de senha enviado por e-mail (quando há SMTP).
KEYCLOAK_ACTION_EMAIL_LIFESPAN_SECONDS = int(os.getenv("KEYCLOAK_ACTION_EMAIL_LIFESPAN_SECONDS", "86400"))

# ─── sessão ───────────────────────────────────────────────────────────────────
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "om_session")
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes"}
SESSION_IDLE_TIMEOUT_MINUTES = int(os.getenv("SESSION_IDLE_TIMEOUT_MINUTES", "30"))
SESSION_ABSOLUTE_TIMEOUT_HOURS = int(os.getenv("SESSION_ABSOLUTE_TIMEOUT_HOURS", "8"))
# Chave Fernet que cifra o refresh token guardado na sessão (server-side).
# Gere: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
SESSION_ENCRYPTION_KEY = os.getenv("SESSION_ENCRYPTION_KEY", "").strip()

# ─── CORS ─────────────────────────────────────────────────────────────────────
_raw_origins = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
FRONTEND_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# ─── bootstrap ────────────────────────────────────────────────────────────────
DEV_ADMIN_EMAIL = os.getenv("DEV_ADMIN_EMAIL", "").strip().lower()
_CONFIGURED_BOOTSTRAP_ADMIN_EMAIL = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
# Em desenvolvimento, o usuário DEV configurado é a referência de bootstrap.
# Isso evita divergência quando DEV_ADMIN_EMAIL é alterado e o .env ainda
# conserva o valor padrão antigo de BOOTSTRAP_ADMIN_EMAIL. Em produção, vale
# exclusivamente BOOTSTRAP_ADMIN_EMAIL.
BOOTSTRAP_ADMIN_EMAIL = (
    DEV_ADMIN_EMAIL
    if APP_ENV.strip().lower() == "development" and DEV_ADMIN_EMAIL
    else _CONFIGURED_BOOTSTRAP_ADMIN_EMAIL
)

# Pré-provisionamento dos usuários DEV do Keycloak local (admin.om, analista.om...).
# Nunca roda fora de APP_ENV=development.
DEV_PROVISION_USERS = (
    APP_ENV.strip().lower() == "development"
    and os.getenv("DEV_PROVISION_USERS", "true").strip().lower() in {"1", "true", "yes", "on"}
)
