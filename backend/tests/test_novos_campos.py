"""
Testes dos três novos campos: requester, analyst_responsible, non_approval_reason.

Critérios cobertos:
1. requester é extraído do field 580436
2. analyst_responsible é extraído do field 603645
3. non_approval_reason é extraído do field 617502
4. mudança somente em requester gera updated
5. mudança somente em analyst_responsible gera updated
6. mudança somente em non_approval_reason gera updated
7. registros sem mudanças continuam unchanged
8. campos ausentes retornam None e não quebram a importação
9. novos registros persistem corretamente os três campos
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.service import Service
from app.models.upload import Upload
from app.services.importer import (
    extrair_campos_negocio,
    sincronizar_servicos,
    CAMPOS_SINCRONIZADOS,
)
from app.integrations.transformar_chamados import FIELD_ALIASES
from tests.conftest import make_linha


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def sync(db, linhas, upload=None, agora=None):
    if upload is None:
        u = Upload(source_file_name="test", total_rows=0)
        db.add(u)
        db.flush()
        upload = u
    if agora is None:
        agora = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    return sincronizar_servicos(db, linhas, upload.id, agora)


def criar_service(
    db: Session,
    upload_id: int,
    ticket: str = "1001",
    praca: str = "Nordeste",
    requester: str | None = None,
    analyst_responsible: str | None = None,
    non_approval_reason: str | None = None,
) -> Service:
    svc = Service(
        ticket=ticket,
        status="Em Aberto",          # alinhado com o que make_linha("Em aberto") normaliza
        praca=praca,
        store_name="Loja A",
        bpcs_number="100",
        sap_number="200",
        service_description="Descrição padrão",  # alinhado com o default de make_linha
        requester=requester,
        analyst_responsible=analyst_responsible,
        non_approval_reason=non_approval_reason,
        upload_id=upload_id,
    )
    db.add(svc)
    db.flush()
    return svc


# ---------------------------------------------------------------------------
# 1-3: Aliases corretos no FIELD_ALIASES
# ---------------------------------------------------------------------------

class TestAliases:
    def test_requester_field_id(self):
        """requester deve mapear para field_id 580436."""
        assert 580436 in FIELD_ALIASES["requester"]["field_ids"]

    def test_analyst_responsible_field_id(self):
        """analyst_responsible deve mapear para field_id 603645."""
        assert 603645 in FIELD_ALIASES["analyst_responsible"]["field_ids"]

    def test_non_approval_reason_field_id(self):
        """non_approval_reason deve mapear para field_id 617502."""
        assert 617502 in FIELD_ALIASES["non_approval_reason"]["field_ids"]

    def test_campos_sincronizados_contem_novos(self):
        """Os três campos devem estar em CAMPOS_SINCRONIZADOS."""
        assert "requester" in CAMPOS_SINCRONIZADOS
        assert "analyst_responsible" in CAMPOS_SINCRONIZADOS
        assert "non_approval_reason" in CAMPOS_SINCRONIZADOS


# ---------------------------------------------------------------------------
# 1-3: Extração correta dos valores via extrair_campos_negocio
# ---------------------------------------------------------------------------

class TestExtracao:
    def test_requester_extraido_do_field_580436(self):
        """requester é extraído corretamente do field_id 580436."""
        linha = make_linha(ticket="T1", requester="Ana Paula")
        campos = extrair_campos_negocio(linha)
        assert campos["requester"] == "Ana Paula"

    def test_analyst_responsible_extraido_do_field_603645(self):
        """analyst_responsible é extraído corretamente do field_id 603645."""
        linha = make_linha(ticket="T2", analyst_responsible="João Silva")
        campos = extrair_campos_negocio(linha)
        assert campos["analyst_responsible"] == "João Silva"

    def test_non_approval_reason_extraido_do_field_617502(self):
        """non_approval_reason é extraído corretamente do field_id 617502."""
        linha = make_linha(ticket="T3", non_approval_reason="Falta de orçamento aprovado")
        campos = extrair_campos_negocio(linha)
        assert campos["non_approval_reason"] == "Falta de orçamento aprovado"

    def test_requester_com_html_normalizado(self):
        """HTML no requester deve ser removido pelo normalizar_texto."""
        linha = make_linha(ticket="T4", requester="<p>Carlos</p>")
        campos = extrair_campos_negocio(linha)
        assert campos["requester"] == "Carlos"

    def test_non_approval_reason_com_html_normalizado(self):
        """HTML no non_approval_reason deve ser removido."""
        linha = make_linha(ticket="T5", non_approval_reason="<p>Sem orçamento</p>")
        campos = extrair_campos_negocio(linha)
        assert campos["non_approval_reason"] == "Sem orçamento"


# ---------------------------------------------------------------------------
# 8: Campos ausentes retornam None sem quebrar
# ---------------------------------------------------------------------------

class TestCamposAusentes:
    def test_requester_ausente_retorna_none(self):
        linha = make_linha(ticket="T10")  # requester não fornecido → None
        campos = extrair_campos_negocio(linha)
        assert campos["requester"] is None

    def test_analyst_responsible_ausente_retorna_none(self):
        linha = make_linha(ticket="T11")
        campos = extrair_campos_negocio(linha)
        assert campos["analyst_responsible"] is None

    def test_non_approval_reason_ausente_retorna_none(self):
        linha = make_linha(ticket="T12")
        campos = extrair_campos_negocio(linha)
        assert campos["non_approval_reason"] is None

    def test_todos_ausentes_nao_quebram_sync(self, db, agora):
        """Sync com os três campos None não deve lançar exceção."""
        linhas = [make_linha(ticket="T13")]
        resultado = sync(db, linhas, agora=agora)
        assert resultado["inserted"] == 1
        db.flush()
        svc = db.query(Service).filter_by(ticket="T13").one()
        assert svc.requester is None
        assert svc.analyst_responsible is None
        assert svc.non_approval_reason is None


# ---------------------------------------------------------------------------
# 9: Novos registros persistem os três campos corretamente
# ---------------------------------------------------------------------------

class TestPersistenciaNovosRegistros:
    def test_novo_registro_persiste_requester(self, db, agora):
        linhas = [make_linha(ticket="P1", requester="Maria Fernanda")]
        sync(db, linhas, agora=agora)
        db.flush()
        svc = db.query(Service).filter_by(ticket="P1").one()
        assert svc.requester == "Maria Fernanda"

    def test_novo_registro_persiste_analyst_responsible(self, db, agora):
        linhas = [make_linha(ticket="P2", analyst_responsible="Carlos Alberto")]
        sync(db, linhas, agora=agora)
        db.flush()
        svc = db.query(Service).filter_by(ticket="P2").one()
        assert svc.analyst_responsible == "Carlos Alberto"

    def test_novo_registro_persiste_non_approval_reason(self, db, agora):
        linhas = [make_linha(ticket="P3", non_approval_reason="Contrato vencido")]
        sync(db, linhas, agora=agora)
        db.flush()
        svc = db.query(Service).filter_by(ticket="P3").one()
        assert svc.non_approval_reason == "Contrato vencido"

    def test_novo_registro_persiste_os_tres_campos(self, db, agora):
        linhas = [make_linha(
            ticket="P4",
            requester="Joana",
            analyst_responsible="Pedro",
            non_approval_reason="Prazo expirado",
        )]
        sync(db, linhas, agora=agora)
        db.flush()
        svc = db.query(Service).filter_by(ticket="P4").one()
        assert svc.requester == "Joana"
        assert svc.analyst_responsible == "Pedro"
        assert svc.non_approval_reason == "Prazo expirado"


# ---------------------------------------------------------------------------
# 4-6: Mudança isolada em cada campo gera updated
# ---------------------------------------------------------------------------

class TestMudancaGeraUpdated:
    def test_mudanca_somente_requester_gera_updated(self, db, upload, agora):
        """4. Mudança somente em requester → updated."""
        criar_service(db, upload.id, ticket="U1", requester="Ana")

        linhas = [make_linha(ticket="U1", requester="Beatriz")]
        resultado = sync(db, linhas, upload, agora)

        assert resultado["updated"] == 1
        assert resultado["unchanged"] == 0
        svc = db.query(Service).filter_by(ticket="U1").one()
        assert svc.requester == "Beatriz"

    def test_mudanca_somente_analyst_responsible_gera_updated(self, db, upload, agora):
        """5. Mudança somente em analyst_responsible → updated."""
        criar_service(db, upload.id, ticket="U2", analyst_responsible="João")

        linhas = [make_linha(ticket="U2", analyst_responsible="Maria")]
        resultado = sync(db, linhas, upload, agora)

        assert resultado["updated"] == 1
        assert resultado["unchanged"] == 0
        svc = db.query(Service).filter_by(ticket="U2").one()
        assert svc.analyst_responsible == "Maria"

    def test_mudanca_somente_non_approval_reason_gera_updated(self, db, upload, agora):
        """6. Mudança somente em non_approval_reason → updated."""
        criar_service(db, upload.id, ticket="U3", non_approval_reason="Motivo antigo")

        linhas = [make_linha(ticket="U3", non_approval_reason="Motivo novo")]
        resultado = sync(db, linhas, upload, agora)

        assert resultado["updated"] == 1
        assert resultado["unchanged"] == 0
        svc = db.query(Service).filter_by(ticket="U3").one()
        assert svc.non_approval_reason == "Motivo novo"

    def test_requester_none_para_valor_gera_updated(self, db, upload, agora):
        """None → valor em requester gera updated."""
        criar_service(db, upload.id, ticket="U4", requester=None)

        linhas = [make_linha(ticket="U4", requester="Novo Requisitante")]
        resultado = sync(db, linhas, upload, agora)

        assert resultado["updated"] == 1

    def test_analyst_responsible_valor_para_none_gera_updated(self, db, upload, agora):
        """Valor → None em analyst_responsible gera updated."""
        criar_service(db, upload.id, ticket="U5", analyst_responsible="Alguém")

        linhas = [make_linha(ticket="U5", analyst_responsible=None)]
        resultado = sync(db, linhas, upload, agora)

        assert resultado["updated"] == 1
        svc = db.query(Service).filter_by(ticket="U5").one()
        assert svc.analyst_responsible is None


# ---------------------------------------------------------------------------
# 7: Registros sem mudanças continuam unchanged
# ---------------------------------------------------------------------------

class TestSemMudancaUnchanged:
    def test_tres_campos_iguais_unchanged(self, db, upload, agora):
        """7. Todos os campos iguais (incluindo os três novos) → unchanged."""
        criar_service(
            db, upload.id,
            ticket="UC1",
            requester="Req",
            analyst_responsible="Analyst",
            non_approval_reason="Motivo X",
        )

        linhas = [make_linha(
            ticket="UC1",
            requester="Req",
            analyst_responsible="Analyst",
            non_approval_reason="Motivo X",
        )]
        resultado = sync(db, linhas, upload, agora)

        assert resultado["unchanged"] == 1
        assert resultado["updated"] == 0

    def test_todos_none_unchanged(self, db, upload, agora):
        """Três campos None no banco e None na resposta → unchanged."""
        criar_service(
            db, upload.id,
            ticket="UC2",
            requester=None,
            analyst_responsible=None,
            non_approval_reason=None,
        )

        linhas = [make_linha(ticket="UC2")]  # todos None
        resultado = sync(db, linhas, upload, agora)

        assert resultado["unchanged"] == 1
        assert resultado["updated"] == 0
