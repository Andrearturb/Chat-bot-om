"""
Catálogo de permissões e perfis do Chat-bot O&M.

Perfis e permissões são papéis do client ``chat-bot-om-bff`` no Keycloak
(keycloak-central/config/10-realm.yaml). Este módulo apenas interpreta os papéis
recebidos no token assinado; nada aqui concede acesso.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

PERMISSIONS: frozenset[str] = frozenset({
    "assistant.use", "assistant.history",
    "indicators.view",
    "assets.view", "assets.create", "assets.edit", "assets.delete", "assets.import",
    "documents.view", "documents.upload", "documents.replace", "documents.delete",
    "audit.view", "users.view",
    "settings.view", "settings.manage",
    "sync.tape",
})

# Ordem de exibição: o perfil de maior prioridade vira o "perfil" da pessoa.
PROFILE_PRIORITY: tuple[str, ...] = ("ADMINISTRADOR", "GERENTE", "ANALISTA", "DIRETOR", "CONVIDADO")

PROFILE_DISPLAY: dict[str, str] = {
    "ADMINISTRADOR": "Administrador",
    "GERENTE": "Gerente",
    "ANALISTA": "Analista",
    "DIRETOR": "Diretor",
    "CONVIDADO": "Convidado",
}

# (limite diário, limite por minuto) de uso da IA.
AI_LIMITS: dict[str, tuple[int, int]] = {
    "ADMINISTRADOR": (200, 20),
    "ANALISTA": (150, 10),
    "GERENTE": (120, 10),
    "DIRETOR": (80, 8),
    "CONVIDADO": (20, 3),
}
DEFAULT_AI_LIMITS: tuple[int, int] = (10, 2)


@dataclass(frozen=True)
class RoleSnapshot:
    """Retrato do acesso extraído do token: permissões e perfis (por prioridade)."""

    permissions: frozenset[str]
    profiles: tuple[str, ...]

    @property
    def has_access(self) -> bool:
        return bool(self.permissions)


def snapshot_from_roles(roles: Iterable) -> RoleSnapshot:
    names = {role for role in roles if isinstance(role, str)}
    return RoleSnapshot(
        permissions=frozenset(names & PERMISSIONS),
        profiles=tuple(profile for profile in PROFILE_PRIORITY if profile in names),
    )


def primary_profile(profiles: Iterable[str]) -> str | None:
    present = set(profiles)
    return next((profile for profile in PROFILE_PRIORITY if profile in present), None)


def ai_limits_for(profiles: Iterable[str]) -> tuple[int, int]:
    limits = [AI_LIMITS[profile] for profile in set(profiles) if profile in AI_LIMITS]
    if not limits:
        return DEFAULT_AI_LIMITS
    return max(daily for daily, _ in limits), max(per_minute for _, per_minute in limits)
