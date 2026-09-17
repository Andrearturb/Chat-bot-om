"""
Testes da nova regra de normalização de status.

Critérios cobertos (conforme especificação):
 1. Em Aberto            → Em Aberto
 2. Em Atendimento       → Em atendimento
 3. Pendente Aprovação   → Pendente de aprovação
 4. Não Aprovado         → Não Aprovado
 5. Solicitação Finalizada → Concluído
 6. Chamado Concluído    → Concluído
 7. Em Aberto + fornecedor + data → continua Em Aberto
 8. Em Atendimento + fornecedor + data → continua Em atendimento
 9. Pendente Aprovação + fornecedor + data → continua Pendente de aprovação
10. Nenhum chamado vira "Agendado" por causa de supplier/visit_date
11. Nenhum resultado é BackLog, Agendado ou Completa
12. Mudança do status normalizado detectada pelo importer como updated
13. Status desconhecido preservado, não classificado arbitrariamente
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.service import Service
from app.models.upload import Upload
from app.services.importer import (
    normalizar_status,
    extrair_campos_negocio,
    sincronizar_servicos,
)
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


# ---------------------------------------------------------------------------
# 1–6: Mapeamento direto dos cinco status
# ---------------------------------------------------------------------------

class TestMapeamentoStatus:
    """Critérios 1–6: cada status da Tape produz o valor interno correto."""

    def test_em_aberto(self):
        assert normalizar_status("Em Aberto") == "Em Aberto"

    def test_em_aberto_minusculo(self):
        assert normalizar_status("em aberto") == "Em Aberto"

    def test_em_aberto_espacos(self):
        assert normalizar_status("  Em Aberto  ") == "Em Aberto"

    def test_em_atendimento(self):
        assert normalizar_status("Em Atendimento") == "Em atendimento"

    def test_em_atendimento_minusculo(self):
        assert normalizar_status("em atendimento") == "Em atendimento"

    def test_pendente_aprovacao_sem_de(self):
        """Tape envia 'Pendente Aprovação' (sem 'de')."""
        assert normalizar_status("Pendente Aprovação") == "Pendente de aprovação"

    def test_pendente_aprovacao_com_de(self):
        """Tape envia 'Pendente de Aprovação' (com 'de')."""
        assert normalizar_status("Pendente de Aprovação") == "Pendente de aprovação"

    def test_pendente_aprovacao_minusculo(self):
        assert normalizar_status("pendente aprovação") == "Pendente de aprovação"

    def test_pendente_aprovacao_sem_acento(self):
        assert normalizar_status("Pendente Aprovacao") == "Pendente de aprovação"

    def test_nao_aprovado(self):
        assert normalizar_status("Não Aprovado") == "Não Aprovado"

    def test_nao_aprovado_minusculo(self):
        assert normalizar_status("não aprovado") == "Não Aprovado"

    def test_nao_aprovado_sem_acento(self):
        assert normalizar_status("Nao Aprovado") == "Não Aprovado"

    def test_solicitacao_finalizada(self):
        """Critério 5: Solicitação Finalizada → Concluído."""
        assert normalizar_status("Solicitação Finalizada") == "Concluído"

    def test_solicitacao_finalizada_sem_acento(self):
        assert normalizar_status("Solicitacao Finalizada") == "Concluído"

    def test_chamado_concluido(self):
        """Critério 6: Chamado Concluído → Concluído."""
        assert normalizar_status("Chamado Concluído") == "Concluído"

    def test_chamado_concluido_sem_acento(self):
        assert normalizar_status("Chamado Concluido") == "Concluído"

    def test_none_retorna_none(self):
        assert normalizar_status(None) is None

    def test_vazio_retorna_none(self):
        assert normalizar_status("") is None

    def test_apenas_espacos_retorna_none(self):
        assert normalizar_status("   ") is None


# ---------------------------------------------------------------------------
# 7–9: Supplier e visit_date NÃO alteram o status
# ---------------------------------------------------------------------------

class TestFornecedorNaoAlteraStatus:
    """Critérios 7–9: campos operacionais não influenciam o status."""

    def test_em_aberto_com_fornecedor_e_visita(self):
        """Critério 7: Em Aberto + fornecedor + data → continua Em Aberto."""
        linha = make_linha(
            ticket="S1",
            status="Em Aberto",
            supplier="Fornecedor X",
            visit_date="2026-09-20",
        )
        campos = extrair_campos_negocio(linha)
        assert campos["status"] == "Em Aberto"

    def test_em_atendimento_com_fornecedor_e_visita(self):
        """Critério 8: Em Atendimento + fornecedor + data → continua Em atendimento."""
        linha = make_linha(
            ticket="S2",
            status="Em Atendimento",
            supplier="Fornecedor X",
            visit_date="2026-09-20",
        )
        campos = extrair_campos_negocio(linha)
        assert campos["status"] == "Em atendimento"

    def test_pendente_com_fornecedor_e_visita(self):
        """Critério 9: Pendente Aprovação + fornecedor + data → continua Pendente de aprovação."""
        linha = make_linha(
            ticket="S3",
            status="Pendente Aprovação",
            supplier="Fornecedor X",
            visit_date="2026-09-20",
        )
        campos = extrair_campos_negocio(linha)
        assert campos["status"] == "Pendente de aprovação"

    def test_so_fornecedor_sem_visita_nao_altera(self):
        """Apenas fornecedor (sem data) também não deve alterar o status."""
        linha = make_linha(
            ticket="S4",
            status="Em Aberto",
            supplier="Fornecedor X",
            visit_date=None,
        )
        campos = extrair_campos_negocio(linha)
        assert campos["status"] == "Em Aberto"

    def test_so_visita_sem_fornecedor_nao_altera(self):
        """Apenas data de visita (sem fornecedor) não deve alterar o status."""
        linha = make_linha(
            ticket="S5",
            status="Em Aberto",
            supplier=None,
            visit_date="2026-09-20",
        )
        campos = extrair_campos_negocio(linha)
        assert campos["status"] == "Em Aberto"

    def test_status_none_com_fornecedor_nao_infere(self):
        """Status None com fornecedor: não deve inferir 'Em atendimento' nem 'Agendado'."""
        linha = make_linha(
            ticket="S6",
            status=None,
            supplier="Fornecedor X",
            visit_date="2026-09-20",
        )
        campos = extrair_campos_negocio(linha)
        assert campos["status"] is None


# ---------------------------------------------------------------------------
# 10–11: Garantia de que status banidos não são mais produzidos
# ---------------------------------------------------------------------------

class TestStatusBanidos:
    """Critérios 10–11: Agendado, BackLog e Completa não devem ser gerados."""

    STATUS_BANIDOS = {"Agendado", "BackLog", "Completa"}

    def _status_produzido(self, status_tape, supplier=None, visit_date=None):
        linha = make_linha(
            ticket="X",
            status=status_tape,
            supplier=supplier,
            visit_date=visit_date,
        )
        return extrair_campos_negocio(linha)["status"]

    def test_agendado_nunca_gerado_com_fornecedor_visita(self):
        resultado = self._status_produzido("Em Aberto", supplier="F", visit_date="2026-09-20")
        assert resultado not in self.STATUS_BANIDOS

    def test_agendado_nunca_gerado_sem_status_com_fornecedor(self):
        resultado = self._status_produzido(None, supplier="F", visit_date="2026-09-20")
        assert resultado not in self.STATUS_BANIDOS

    def test_backlist_nunca_gerado_para_em_aberto(self):
        resultado = self._status_produzido("Em Aberto")
        assert resultado not in self.STATUS_BANIDOS
        assert resultado == "Em Aberto"

    def test_completa_nunca_gerada(self):
        resultado = self._status_produzido("Solicitação Finalizada")
        assert resultado not in self.STATUS_BANIDOS
        assert resultado == "Concluído"

    def test_todos_status_conhecidos_nao_produzem_banidos(self):
        status_tape = [
            "Em Aberto", "Em Atendimento", "Pendente Aprovação",
            "Não Aprovado", "Solicitação Finalizada", "Chamado Concluído",
        ]
        for st in status_tape:
            resultado = self._status_produzido(st, supplier="F", visit_date="2026-09-20")
            assert resultado not in self.STATUS_BANIDOS, (
                f"Status '{st}' produziu resultado banido: '{resultado}'"
            )


# ---------------------------------------------------------------------------
# 12: Mudança de status detectada pelo importer como updated
# ---------------------------------------------------------------------------

class TestMudancaStatusDetectada:
    """Critério 12: status normalizado alterado → importer detecta updated."""

    def test_status_agendado_vira_em_atendimento_gera_updated(self, db, upload, agora):
        """Banco tem 'Agendado' (legado). Nova sync traz 'Em Atendimento' → updated."""
        from app.models.service import Service
        svc = Service(
            ticket="M1",
            status="Agendado",  # valor legado que não deve mais existir
            praca="Nordeste",
            store_name="Loja A",
            bpcs_number="100",
            sap_number="200",
            service_description="Desc",
            upload_id=upload.id,
        )
        db.add(svc)
        db.flush()

        linhas = [make_linha(ticket="M1", status="Em Atendimento")]
        resultado = sync(db, linhas, upload, agora)

        assert resultado["updated"] == 1
        svc_atualizado = db.query(Service).filter_by(ticket="M1").one()
        assert svc_atualizado.status == "Em atendimento"

    def test_status_backlist_legado_vira_em_aberto_gera_updated(self, db, upload, agora):
        """Banco tem 'BackLog' (legado). Nova sync traz 'Em Aberto' → updated."""
        from app.models.service import Service
        svc = Service(
            ticket="M2",
            status="BackLog",
            praca="Nordeste",
            store_name="Loja A",
            bpcs_number="100",
            sap_number="200",
            service_description="Desc",
            upload_id=upload.id,
        )
        db.add(svc)
        db.flush()

        linhas = [make_linha(ticket="M2", status="Em Aberto")]
        resultado = sync(db, linhas, upload, agora)

        assert resultado["updated"] == 1
        svc_atualizado = db.query(Service).filter_by(ticket="M2").one()
        assert svc_atualizado.status == "Em Aberto"

    def test_status_completa_legado_vira_concluido_gera_updated(self, db, upload, agora):
        """Banco tem 'Completa' (legado). Nova sync traz 'Solicitação Finalizada' → updated."""
        from app.models.service import Service
        svc = Service(
            ticket="M3",
            status="Completa",
            praca="Nordeste",
            store_name="Loja A",
            bpcs_number="100",
            sap_number="200",
            service_description="Desc",
            upload_id=upload.id,
        )
        db.add(svc)
        db.flush()

        linhas = [make_linha(ticket="M3", status="Solicitação Finalizada")]
        resultado = sync(db, linhas, upload, agora)

        assert resultado["updated"] == 1
        svc_atualizado = db.query(Service).filter_by(ticket="M3").one()
        assert svc_atualizado.status == "Concluído"

    def test_mesmo_status_normalizado_unchanged(self, db, upload, agora):
        """Status já correto no banco → unchanged, sem update desnecessário."""
        from app.models.service import Service
        svc = Service(
            ticket="M4",
            status="Em Aberto",
            praca="Nordeste",
            store_name="Loja A",
            bpcs_number="100",
            sap_number="200",
            service_description="Descrição padrão",  # igual ao default do make_linha
            upload_id=upload.id,
        )
        db.add(svc)
        db.flush()

        linhas = [make_linha(ticket="M4", status="Em Aberto")]
        resultado = sync(db, linhas, upload, agora)

        assert resultado["unchanged"] == 1
        assert resultado["updated"] == 0


# ---------------------------------------------------------------------------
# 13: Status desconhecido preservado, não classificado
# ---------------------------------------------------------------------------

class TestStatusDesconhecido:
    """Critério 13: valores fora do mapeamento são preservados como recebidos."""

    def test_status_desconhecido_preservado(self):
        resultado = normalizar_status("Status Novo Qualquer")
        assert resultado == "Status Novo Qualquer"

    def test_status_desconhecido_nao_vira_em_aberto(self):
        resultado = normalizar_status("Triagem")
        assert resultado == "Triagem"
        assert resultado != "Em Aberto"

    def test_status_desconhecido_nao_vira_em_atendimento(self):
        resultado = normalizar_status("Aguardando Peças")
        assert resultado == "Aguardando Peças"
        assert resultado != "Em atendimento"

    def test_status_desconhecido_via_extrair_campos(self):
        """Status desconhecido percorre o fluxo completo sem ser alterado."""
        linha = make_linha(ticket="D1", status="Em Análise")
        campos = extrair_campos_negocio(linha)
        assert campos["status"] == "Em Análise"
