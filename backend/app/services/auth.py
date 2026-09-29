"""
Serviço de autenticação e autorização da aplicação.

Responsabilidades:
- gerenciar sessões server-side;
- resolver permissões do usuário (perfil + overrides);
- verificar limites de uso da IA;
- registrar eventos de auditoria e segurança;
- fluxo OIDC (redirect, callback, logout).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import (
    OIDC_CLIENT_ID,
    OIDC_CLIENT_SECRET,
    OIDC_ISSUER_URL,
    OIDC_POST_LOGOUT_REDIRECT_URI,
    OIDC_REDIRECT_URI,
    SESSION_ABSOLUTE_TIMEOUT_HOURS,
    SESSION_IDLE_TIMEOUT_MINUTES,
    BOOTSTRAP_ADMIN_EMAIL,
)
from app.models.auth import (
    AiUsage,
    AppUser,
    AuditLog,
    AssistantConversation,
    OidcIdentity,
    Permission,
    Profile,
    ProfilePermission,
    SecurityEvent,
    UserPermissionOverride,
    UserSession,
)

# ─── Constantes ───────────────────────────────────────────────────────────────

PROFILE_NAMES = {
    "ADMINISTRADOR": {
        "display": "Administrador",
        "ai_daily": 200,
        "ai_per_min": 20,
        "permissions": [
            "assistant.use", "assistant.history",
            "indicators.view",
            "assets.view", "assets.create", "assets.edit", "assets.delete", "assets.import",
            "documents.view", "documents.upload", "documents.replace", "documents.delete",
            "audit.view", "users.manage",
            "settings.view", "settings.manage",
            "sync.tape",
        ],
    },
    "ANALISTA": {
        "display": "Analista",
        "ai_daily": 150,
        "ai_per_min": 10,
        "permissions": [
            "assistant.use", "assistant.history",
            "indicators.view",
            "assets.view", "assets.create", "assets.edit",
            "documents.view", "documents.upload", "documents.replace",
            "settings.view",
        ],
    },
    "GERENTE": {
        "display": "Gerente",
        "ai_daily": 120,
        "ai_per_min": 10,
        "permissions": [
            "assistant.use", "assistant.history",
            "indicators.view",
            "assets.view", "assets.create", "assets.edit", "assets.delete", "assets.import",
            "documents.view", "documents.upload", "documents.replace", "documents.delete",
            "audit.view",
            "settings.view",
        ],
    },
    "DIRETOR": {
        "display": "Diretor",
        "ai_daily": 80,
        "ai_per_min": 8,
        "permissions": [
            "assistant.use", "assistant.history",
            "indicators.view",
            "assets.view",
            "documents.view",
            "settings.view",
        ],
    },
    "CONVIDADO": {
        "display": "Convidado",
        "ai_daily": 20,
        "ai_per_min": 3,
        "permissions": [
            "assistant.use", "assistant.history",
            "indicators.view",
            "assets.view",
        ],
    },
}

ALL_PERMISSIONS = [
    ("assistant.use",       "Usar o assistente IA"),
    ("assistant.history",   "Ver histórico de conversas"),
    ("indicators.view",     "Ver Central de Indicadores"),
    ("assets.view",         "Ver Central de Ativos"),
    ("assets.create",       "Cadastrar ativos e equipamentos"),
    ("assets.edit",         "Editar ativos e equipamentos"),
    ("assets.delete",       "Excluir ativos e equipamentos"),
    ("assets.import",       "Importar ativos via Excel"),
    ("documents.view",      "Ver documentos da loja"),
    ("documents.upload",    "Fazer upload de documento"),
    ("documents.replace",   "Substituir arquivo de documento"),
    ("documents.delete",    "Excluir documento"),
    ("audit.view",          "Ver log de auditoria"),
    ("users.manage",        "Gerenciar usuários e acessos"),
    ("settings.view",       "Ver configurações"),
    ("settings.manage",     "Alterar configurações"),
    ("sync.tape",           "Executar sincronização da Tape"),
]


# ─── Seed idempotente ─────────────────────────────────────────────────────────

def seed_profiles_and_permissions(db: Session) -> None:
    """Garante que perfis e permissões existem. Idempotente."""
    for code, description in ALL_PERMISSIONS:
        if not db.scalar(select(Permission).where(Permission.code == code)):
            db.add(Permission(code=code, description=description))
    db.flush()

    for name, cfg in PROFILE_NAMES.items():
        profile = db.scalar(select(Profile).where(Profile.name == name))
        if not profile:
            profile = Profile(
                name=name,
                display_name=cfg["display"],
                ai_daily_limit=cfg["ai_daily"],
                ai_per_minute_limit=cfg["ai_per_min"],
            )
            db.add(profile)
            db.flush()
        else:
            profile.ai_daily_limit = cfg["ai_daily"]
            profile.ai_per_minute_limit = cfg["ai_per_min"]

        existing_codes = {
            db.get(Permission, pp.permission_id).code
            for pp in db.scalars(
                select(ProfilePermission).where(ProfilePermission.profile_id == profile.id)
            ).all()
        }
        for pcode in cfg["permissions"]:
            if pcode not in existing_codes:
                perm = db.scalar(select(Permission).where(Permission.code == pcode))
                if perm:
                    db.add(ProfilePermission(profile_id=profile.id, permission_id=perm.id))

    db.commit()


# ─── Hashing helpers ──────────────────────────────────────────────────────────

def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


# ─── Sessões ──────────────────────────────────────────────────────────────────

def create_session(db: Session, user_id: int, ip: str | None = None, ua: str | None = None) -> str:
    """Cria uma sessão server-side. Retorna o token opaco."""
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    session = UserSession(
        user_id=user_id,
        session_token_hash=_sha256(token),
        csrf_secret=csrf,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(minutes=SESSION_IDLE_TIMEOUT_MINUTES),
        absolute_expires_at=now + timedelta(hours=SESSION_ABSOLUTE_TIMEOUT_HOURS),
        ip_hash=_sha256(ip) if ip else None,
        user_agent_hash=_sha256(ua) if ua else None,
    )
    db.add(session)
    db.commit()
    return token


def get_session(db: Session, token: str) -> UserSession | None:
    token_hash = _sha256(token)
    session = db.scalar(select(UserSession).where(UserSession.session_token_hash == token_hash))
    if session is None:
        return None
    now = datetime.utcnow()
    if session.revoked_at is not None:
        return None
    if now > session.expires_at or now > session.absolute_expires_at:
        return None
    return session


def refresh_session(db: Session, session: UserSession) -> None:
    """Atualiza last_seen e idle expiry sem bater no banco em todo request."""
    now = datetime.utcnow()
    delta = now - session.last_seen_at
    if delta.total_seconds() > 60:
        session.last_seen_at = now
        session.expires_at = now + timedelta(minutes=SESSION_IDLE_TIMEOUT_MINUTES)
        db.commit()


def revoke_session(db: Session, token: str) -> None:
    session = get_session(db, token)
    if session:
        session.revoked_at = datetime.utcnow()
        db.commit()


# ─── Resolução de permissões ──────────────────────────────────────────────────

def get_user_permissions(db: Session, user: AppUser) -> set[str]:
    """
    Resolve o conjunto de permissões do usuário considerando:
    1. Permissões do perfil.
    2. Overrides individuais (deny prevalece sobre allow do perfil).
    """
    profile_perms: set[str] = set()
    if user.profile_id:
        rows = db.execute(
            select(Permission.code)
            .join(ProfilePermission, ProfilePermission.permission_id == Permission.id)
            .where(ProfilePermission.profile_id == user.profile_id)
        ).scalars().all()
        profile_perms = set(rows)

    overrides = db.scalars(
        select(UserPermissionOverride).where(UserPermissionOverride.user_id == user.id)
    ).all()
    allow_overrides: set[str] = set()
    deny_overrides: set[str] = set()
    for override in overrides:
        perm = db.get(Permission, override.permission_id)
        if perm:
            if override.effect == "allow":
                allow_overrides.add(perm.code)
            else:
                deny_overrides.add(perm.code)

    result = (profile_perms | allow_overrides) - deny_overrides
    return result


def user_has_permission(db: Session, user: AppUser, permission_code: str) -> bool:
    perms = get_user_permissions(db, user)
    return permission_code in perms


# ─── Validação de usuário ─────────────────────────────────────────────────────

def check_user_active(user: AppUser) -> tuple[bool, str]:
    """Retorna (ok, motivo_bloqueio)."""
    if user.status == "pending":
        return False, "Seu acesso ainda está pendente de aprovação."
    if user.status == "disabled":
        return False, "Sua conta está desativada."
    if user.access_expires_at and datetime.utcnow() > user.access_expires_at:
        return False, "Seu acesso expirou."
    return True, ""


# ─── Limites de IA ────────────────────────────────────────────────────────────

def get_ai_limits(db: Session, user: AppUser) -> tuple[int, int]:
    """Retorna (daily_limit, per_minute_limit) considerando override individual."""
    if user.ai_daily_limit_override is not None and user.ai_per_minute_limit_override is not None:
        return user.ai_daily_limit_override, user.ai_per_minute_limit_override

    profile = db.get(Profile, user.profile_id) if user.profile_id else None
    if profile:
        daily = user.ai_daily_limit_override if user.ai_daily_limit_override is not None else profile.ai_daily_limit
        per_min = user.ai_per_minute_limit_override if user.ai_per_minute_limit_override is not None else profile.ai_per_minute_limit
        return daily, per_min
    return 10, 2


def check_ai_rate_limit(db: Session, user: AppUser) -> dict[str, Any]:
    """
    Verifica limites de IA. Retorna:
    {"allowed": bool, "used_today": int, "daily_limit": int,
     "used_this_minute": int, "per_minute_limit": int,
     "resets_at": str, "reason": str | None}
    """
    daily_limit, per_min_limit = get_ai_limits(db, user)
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    minute_start = now - timedelta(seconds=60)

    used_today = db.scalar(
        select(func.count(AiUsage.id))
        .where(AiUsage.user_id == user.id)
        .where(AiUsage.created_at >= today_start)
        .where(AiUsage.status != "error")
    ) or 0

    used_this_minute = db.scalar(
        select(func.count(AiUsage.id))
        .where(AiUsage.user_id == user.id)
        .where(AiUsage.created_at >= minute_start)
        .where(AiUsage.status != "error")
    ) or 0

    tomorrow = (today_start + timedelta(days=1)).isoformat()

    if used_today >= daily_limit:
        return {
            "allowed": False,
            "used_today": used_today,
            "daily_limit": daily_limit,
            "used_this_minute": used_this_minute,
            "per_minute_limit": per_min_limit,
            "resets_at": tomorrow,
            "reason": "daily_limit",
        }

    if used_this_minute >= per_min_limit:
        return {
            "allowed": False,
            "used_today": used_today,
            "daily_limit": daily_limit,
            "used_this_minute": used_this_minute,
            "per_minute_limit": per_min_limit,
            "resets_at": (now + timedelta(seconds=60)).isoformat(),
            "reason": "per_minute_limit",
        }

    return {
        "allowed": True,
        "used_today": used_today,
        "daily_limit": daily_limit,
        "used_this_minute": used_this_minute,
        "per_minute_limit": per_min_limit,
        "resets_at": tomorrow,
        "reason": None,
    }


# ─── Auditoria ────────────────────────────────────────────────────────────────

def record_audit(
    db: Session,
    *,
    user_id: int | None,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    store_id: int | None = None,
    old_values: dict | None = None,
    new_values: dict | None = None,
    metadata: dict | None = None,
) -> None:
    db.add(AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        store_id=store_id,
        old_values=old_values,
        new_values=new_values,
        metadata_=metadata,
    ))
    db.flush()


def record_security_event(
    db: Session,
    *,
    event_type: str,
    severity: str = "medium",
    user_id: int | None = None,
    metadata: dict | None = None,
) -> None:
    db.add(SecurityEvent(
        user_id=user_id,
        event_type=event_type,
        severity=severity,
        metadata_=metadata,
    ))
    db.flush()


# ─── OIDC discovery ───────────────────────────────────────────────────────────

_oidc_config_cache: dict | None = None


def _get_oidc_config() -> dict:
    global _oidc_config_cache
    if _oidc_config_cache is not None:
        return _oidc_config_cache
    discovery_url = OIDC_ISSUER_URL.rstrip("/") + "/.well-known/openid-configuration"
    with httpx.Client(timeout=10) as client:
        resp = client.get(discovery_url)
        resp.raise_for_status()
    _oidc_config_cache = resp.json()
    return _oidc_config_cache


def get_authorization_url(state: str, code_verifier: str) -> str:
    """Gera URL de redirecionamento para o Keycloak com PKCE."""
    import base64
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    cfg = _get_oidc_config()
    params = {
        "response_type": "code",
        "client_id": OIDC_CLIENT_ID,
        "redirect_uri": OIDC_REDIRECT_URI,
        "scope": "openid email profile",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    from urllib.parse import urlencode
    return cfg["authorization_endpoint"] + "?" + urlencode(params)


def exchange_code(code: str, code_verifier: str) -> dict:
    """Troca authorization code por tokens (server-side)."""
    cfg = _get_oidc_config()
    with httpx.Client(timeout=15) as client:
        resp = client.post(
            cfg["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": OIDC_REDIRECT_URI,
                "client_id": OIDC_CLIENT_ID,
                "client_secret": OIDC_CLIENT_SECRET,
                "code_verifier": code_verifier,
            },
        )
        resp.raise_for_status()
    return resp.json()


def get_userinfo(access_token: str) -> dict:
    cfg = _get_oidc_config()
    with httpx.Client(timeout=10) as client:
        resp = client.get(
            cfg["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
    return resp.json()


def get_logout_url(id_token_hint: str | None = None) -> str:
    cfg = _get_oidc_config()
    end_session = cfg.get("end_session_endpoint", "")
    if not end_session:
        return OIDC_POST_LOGOUT_REDIRECT_URI
    from urllib.parse import urlencode
    params: dict[str, str] = {"post_logout_redirect_uri": OIDC_POST_LOGOUT_REDIRECT_URI}
    if id_token_hint:
        params["id_token_hint"] = id_token_hint
    return end_session + "?" + urlencode(params)


# ─── Vinculação de identidade ─────────────────────────────────────────────────

def _grant_bootstrap_admin_if_eligible(db: Session, user: AppUser, email: str) -> bool:
    """Promove o usuário configurado como bootstrap admin, inclusive em logins posteriores.

    Isso permite recuperar o cenário em que a primeira autenticação criou/vinculou
    o usuário como ``pending`` antes de o email de bootstrap ser configurado
    corretamente. A promoção só ocorre enquanto ``bootstrap_admin_granted`` for
    falso; depois disso, desabilitar o usuário continua prevalecendo.
    """
    if (
        not BOOTSTRAP_ADMIN_EMAIL
        or not email
        or email != BOOTSTRAP_ADMIN_EMAIL
        or user.bootstrap_admin_granted
    ):
        return False

    admin_profile = db.scalar(select(Profile).where(Profile.name == "ADMINISTRADOR"))
    if not admin_profile:
        return False

    user.profile_id = admin_profile.id
    user.status = "active"
    user.bootstrap_admin_granted = True
    user.updated_at = datetime.utcnow()
    record_audit(
        db,
        user_id=user.id,
        action="BOOTSTRAP_ADMIN_GRANTED",
        entity_type="app_user",
        entity_id=str(user.id),
        metadata={"email": email},
    )
    return True


def _sync_user_from_oidc(db: Session, user: AppUser, identity: OidcIdentity, *, email: str, display_name: str) -> None:
    """Sincroniza metadados não sensíveis da identidade já vinculada.

    O ``issuer+subject`` continua sendo a âncora da identidade. Se o email mudar
    no provedor DEV/corporativo, atualizamos o cadastro local somente quando não
    houver colisão com outro usuário.
    """
    identity.last_seen_at = datetime.utcnow()
    if email:
        identity.email_at_link = email
        if user.email != email:
            conflict = db.scalar(
                select(AppUser).where(AppUser.email == email, AppUser.id != user.id)
            )
            if conflict is None:
                user.email = email
    if display_name and user.display_name != display_name:
        user.display_name = display_name
    user.last_seen_at = datetime.utcnow()


def resolve_or_create_user(db: Session, userinfo: dict) -> AppUser | None:
    """Resolve/vincula a identidade OIDC e aplica o bootstrap admin.

    1. Procura ``oidc_identity`` por issuer+subject.
    2. Se existir, sincroniza email/nome e reaplica a regra de bootstrap caso
       ainda não tenha sido concedida.
    3. Se não existir, procura usuário pelo email; se necessário cria ``pending``.
    4. Vincula a identidade e concede bootstrap quando elegível.
    """
    issuer = userinfo.get("iss", OIDC_ISSUER_URL)
    subject = userinfo.get("sub", "")
    email = (userinfo.get("email") or "").strip().lower()
    display_name = userinfo.get("name") or userinfo.get("preferred_username") or email

    if not subject:
        return None

    # 1. Identidade existente: não retornar cedo antes de avaliar bootstrap.
    identity = db.scalar(
        select(OidcIdentity)
        .where(OidcIdentity.issuer == issuer)
        .where(OidcIdentity.subject == subject)
    )
    if identity:
        user = db.get(AppUser, identity.user_id)
        if user is None:
            return None
        _sync_user_from_oidc(db, user, identity, email=email, display_name=display_name)
        _grant_bootstrap_admin_if_eligible(db, user, email)
        db.commit()
        db.refresh(user)
        return user

    # 2. Usuário por email
    user = db.scalar(select(AppUser).where(AppUser.email == email)) if email else None

    # 3. Criar usuário se não existir
    if not user:
        if not email:
            return None
        user = AppUser(
            email=email,
            display_name=display_name,
            status="pending",
        )
        db.add(user)
        db.flush()
    else:
        if display_name:
            user.display_name = display_name
        user.last_seen_at = datetime.utcnow()

    _grant_bootstrap_admin_if_eligible(db, user, email)

    # 4. Vincular identidade
    new_identity = OidcIdentity(
        user_id=user.id,
        issuer=issuer,
        subject=subject,
        email_at_link=email,
        created_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
    )
    db.add(new_identity)
    db.commit()
    db.refresh(user)
    return user
