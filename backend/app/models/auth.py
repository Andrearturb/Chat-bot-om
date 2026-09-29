"""
Modelos de autenticação, autorização, sessões e auditoria.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# ─── Perfis ───────────────────────────────────────────────────────────────────

class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Limites padrão de IA associados ao perfil
    ai_daily_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    ai_per_minute_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    permissions: Mapped[list["ProfilePermission"]] = relationship(
        "ProfilePermission", back_populates="profile", cascade="all, delete-orphan"
    )
    users: Mapped[list["AppUser"]] = relationship("AppUser", back_populates="profile")


# ─── Permissões ───────────────────────────────────────────────────────────────

class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    profile_permissions: Mapped[list["ProfilePermission"]] = relationship(
        "ProfilePermission", back_populates="permission"
    )
    user_overrides: Mapped[list["UserPermissionOverride"]] = relationship(
        "UserPermissionOverride", back_populates="permission"
    )


class ProfilePermission(Base):
    __tablename__ = "profile_permissions"
    __table_args__ = (UniqueConstraint("profile_id", "permission_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    permission_id: Mapped[int] = mapped_column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)

    profile: Mapped["Profile"] = relationship("Profile", back_populates="permissions")
    permission: Mapped["Permission"] = relationship("Permission", back_populates="profile_permissions")


# ─── Usuário da aplicação ─────────────────────────────────────────────────────

class AppUser(Base):
    __tablename__ = "app_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    profile_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("profiles.id"), nullable=True)
    # pending | active | disabled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    access_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ai_daily_limit_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_per_minute_limit_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # flag: bootstrap admin já foi concedido uma única vez
    bootstrap_admin_granted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    profile: Mapped["Profile | None"] = relationship("Profile", back_populates="users")
    oidc_identities: Mapped[list["OidcIdentity"]] = relationship(
        "OidcIdentity", back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["UserSession"]] = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )
    permission_overrides: Mapped[list["UserPermissionOverride"]] = relationship(
        "UserPermissionOverride", back_populates="user", cascade="all, delete-orphan"
    )


# ─── Identidade OIDC ──────────────────────────────────────────────────────────

class OidcIdentity(Base):
    __tablename__ = "oidc_identities"
    __table_args__ = (UniqueConstraint("issuer", "subject"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    issuer: Mapped[str] = mapped_column(String(512), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    email_at_link: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["AppUser"] = relationship("AppUser", back_populates="oidc_identities")


# ─── Sessões ──────────────────────────────────────────────────────────────────

class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (Index("ix_user_sessions_token_hash", "session_token_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    # Hash SHA-256 do token opaco — nunca o token em texto puro
    session_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_secret: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)        # idle expiry
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped["AppUser"] = relationship("AppUser", back_populates="sessions")


# ─── Overrides de permissão ───────────────────────────────────────────────────

class UserPermissionOverride(Base):
    __tablename__ = "user_permission_overrides"
    __table_args__ = (UniqueConstraint("user_id", "permission_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    permission_id: Mapped[int] = mapped_column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)
    # "allow" ou "deny"
    effect: Mapped[str] = mapped_column(Enum("allow", "deny", name="override_effect"), nullable=False)

    user: Mapped["AppUser"] = relationship("AppUser", back_populates="permission_overrides")
    permission: Mapped["Permission"] = relationship("Permission", back_populates="user_overrides")


# ─── Conversas ────────────────────────────────────────────────────────────────

class AssistantConversation(Base):
    __tablename__ = "assistant_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)   # UUID
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False, index=True)
    n8n_session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="Nova conversa")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    messages: Mapped[list["AssistantMessage"]] = relationship(
        "AssistantMessage", back_populates="conversation", cascade="all, delete-orphan"
    )


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)   # UUID
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(Enum("user", "assistant", name="message_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    response_time: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    conversation: Mapped["AssistantConversation"] = relationship("AssistantConversation", back_populates="messages")


# ─── Uso da IA ────────────────────────────────────────────────────────────────

class AiUsage(Base):
    __tablename__ = "ai_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("assistant_conversations.id", ondelete="SET NULL"), nullable=True)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # pending | success | error
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_chars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_chars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)


# ─── Auditoria ────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("app_users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    store_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    old_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)


# ─── Eventos de segurança ─────────────────────────────────────────────────────

class SecurityEvent(Base):
    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("app_users.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    # low | medium | high | critical
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)
