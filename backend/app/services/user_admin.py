"""
Gestão administrativa de usuários do Chat-bot O&M.

Divisão de responsabilidades:
- Keycloak: identidade, login, senha e credenciais (via Admin API, server-side);
- PostgreSQL: perfil, status e dados complementares da aplicação.

Cadastro (saga com compensação):
    Keycloak (cria conta) → subject → app_users → oidc_identities
Se a gravação local falhar, a conta recém-criada no Keycloak é removida. Uma
conta já existente no Keycloak (mesmo usuário e mesmo e-mail) e ainda não
vinculada é *adotada* em vez de duplicada — isso torna a operação idempotente
e permite repetir um cadastro interrompido.

Senhas nunca são persistidas, registradas em log ou devolvidas pela API.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import BOOTSTRAP_ADMIN_EMAIL
from app.models.auth import AppUser, OidcIdentity, Profile
from app.services.auth import (
    PROFILE_NAMES,
    check_user_active,
    get_user_permissions,
    oidc_issuer,
    record_audit,
    revoke_user_sessions,
)
from app.services.keycloak_admin import IdentityAdminError, KeycloakAdminClient

logger = logging.getLogger(__name__)

ADMIN_PROFILE = "ADMINISTRADOR"
PROFILE_ORDER = list(PROFILE_NAMES.keys())
MANAGEABLE_STATUSES = ("active", "disabled")
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

# Usuários fixos do Keycloak DEV → perfil esperado no aplicativo.
DEV_USERS: tuple[tuple[str, str], ...] = (
    ("admin.om", "ADMINISTRADOR"),
    ("analista.om", "ANALISTA"),
    ("gerente.om", "GERENTE"),
    ("diretor.om", "DIRETOR"),
    ("convidado.om", "CONVIDADO"),
)

_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}[a-z0-9]$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")
# Mesmos caracteres recusados pelo validador de nomes do Keycloak.
_PROHIBITED_NAME_CHARS = set('<>&"$%!#?§;*~/\\|^=[]{}()')


class UserAdminError(Exception):
    """Erro de regra de negócio com mensagem segura para o administrador."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        code: str = "invalid_request",
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.extra = extra or {}

    @classmethod
    def from_identity(cls, exc: IdentityAdminError) -> "UserAdminError":
        return cls(exc.message, status_code=exc.status_code, code=exc.code)


@dataclass
class OperationResult:
    user: AppUser
    warnings: list[str] = field(default_factory=list)


# ─── Normalização e validação ─────────────────────────────────────────────────

def normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def validate_email(value: str | None) -> str:
    email = normalize_email(value)
    if not email or len(email) > 254 or not _EMAIL_RE.match(email):
        raise UserAdminError("Informe um e-mail válido.", status_code=422, code="invalid_email")
    return email


def username_from_email(email: str) -> str:
    local = normalize_email(email).split("@", 1)[0]
    local = unicodedata.normalize("NFKD", local).encode("ascii", "ignore").decode()
    local = re.sub(r"[^a-z0-9._-]+", ".", local)
    local = re.sub(r"[._-]{2,}", ".", local).strip("._-")
    return local[:64]


def validate_username(value: str | None) -> str:
    username = (value or "").strip().lower()
    if not _USERNAME_RE.match(username):
        raise UserAdminError(
            "O usuário deve ter de 2 a 64 caracteres: letras minúsculas, números, ponto, hífen ou sublinhado.",
            status_code=422,
            code="invalid_username",
        )
    return username


def validate_display_name(value: str | None) -> str:
    name = " ".join((value or "").split())
    if len(name) < 3 or len(name) > 200:
        raise UserAdminError("Informe o nome completo.", status_code=422, code="invalid_name")
    if len(name.split(" ")) < 2:
        raise UserAdminError("Informe nome e sobrenome.", status_code=422, code="invalid_name")
    if any(ch in _PROHIBITED_NAME_CHARS or ord(ch) < 32 for ch in name):
        raise UserAdminError("O nome contém caracteres não permitidos.", status_code=422, code="invalid_name")
    return name


def split_name(display_name: str) -> tuple[str, str]:
    first, _, last = display_name.partition(" ")
    return first, last.strip()


def validate_temporary_password(password: str | None, *, username: str = "", email: str = "") -> str:
    value = password or ""
    if len(value) < PASSWORD_MIN_LENGTH:
        raise UserAdminError(
            f"A senha temporária deve ter pelo menos {PASSWORD_MIN_LENGTH} caracteres.",
            status_code=422, code="invalid_password",
        )
    if len(value) > PASSWORD_MAX_LENGTH:
        raise UserAdminError("A senha temporária é longa demais.", status_code=422, code="invalid_password")
    lowered = value.lower()
    if (username and lowered == username.lower()) or (email and lowered == email.lower()):
        raise UserAdminError("A senha não pode ser igual ao usuário ou ao e-mail.", status_code=422, code="invalid_password")
    return value


def _validate_status(value: str) -> str:
    if value not in MANAGEABLE_STATUSES:
        raise UserAdminError("Status inválido. Use ativo ou bloqueado.", status_code=422, code="invalid_status")
    return value


def _get_profile(db: Session, name: str | None) -> Profile:
    profile = db.scalar(select(Profile).where(Profile.name == (name or "").strip().upper()))
    if profile is None:
        raise UserAdminError("Selecione um perfil válido.", status_code=422, code="invalid_profile")
    return profile


# ─── Consultas ────────────────────────────────────────────────────────────────

def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    text = value.isoformat()
    # Datas são gravadas em UTC sem fuso; explicita o "Z" para o navegador.
    return text + "Z" if value.tzinfo is None else text


def identity_for(db: Session, user: AppUser) -> OidcIdentity | None:
    return db.scalar(
        select(OidcIdentity)
        .where(OidcIdentity.user_id == user.id)
        .where(OidcIdentity.issuer == oidc_issuer())
        .order_by(OidcIdentity.id.desc())
    )


def _is_effective_admin(db: Session, user: AppUser) -> bool:
    ok, _ = check_user_active(user)
    if not ok:
        return False
    profile = db.get(Profile, user.profile_id) if user.profile_id else None
    if profile is None or profile.name != ADMIN_PROFILE:
        return False
    return "users.manage" in get_user_permissions(db, user)


def active_admin_ids(db: Session) -> set[int]:
    """Administradores ativos que efetivamente conseguem gerir usuários."""
    admin_profile = db.scalar(select(Profile).where(Profile.name == ADMIN_PROFILE))
    if admin_profile is None:
        return set()
    candidates = db.scalars(
        select(AppUser)
        .where(AppUser.profile_id == admin_profile.id)
        .where(AppUser.status == "active")
    ).all()
    return {user.id for user in candidates if _is_effective_admin(db, user)}


def serialize_user(
    db: Session,
    user: AppUser,
    *,
    actor_id: int | None = None,
    identity: OidcIdentity | None = None,
    identity_known: bool = False,
) -> dict[str, Any]:
    profile = db.get(Profile, user.profile_id) if user.profile_id else None
    if not identity_known:
        identity = identity_for(db, user)
    daily = user.ai_daily_limit_override if user.ai_daily_limit_override is not None else (
        profile.ai_daily_limit if profile else None
    )
    per_minute = user.ai_per_minute_limit_override if user.ai_per_minute_limit_override is not None else (
        profile.ai_per_minute_limit if profile else None
    )
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "display_name": user.display_name,
        "profile": profile.name if profile else None,
        "profile_display": profile.display_name if profile else None,
        "status": user.status,
        "last_seen_at": _iso(user.last_seen_at),
        "created_at": _iso(user.created_at),
        "updated_at": _iso(user.updated_at),
        "access_expires_at": _iso(user.access_expires_at),
        "ai_daily_limit": daily,
        "ai_per_minute_limit": per_minute,
        "identity_linked": identity is not None,
        "is_self": actor_id is not None and actor_id == user.id,
    }


def list_users(
    db: Session,
    *,
    actor_id: int | None = None,
    q: str | None = None,
    status: str | None = None,
    profile: str | None = None,
) -> list[dict[str, Any]]:
    query = select(AppUser)
    if status:
        query = query.where(AppUser.status == status)
    if profile:
        query = query.join(Profile, Profile.id == AppUser.profile_id).where(Profile.name == profile.strip().upper())
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        query = query.where(or_(
            func.lower(AppUser.display_name).like(term),
            func.lower(AppUser.email).like(term),
            func.lower(func.coalesce(AppUser.username, "")).like(term),
        ))
    query = query.order_by(func.lower(AppUser.display_name), AppUser.email)
    users = db.scalars(query).all()

    identities: dict[int, OidcIdentity] = {}
    if users:
        rows = db.scalars(
            select(OidcIdentity)
            .where(OidcIdentity.issuer == oidc_issuer())
            .where(OidcIdentity.user_id.in_([u.id for u in users]))
        ).all()
        for row in rows:
            identities[row.user_id] = row

    return [
        serialize_user(db, user, actor_id=actor_id, identity=identities.get(user.id), identity_known=True)
        for user in users
    ]


def list_profiles(db: Session) -> list[dict[str, str]]:
    profiles = db.scalars(select(Profile)).all()
    order = {name: index for index, name in enumerate(PROFILE_ORDER)}
    profiles = sorted(profiles, key=lambda p: (order.get(p.name, len(order)), p.name))
    return [{"name": p.name, "display_name": p.display_name} for p in profiles]


# ─── Cadastro ─────────────────────────────────────────────────────────────────

def create_user(
    db: Session,
    idp: KeycloakAdminClient,
    actor: AppUser,
    *,
    display_name: str,
    email: str,
    username: str | None,
    profile_name: str,
    status: str = "active",
    password_mode: str = "temporary",
    temporary_password: str | None = None,
) -> OperationResult:
    display_name = validate_display_name(display_name)
    email = validate_email(email)
    username = validate_username(username or username_from_email(email))
    profile = _get_profile(db, profile_name)
    status = _validate_status(status or "active")
    if password_mode not in ("temporary", "email"):
        raise UserAdminError("Forma de acesso inicial inválida.", status_code=422, code="invalid_password_mode")

    if not idp.is_configured():
        raise UserAdminError(
            "A integração com o provedor de identidade não está configurada. Não é possível cadastrar usuários.",
            status_code=503, code="identity_admin_not_configured",
        )

    password = None
    if password_mode == "temporary":
        password = validate_temporary_password(temporary_password, username=username, email=email)

    issuer = oidc_issuer()
    warnings: list[str] = []

    # 1. Conflitos locais — sem efeitos colaterais.
    existing_app = db.scalar(select(AppUser).where(func.lower(AppUser.email) == email))
    if existing_app is not None and identity_for(db, existing_app) is not None:
        raise UserAdminError(
            "Já existe um usuário cadastrado com este e-mail.",
            status_code=409, code="user_exists", extra={"user_id": existing_app.id},
        )

    try:
        if password_mode == "email" and not idp.smtp_configured():
            raise UserAdminError(
                "O envio de e-mails ainda não está configurado no provedor de identidade. Defina uma senha temporária.",
                status_code=409, code="email_not_configured",
            )

        # 2. Conta no Keycloak: reaproveita somente a mesma pessoa (usuário + e-mail).
        by_username = idp.find_by_username(username)
        by_email = idp.find_by_email(email)
        if by_username and by_email and by_username.id != by_email.id:
            raise UserAdminError(
                "O usuário e o e-mail informados pertencem a contas diferentes no provedor de identidade.",
                status_code=409, code="identity_conflict",
            )
        if by_username and not by_email:
            raise UserAdminError(
                f"O nome de usuário “{username}” já está em uso.",
                status_code=409, code="username_taken",
            )
        if by_email and not by_username:
            raise UserAdminError(
                "Este e-mail já está vinculado a outra conta no provedor de identidade.",
                status_code=409, code="email_taken",
            )

        first_name, last_name = split_name(display_name)
        created_in_idp = False
        if by_username is not None:
            subject = by_username.id
            linked = db.scalar(
                select(OidcIdentity)
                .where(OidcIdentity.issuer == issuer)
                .where(OidcIdentity.subject == subject)
            )
            if linked is not None:
                raise UserAdminError(
                    "Este usuário já está cadastrado no Chat-bot O&M.",
                    status_code=409, code="user_exists", extra={"user_id": linked.user_id},
                )
            # Conta órfã (ex.: cadastro anterior interrompido) — adota sem duplicar.
            idp.update_user(subject, first_name=first_name, last_name=last_name, enabled=status == "active")
            if password:
                idp.set_temporary_password(subject, password)
        else:
            subject = idp.create_user(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                enabled=status == "active",
                temporary_password=password,
                required_actions=["UPDATE_PASSWORD"] if password_mode == "email" else [],
            )
            created_in_idp = True
    except IdentityAdminError as exc:
        raise UserAdminError.from_identity(exc) from None

    # 3. Aplicação: app_users + oidc_identities na mesma transação.
    now = datetime.utcnow()
    try:
        user = existing_app or AppUser(email=email, created_at=now)
        user.email = email
        user.username = username
        user.display_name = display_name
        user.profile_id = profile.id
        user.status = status
        user.updated_at = now
        if existing_app is None:
            db.add(user)
        db.flush()
        db.add(OidcIdentity(
            user_id=user.id,
            issuer=issuer,
            subject=subject,
            email_at_link=email,
            created_at=now,
        ))
        record_audit(
            db,
            user_id=actor.id,
            action="USER_CREATE",
            entity_type="app_user",
            entity_id=str(user.id),
            new_values={
                "email": email,
                "username": username,
                "profile": profile.name,
                "status": status,
                "password_mode": password_mode,
            },
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001 — compensação obrigatória
        db.rollback()
        logger.error("Cadastro de usuário: falha ao gravar no banco (%s).", type(exc).__name__)
        if created_in_idp:
            try:
                idp.delete_user(subject)
            except IdentityAdminError:
                logger.error(
                    "Cadastro de usuário: não foi possível remover a conta criada no Keycloak "
                    "(username=%s). Repetir o cadastro reaproveita a conta sem duplicar.",
                    username,
                )
        raise UserAdminError(
            "Não foi possível concluir o cadastro. Nenhuma alteração foi mantida; tente novamente.",
            status_code=500, code="create_failed",
        ) from None

    if password_mode == "email":
        try:
            idp.send_update_password_email(subject)
        except IdentityAdminError:
            warnings.append(
                "O usuário foi criado, mas o e-mail para definir a senha não pôde ser enviado. "
                "Use “Redefinir senha” para definir uma senha temporária."
            )

    db.refresh(user)
    return OperationResult(user, warnings)


# ─── Edição / status ──────────────────────────────────────────────────────────

def update_user(
    db: Session,
    idp: KeycloakAdminClient,
    actor: AppUser,
    user: AppUser,
    *,
    display_name: str | None = None,
    profile_name: str | None = None,
    status: str | None = None,
) -> OperationResult:
    warnings: list[str] = []
    current_profile = db.get(Profile, user.profile_id) if user.profile_id else None

    new_name = validate_display_name(display_name) if display_name is not None else user.display_name
    new_profile = _get_profile(db, profile_name) if profile_name is not None else current_profile
    new_status = _validate_status(status) if status is not None else user.status

    name_changed = new_name != user.display_name
    profile_changed = (new_profile.id if new_profile else None) != user.profile_id
    status_changed = new_status != user.status
    if not (name_changed or profile_changed or status_changed):
        return OperationResult(user, warnings)

    # ── Proteções ────────────────────────────────────────────────────────────
    if user.id == actor.id and new_status != "active":
        raise UserAdminError("Você não pode desativar a sua própria conta.", status_code=409, code="self_disable")
    if new_status == "active" and new_profile is None:
        raise UserAdminError("Selecione um perfil para liberar o acesso deste usuário.", status_code=422, code="profile_required")

    admins = active_admin_ids(db)
    will_be_admin = new_status == "active" and new_profile is not None and new_profile.name == ADMIN_PROFILE
    if user.id in admins and not will_be_admin and not (admins - {user.id}):
        raise UserAdminError(
            "É necessário manter pelo menos um administrador ativo. "
            "Defina outro administrador antes de alterar este usuário.",
            status_code=409, code="last_admin",
        )

    identity = identity_for(db, user)
    subject = identity.subject if identity else None
    sync_idp = subject is not None and idp.is_configured()
    activating = status_changed and new_status == "active"
    disabling = status_changed and new_status == "disabled"

    # 1. Provedor primeiro quando a mudança local depende dele (nome/reativação).
    if sync_idp and (name_changed or activating):
        first_name, last_name = split_name(new_name) if name_changed else (None, None)
        try:
            idp.update_user(
                subject,
                first_name=first_name,
                last_name=last_name,
                enabled=True if activating else None,
            )
        except IdentityAdminError as exc:
            raise UserAdminError.from_identity(exc) from None
    elif name_changed and subject is not None:
        warnings.append(
            "O nome foi alterado apenas no Chat-bot O&M; o provedor de identidade pode sobrescrevê-lo no próximo acesso."
        )

    # 2. Aplicação.
    now = datetime.utcnow()
    if name_changed:
        record_audit(db, user_id=actor.id, action="USER_UPDATE", entity_type="app_user", entity_id=str(user.id),
                     old_values={"display_name": user.display_name}, new_values={"display_name": new_name})
        user.display_name = new_name
    if profile_changed:
        record_audit(db, user_id=actor.id, action="USER_ROLE_CHANGE", entity_type="app_user", entity_id=str(user.id),
                     old_values={"profile": current_profile.name if current_profile else None},
                     new_values={"profile": new_profile.name if new_profile else None})
        user.profile_id = new_profile.id if new_profile else None
    if status_changed:
        record_audit(db, user_id=actor.id, action="USER_ACTIVATE" if activating else "USER_DISABLE",
                     entity_type="app_user", entity_id=str(user.id),
                     old_values={"status": user.status}, new_values={"status": new_status})
        user.status = new_status
        if disabling:
            revoke_user_sessions(db, user.id)
    user.updated_at = now
    db.commit()

    # 3. Bloqueio no provedor: best-effort, pois o acesso já está bloqueado no app.
    if disabling and sync_idp:
        try:
            idp.update_user(subject, enabled=False)
            idp.logout_user(subject)
        except IdentityAdminError:
            warnings.append(
                "O acesso foi bloqueado no Chat-bot O&M, mas não foi possível desativar a conta no provedor de identidade."
            )

    db.refresh(user)
    return OperationResult(user, warnings)


def reset_password(
    db: Session,
    idp: KeycloakAdminClient,
    actor: AppUser,
    user: AppUser,
    *,
    temporary_password: str | None,
) -> OperationResult:
    identity = identity_for(db, user)
    if identity is None or not idp.is_configured():
        raise UserAdminError(
            "Este usuário não possui conta vinculada ao provedor de identidade.",
            status_code=409, code="identity_not_linked",
        )
    password = validate_temporary_password(temporary_password, username=user.username or "", email=user.email)
    try:
        idp.set_temporary_password(identity.subject, password)
    except IdentityAdminError as exc:
        raise UserAdminError.from_identity(exc) from None

    revoked = revoke_user_sessions(db, user.id)
    record_audit(db, user_id=actor.id, action="USER_PASSWORD_RESET", entity_type="app_user",
                 entity_id=str(user.id), metadata={"temporary": True, "sessions_revoked": revoked})
    db.commit()

    warnings: list[str] = []
    try:
        idp.logout_user(identity.subject)
    except IdentityAdminError:
        warnings.append("A senha foi redefinida, mas não foi possível encerrar as sessões abertas no provedor de identidade.")
    db.refresh(user)
    return OperationResult(user, warnings)


def send_password_email(db: Session, idp: KeycloakAdminClient, actor: AppUser, user: AppUser) -> OperationResult:
    identity = identity_for(db, user)
    if identity is None or not idp.is_configured():
        raise UserAdminError(
            "Este usuário não possui conta vinculada ao provedor de identidade.",
            status_code=409, code="identity_not_linked",
        )
    try:
        if not idp.smtp_configured():
            raise UserAdminError(
                "O envio de e-mails ainda não está configurado no provedor de identidade.",
                status_code=409, code="email_not_configured",
            )
        idp.send_update_password_email(identity.subject)
    except IdentityAdminError as exc:
        raise UserAdminError.from_identity(exc) from None

    record_audit(db, user_id=actor.id, action="USER_PASSWORD_EMAIL", entity_type="app_user",
                 entity_id=str(user.id), metadata={"required_action": "UPDATE_PASSWORD"})
    db.commit()
    return OperationResult(user, [])


# ─── Pré-provisionamento DEV ──────────────────────────────────────────────────

def provision_dev_users(db: Session, idp: KeycloakAdminClient) -> list[str]:
    """Vincula os usuários fixos do Keycloak DEV ao aplicativo. Idempotente.

    - cria ``app_users`` ativos com o perfil esperado e a ``oidc_identity``
      (issuer + subject do Keycloak) — o primeiro login não depende de aprovação;
    - usuários ainda ``pending`` são liberados com o perfil esperado;
    - perfil/status alterados por um administrador são preservados.
    """
    if not idp.is_configured():
        return ["Keycloak Admin API não configurada — provisionamento DEV ignorado."]

    issuer = oidc_issuer()
    summary: list[str] = []
    now = datetime.utcnow()

    for username, profile_name in DEV_USERS:
        account = idp.find_by_username(username)
        if account is None or not account.email:
            summary.append(f"{username}: não encontrado no Keycloak")
            continue
        profile = db.scalar(select(Profile).where(Profile.name == profile_name))
        if profile is None:
            summary.append(f"{username}: perfil {profile_name} inexistente")
            continue

        email = account.email.lower()
        identity = db.scalar(
            select(OidcIdentity)
            .where(OidcIdentity.issuer == issuer)
            .where(OidcIdentity.subject == account.id)
        )
        user = db.get(AppUser, identity.user_id) if identity else None
        if user is None:
            user = db.scalar(select(AppUser).where(func.lower(AppUser.email) == email))

        action = "vinculado"
        if user is None:
            user = AppUser(email=email, display_name=account.full_name or username,
                           status="active", profile_id=profile.id, created_at=now)
            db.add(user)
            db.flush()
            action = "criado"
        elif user.status == "pending":
            user.status = "active"
            user.profile_id = profile.id
            action = "liberado"
        elif user.profile_id is None:
            user.profile_id = profile.id

        if user.email != email and db.scalar(
            select(AppUser).where(func.lower(AppUser.email) == email, AppUser.id != user.id)
        ) is None:
            user.email = email
        user.username = username
        if not user.display_name:
            user.display_name = account.full_name or username
        if profile_name == ADMIN_PROFILE and BOOTSTRAP_ADMIN_EMAIL and email == BOOTSTRAP_ADMIN_EMAIL:
            user.bootstrap_admin_granted = True
        user.updated_at = now

        if identity is None:
            db.add(OidcIdentity(user_id=user.id, issuer=issuer, subject=account.id,
                                email_at_link=email, created_at=now))
            if action == "vinculado":
                action = "identidade vinculada"
        if action in ("criado", "liberado", "identidade vinculada"):
            record_audit(db, user_id=None, action="USER_PROVISIONED_DEV", entity_type="app_user",
                         entity_id=str(user.id), new_values={"username": username, "profile": profile_name, "result": action})
        summary.append(f"{username}: {action}")

    db.commit()
    return summary
