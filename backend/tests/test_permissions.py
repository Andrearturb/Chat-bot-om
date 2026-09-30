"""Interpretação dos papéis do client chat-bot-om-bff (app/services/permissions.py)."""
from app.services.permissions import (
    AI_LIMITS,
    DEFAULT_AI_LIMITS,
    PERMISSIONS,
    PROFILE_PRIORITY,
    ai_limits_for,
    primary_profile,
    snapshot_from_roles,
)


def test_catalogo_tem_17_permissoes_com_users_view():
    assert len(PERMISSIONS) == 17
    assert "users.view" in PERMISSIONS
    assert "users.manage" not in PERMISSIONS


def test_retrato_separa_permissoes_e_perfis_e_ignora_papeis_desconhecidos():
    snap = snapshot_from_roles(["ANALISTA", "assets.view", "uma_authorization", "offline_access", "admin"])
    assert snap.permissions == frozenset({"assets.view"})
    assert snap.profiles == ("ANALISTA",)
    assert snap.has_access


def test_perfis_ficam_em_ordem_de_prioridade():
    snap = snapshot_from_roles(["CONVIDADO", "ADMINISTRADOR", "GERENTE", "assistant.use"])
    assert snap.profiles == ("ADMINISTRADOR", "GERENTE", "CONVIDADO")


def test_sem_permissao_nao_ha_acesso_mesmo_com_nome_de_perfil():
    assert not snapshot_from_roles(["ANALISTA"]).has_access
    assert not snapshot_from_roles([]).has_access


def test_valores_que_nao_sao_texto_sao_ignorados():
    snap = snapshot_from_roles(["assets.view", None, 42, {"x": 1}])
    assert snap.permissions == frozenset({"assets.view"})


def test_perfil_principal_segue_a_prioridade():
    assert primary_profile(["DIRETOR", "GERENTE"]) == "GERENTE"
    assert primary_profile(["ANALISTA", "DIRETOR"]) == "ANALISTA"
    assert primary_profile([]) is None


def test_limite_de_ia_e_o_maior_entre_os_perfis():
    assert ai_limits_for(["CONVIDADO"]) == (20, 3)
    assert ai_limits_for(["GERENTE", "ANALISTA"]) == (150, 10)
    assert ai_limits_for(["DIRETOR", "CONVIDADO"]) == (80, 8)
    assert ai_limits_for([]) == DEFAULT_AI_LIMITS == (10, 2)


def test_tabelas_mantem_os_valores_atuais():
    assert AI_LIMITS == {"ADMINISTRADOR": (200, 20), "ANALISTA": (150, 10), "GERENTE": (120, 10),
                         "DIRETOR": (80, 8), "CONVIDADO": (20, 3)}
    assert PROFILE_PRIORITY == ("ADMINISTRADOR", "GERENTE", "ANALISTA", "DIRETOR", "CONVIDADO")
