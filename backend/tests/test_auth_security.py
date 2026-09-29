"""
Testes de autenticação, sessão, CSRF, permissões, overrides,
controle de IA, conversas e isolamento — SQLite in-memory.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.auth import (
    AiUsage, AppUser, AssistantConversation, AuditLog,
    Permission, Profile, ProfilePermission, SecurityEvent,
    UserPermissionOverride, UserSession,
)
from app.services.auth import (
    check_ai_rate_limit, check_user_active, create_session,
    get_session, get_user_permissions, record_audit,
    record_security_event, resolve_or_create_user,
    revoke_session, seed_profiles_and_permissions,
)


def _sha256(v): return hashlib.sha256(v.encode()).hexdigest()


def _make_profile(db, name, perms, ai_daily=50, ai_per_min=5):
    p = Profile(name=name, display_name=name, ai_daily_limit=ai_daily, ai_per_minute_limit=ai_per_min)
    db.add(p); db.flush()
    for code in perms:
        perm = db.scalar(select(Permission).where(Permission.code == code))
        if not perm:
            perm = Permission(code=code, description=code); db.add(perm); db.flush()
        db.add(ProfilePermission(profile_id=p.id, permission_id=perm.id))
    db.flush(); return p


def _make_user(db, email, profile=None, status="active"):
    u = AppUser(email=email, display_name=email.split("@")[0],
                profile_id=profile.id if profile else None, status=status)
    db.add(u); db.flush(); return u


def _make_session(db, user):
    token = create_session(db, user.id)
    session = db.scalar(select(UserSession).where(UserSession.session_token_hash == _sha256(token)))
    return token, session


# ── Seed ──────────────────────────────────────────────────────────────────────

def test_seed_idempotente(db):
    seed_profiles_and_permissions(db)
    seed_profiles_and_permissions(db)
    assert db.scalar(select(Profile).where(Profile.name == "ADMINISTRADOR")) is not None


# ── Sessão ────────────────────────────────────────────────────────────────────

def test_token_armazenado_como_hash(db):
    p = _make_profile(db, "T1", []); u = _make_user(db, "t1@t.com", p)
    token, s = _make_session(db, u)
    assert s.session_token_hash != token
    assert s.session_token_hash == _sha256(token)

def test_get_session_valida(db):
    p = _make_profile(db, "T2", []); u = _make_user(db, "t2@t.com", p)
    token, _ = _make_session(db, u)
    assert get_session(db, token) is not None

def test_get_session_token_invalido(db):
    assert get_session(db, "token_falso") is None

def test_sessao_expirada_idle(db):
    p = _make_profile(db, "T3", []); u = _make_user(db, "t3@t.com", p)
    token, s = _make_session(db, u)
    s.expires_at = datetime.utcnow() - timedelta(minutes=1); db.commit()
    assert get_session(db, token) is None

def test_sessao_expirada_absoluto(db):
    p = _make_profile(db, "T4", []); u = _make_user(db, "t4@t.com", p)
    token, s = _make_session(db, u)
    s.absolute_expires_at = datetime.utcnow() - timedelta(minutes=1); db.commit()
    assert get_session(db, token) is None

def test_logout_revoga_sessao(db):
    p = _make_profile(db, "T5", []); u = _make_user(db, "t5@t.com", p)
    token, _ = _make_session(db, u)
    revoke_session(db, token)
    assert get_session(db, token) is None


# ── Usuário ───────────────────────────────────────────────────────────────────

def test_pending_bloqueado(db):
    u = _make_user(db, "p@t.com", status="pending")
    ok, r = check_user_active(u); assert not ok; assert "pendente" in r.lower()

def test_disabled_bloqueado(db):
    u = _make_user(db, "d@t.com", status="disabled")
    ok, r = check_user_active(u); assert not ok; assert "desativada" in r.lower()

def test_ativo_ok(db):
    u = _make_user(db, "a@t.com", status="active")
    ok, _ = check_user_active(u); assert ok

def test_expirado_bloqueado(db):
    u = _make_user(db, "e@t.com", status="active")
    u.access_expires_at = datetime.utcnow() - timedelta(hours=1); db.commit()
    ok, r = check_user_active(u); assert not ok; assert "expirou" in r.lower()


# ── Permissões ────────────────────────────────────────────────────────────────

def test_perfil_analista(db):
    seed_profiles_and_permissions(db)
    p = db.scalar(select(Profile).where(Profile.name == "ANALISTA"))
    u = _make_user(db, "an@t.com", p)
    perms = get_user_permissions(db, u)
    assert "assets.create" in perms
    assert "assets.delete" not in perms
    assert "audit.view" not in perms
    assert "users.manage" not in perms

def test_perfil_gerente(db):
    seed_profiles_and_permissions(db)
    p = db.scalar(select(Profile).where(Profile.name == "GERENTE"))
    u = _make_user(db, "ge@t.com", p)
    perms = get_user_permissions(db, u)
    assert "assets.delete" in perms
    assert "audit.view" in perms
    assert "users.manage" not in perms

def test_perfil_diretor(db):
    seed_profiles_and_permissions(db)
    p = db.scalar(select(Profile).where(Profile.name == "DIRETOR"))
    u = _make_user(db, "di@t.com", p)
    perms = get_user_permissions(db, u)
    assert "assets.view" in perms
    assert "assets.create" not in perms

def test_perfil_convidado(db):
    seed_profiles_and_permissions(db)
    p = db.scalar(select(Profile).where(Profile.name == "CONVIDADO"))
    u = _make_user(db, "co@t.com", p)
    perms = get_user_permissions(db, u)
    assert "assets.view" in perms
    assert "documents.view" not in perms

def test_perfil_admin(db):
    seed_profiles_and_permissions(db)
    p = db.scalar(select(Profile).where(Profile.name == "ADMINISTRADOR"))
    u = _make_user(db, "ad@t.com", p)
    perms = get_user_permissions(db, u)
    assert "users.manage" in perms
    assert "settings.manage" in perms
    assert "sync.tape" in perms


# ── Overrides ─────────────────────────────────────────────────────────────────

def test_override_allow(db):
    seed_profiles_and_permissions(db)
    p = db.scalar(select(Profile).where(Profile.name == "ANALISTA"))
    u = _make_user(db, "ova@t.com", p)
    assert "assets.import" not in get_user_permissions(db, u)
    perm = db.scalar(select(Permission).where(Permission.code == "assets.import"))
    db.add(UserPermissionOverride(user_id=u.id, permission_id=perm.id, effect="allow")); db.commit()
    assert "assets.import" in get_user_permissions(db, u)

def test_override_deny(db):
    seed_profiles_and_permissions(db)
    p = db.scalar(select(Profile).where(Profile.name == "ANALISTA"))
    u = _make_user(db, "ovd@t.com", p)
    assert "assets.edit" in get_user_permissions(db, u)
    perm = db.scalar(select(Permission).where(Permission.code == "assets.edit"))
    db.add(UserPermissionOverride(user_id=u.id, permission_id=perm.id, effect="deny")); db.commit()
    assert "assets.edit" not in get_user_permissions(db, u)

def test_deny_prevalece(db):
    seed_profiles_and_permissions(db)
    p = db.scalar(select(Profile).where(Profile.name == "ANALISTA"))
    u = _make_user(db, "ovd2@t.com", p)
    assert "assets.view" in get_user_permissions(db, u)
    perm = db.scalar(select(Permission).where(Permission.code == "assets.view"))
    db.add(UserPermissionOverride(user_id=u.id, permission_id=perm.id, effect="deny")); db.commit()
    assert "assets.view" not in get_user_permissions(db, u)


# ── Controle de IA ────────────────────────────────────────────────────────────

def test_limite_diario_permitido(db):
    p = _make_profile(db, "IA1", [], ai_daily=5, ai_per_min=2)
    u = _make_user(db, "ia1@t.com", p)
    r = check_ai_rate_limit(db, u)
    assert r["allowed"] is True and r["daily_limit"] == 5

def test_limite_diario_atingido(db):
    p = _make_profile(db, "IA2", [], ai_daily=2, ai_per_min=5)
    u = _make_user(db, "ia2@t.com", p)
    for _ in range(2):
        db.add(AiUsage(user_id=u.id, request_id=secrets.token_hex(8),
                       status="success", created_at=datetime.utcnow()))
    db.commit()
    r = check_ai_rate_limit(db, u)
    assert r["allowed"] is False and r["reason"] == "daily_limit"

def test_limite_por_minuto(db):
    p = _make_profile(db, "IA3", [], ai_daily=100, ai_per_min=2)
    u = _make_user(db, "ia3@t.com", p)
    for _ in range(2):
        db.add(AiUsage(user_id=u.id, request_id=secrets.token_hex(8),
                       status="success", created_at=datetime.utcnow()))
    db.commit()
    r = check_ai_rate_limit(db, u)
    assert r["allowed"] is False and r["reason"] == "per_minute_limit"

def test_erros_nao_contam(db):
    p = _make_profile(db, "IA4", [], ai_daily=1, ai_per_min=1)
    u = _make_user(db, "ia4@t.com", p)
    db.add(AiUsage(user_id=u.id, request_id=secrets.token_hex(8),
                   status="error", created_at=datetime.utcnow()))
    db.commit()
    assert check_ai_rate_limit(db, u)["allowed"] is True

def test_override_individual(db):
    p = _make_profile(db, "IA5", [], ai_daily=10, ai_per_min=3)
    u = _make_user(db, "ia5@t.com", p)
    u.ai_daily_limit_override = 50; u.ai_per_minute_limit_override = 10; db.commit()
    r = check_ai_rate_limit(db, u)
    assert r["daily_limit"] == 50 and r["per_minute_limit"] == 10


# ── Conversas ─────────────────────────────────────────────────────────────────

def test_conversa_isolada(db):
    p = _make_profile(db, "CV1", [], ai_daily=10, ai_per_min=5)
    ua = _make_user(db, "a@cv.com", p); ub = _make_user(db, "b@cv.com", p)
    c = AssistantConversation(id="conv-a", user_id=ua.id, n8n_session_id="s",
                              title="A", created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    db.add(c); db.commit()
    # B não vê conversa de A
    result = db.scalar(select(AssistantConversation).where(
        AssistantConversation.id == "conv-a", AssistantConversation.user_id == ub.id))
    assert result is None

def test_conversa_dono_acessa(db):
    p = _make_profile(db, "CV2", [], ai_daily=10, ai_per_min=5)
    u = _make_user(db, "o@cv.com", p)
    c = AssistantConversation(id="conv-o", user_id=u.id, n8n_session_id="s",
                              title="Minha", created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    db.add(c); db.commit()
    result = db.scalar(select(AssistantConversation).where(
        AssistantConversation.id == "conv-o", AssistantConversation.user_id == u.id))
    assert result is not None


# ── Auditoria ─────────────────────────────────────────────────────────────────

def test_record_audit(db):
    p = _make_profile(db, "AU1", [], 10, 5); u = _make_user(db, "au@t.com", p)
    record_audit(db, user_id=u.id, action="ASSET_CREATE", entity_type="x", entity_id="1"); db.commit()
    log = db.scalar(select(AuditLog).where(AuditLog.user_id == u.id))
    assert log is not None and log.action == "ASSET_CREATE"

def test_record_security_event(db):
    record_security_event(db, event_type="CSRF_REJECTED", severity="high"); db.commit()
    ev = db.scalar(select(SecurityEvent).where(SecurityEvent.event_type == "CSRF_REJECTED"))
    assert ev is not None


# ── Vinculação OIDC ───────────────────────────────────────────────────────────

def test_novo_usuario_pending(db, monkeypatch):
    monkeypatch.setattr("app.services.auth.BOOTSTRAP_ADMIN_EMAIL", "")
    seed_profiles_and_permissions(db)
    userinfo = {"iss": "http://kc/test", "sub": "sub1", "email": "novo@t.com", "name": "Novo"}
    u = resolve_or_create_user(db, userinfo)
    assert u.status == "pending"

def test_bootstrap_admin(db, monkeypatch):
    monkeypatch.setattr("app.services.auth.BOOTSTRAP_ADMIN_EMAIL", "boot@t.com")
    seed_profiles_and_permissions(db)
    userinfo = {"iss": "http://kc/test", "sub": "sub2", "email": "boot@t.com", "name": "Boot"}
    u = resolve_or_create_user(db, userinfo)
    assert u.status == "active" and u.bootstrap_admin_granted is True

def test_bootstrap_apenas_uma_vez(db, monkeypatch):
    monkeypatch.setattr("app.services.auth.BOOTSTRAP_ADMIN_EMAIL", "boot2@t.com")
    seed_profiles_and_permissions(db)
    userinfo = {"iss": "http://kc/test", "sub": "sub3", "email": "boot2@t.com", "name": "Boot2"}
    u = resolve_or_create_user(db, userinfo)
    assert u.bootstrap_admin_granted is True
    u.status = "disabled"; db.commit()
    u2 = resolve_or_create_user(db, userinfo)
    assert u2.status == "disabled"



def test_bootstrap_recupera_identidade_existente_pending(db, monkeypatch):
    """Se o email de bootstrap for corrigido depois do primeiro login, o mesmo subject deve ser promovido."""
    seed_profiles_and_permissions(db)
    monkeypatch.setattr("app.services.auth.BOOTSTRAP_ADMIN_EMAIL", "")
    userinfo = {"iss": "http://kc/test", "sub": "sub-recover", "email": "admin.real@empresa.com", "name": "Admin Real"}
    u1 = resolve_or_create_user(db, userinfo)
    assert u1.status == "pending"
    assert u1.bootstrap_admin_granted is False

    monkeypatch.setattr("app.services.auth.BOOTSTRAP_ADMIN_EMAIL", "admin.real@empresa.com")
    u2 = resolve_or_create_user(db, userinfo)
    assert u2.id == u1.id
    assert u2.status == "active"
    assert u2.bootstrap_admin_granted is True
    assert u2.profile is not None and u2.profile.name == "ADMINISTRADOR"


def test_identidade_existente_sincroniza_email_sem_duplicar(db, monkeypatch):
    seed_profiles_and_permissions(db)
    monkeypatch.setattr("app.services.auth.BOOTSTRAP_ADMIN_EMAIL", "")
    original = {"iss": "http://kc/test", "sub": "sub-email-change", "email": "admin.om@local", "name": "Admin Local"}
    u1 = resolve_or_create_user(db, original)
    changed = {"iss": "http://kc/test", "sub": "sub-email-change", "email": "admin.real@empresa.com", "name": "Admin Real"}
    u2 = resolve_or_create_user(db, changed)
    assert u2.id == u1.id
    assert u2.email == "admin.real@empresa.com"
    assert u2.display_name == "Admin Real"

def test_identidade_existente(db, monkeypatch):
    monkeypatch.setattr("app.services.auth.BOOTSTRAP_ADMIN_EMAIL", "")
    seed_profiles_and_permissions(db)
    userinfo = {"iss": "http://kc/test", "sub": "sub4", "email": "exist@t.com", "name": "Exist"}
    u1 = resolve_or_create_user(db, userinfo)
    u2 = resolve_or_create_user(db, userinfo)
    assert u1.id == u2.id
