"""
Testes da sincronização por diferenças do importer.

Cobre os cenários exigidos pelo critério de aceitação:
- Inserção de registro novo
- Atualização de status
- Atualização de outro campo com status igual
- Registro idêntico → sem UPDATE nos campos de negócio
- Valores nulos e campos ausentes
- Praça e registros filtrados pelas regras de negócio
- Registro ausente na resposta → preservado no banco
- Coleta vazia → banco intocado
- Reexecução do mesmo conjunto → 0 inserções, 0 atualizações
- Critério de aceitação principal: 1000 + 20 novos + 10 mudaram
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.orm import Session

from app.models.service import Service
from app.models.upload import Upload
from app.services.importer import (
    campos_mudaram,
    sincronizar_servicos,
    importar_servicos_tape,
    preparar_registro,
    CAMPOS_SINCRONIZADOS,
)
from tests.conftest import make_linha


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def criar_service_existente(
    db: Session,
    upload_id: int,
    ticket: str = "1001",
    status: str = "BackLog",
    store_name: str = "Loja A",
    bpcs_number: str = "100",
    sap_number: str = "200",
    praca: str = "Nordeste",
    service_description: str = "Descrição padrão",
    supplier: str | None = None,
    visit_date: datetime | None = None,
    solution_text: str | None = None,
    signature_status: str | None = None,
    signed_pdf_url: str | None = None,
    created_on: datetime | None = None,
) -> Service:
    svc = Service(
        ticket=ticket,
        status=status,
        store_name=store_name,
        bpcs_number=bpcs_number,
        sap_number=sap_number,
        praca=praca,
        service_description=service_description,
        supplier=supplier,
        visit_date=visit_date,
        solution_text=solution_text,
        signature_status=signature_status,
        signed_pdf_url=signed_pdf_url,
        created_on=created_on,
        upload_id=upload_id,
    )
    db.add(svc)
    db.flush()
    return svc


def sync(db, linhas, upload=None, agora=None):
    """Atalho para chamar sincronizar_servicos nos testes."""
    if upload is None:
        u = Upload(source_file_name="test", total_rows=0)
        db.add(u)
        db.flush()
        upload = u
    if agora is None:
        agora = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    return sincronizar_servicos(db, linhas, upload.id, agora)


# ---------------------------------------------------------------------------
# Testes unitários: campos_mudaram
# ---------------------------------------------------------------------------

class TestCamposMudaram:
    def test_status_mudou(self, db, upload):
        svc = criar_service_existente(db, upload.id, ticket="1", status="BackLog")
        campos = {"status": "Em atendimento", **{c: None for c in CAMPOS_SINCRONIZADOS if c != "status"}}
        # store_name etc precisam bater para isolar o status
        campos["store_name"] = svc.store_name
        campos["bpcs_number"] = svc.bpcs_number
        campos["sap_number"] = svc.sap_number
        campos["praca"] = svc.praca
        campos["service_description"] = svc.service_description
        assert campos_mudaram(svc, campos) is True

    def test_sem_mudanca(self, db, upload):
        svc = criar_service_existente(db, upload.id, ticket="2", status="BackLog")
        campos = {c: getattr(svc, c) for c in CAMPOS_SINCRONIZADOS}
        assert campos_mudaram(svc, campos) is False

    def test_campo_texto_mudou(self, db, upload):
        svc = criar_service_existente(db, upload.id, ticket="3", service_description="Antes")
        campos = {c: getattr(svc, c) for c in CAMPOS_SINCRONIZADOS}
        campos["service_description"] = "Depois"
        assert campos_mudaram(svc, campos) is True

    def test_none_para_valor(self, db, upload):
        svc = criar_service_existente(db, upload.id, ticket="4", supplier=None)
        campos = {c: getattr(svc, c) for c in CAMPOS_SINCRONIZADOS}
        campos["supplier"] = "Novo Fornecedor"
        assert campos_mudaram(svc, campos) is True

    def test_valor_para_none(self, db, upload):
        svc = criar_service_existente(db, upload.id, ticket="5", supplier="Fornecedor")
        campos = {c: getattr(svc, c) for c in CAMPOS_SINCRONIZADOS}
        campos["supplier"] = None
        assert campos_mudaram(svc, campos) is True

    def test_ambos_none(self, db, upload):
        svc = criar_service_existente(db, upload.id, ticket="6", supplier=None, solution_text=None)
        campos = {c: getattr(svc, c) for c in CAMPOS_SINCRONIZADOS}
        assert campos_mudaram(svc, campos) is False


# ---------------------------------------------------------------------------
# Testes de sincronização: cenários básicos
# ---------------------------------------------------------------------------

class TestSincronizarServicos:

    def test_insere_registro_novo(self, db, agora):
        linhas = [make_linha(ticket="2000")]
        resultado = sync(db, linhas, agora=agora)
        db.flush()

        assert resultado["inserted"] == 1
        assert resultado["updated"] == 0
        assert resultado["unchanged"] == 0

        svc = db.query(Service).filter_by(ticket="2000").one()
        assert svc.status == "BackLog"
        assert svc.praca == "Nordeste"
        # SQLite strip tzinfo — compara ingênuo
        assert svc.synced_at is not None

    def test_atualiza_status_mudou(self, db, upload, agora):
        criar_service_existente(db, upload.id, ticket="3000", status="BackLog", praca="Nordeste")

        # Linha com fornecedor → status muda para "Em atendimento"
        linhas = [make_linha(ticket="3000", status="Em aberto", supplier="Fornecedor Teste")]
        resultado = sync(db, linhas, upload, agora)

        assert resultado["updated"] == 1
        assert resultado["inserted"] == 0

        svc = db.query(Service).filter_by(ticket="3000").one()
        assert svc.status == "Em atendimento"
        assert svc.supplier == "Fornecedor Teste"

    def test_atualiza_descricao_status_igual(self, db, upload, agora):
        criar_service_existente(
            db, upload.id, ticket="4000",
            status="BackLog", praca="Nordeste",
            service_description="Descrição antiga",
        )

        linhas = [make_linha(ticket="4000", service_description="Descrição nova")]
        resultado = sync(db, linhas, upload, agora)

        assert resultado["updated"] == 1
        svc = db.query(Service).filter_by(ticket="4000").one()
        assert svc.service_description == "Descrição nova"
        assert svc.status == "BackLog"  # status não mudou

    def test_sem_mudanca_nao_conta_como_update(self, db, upload, agora):
        """Registro idêntico: unchanged++ mas sem UPDATE nos campos de negócio."""
        svc_antes = criar_service_existente(
            db, upload.id, ticket="5000",
            status="BackLog", praca="Nordeste",
            service_description="Descrição padrão",
            store_name="Loja A",
            bpcs_number="100",
            sap_number="200",
        )
        id_antes = svc_antes.id
        created_on_antes = svc_antes.created_on
        db.flush()

        linhas = [make_linha(ticket="5000")]
        resultado = sync(db, linhas, upload, agora)
        db.flush()

        assert resultado["unchanged"] == 1, f"unchanged={resultado}"
        assert resultado["updated"] == 0

        svc = db.query(Service).filter_by(ticket="5000").one()
        assert svc.id == id_antes  # identidade preservada
        assert svc.created_on == created_on_antes  # created_on preservado

    def test_registro_ausente_preservado(self, db, upload, agora):
        """Registro existente não presente na resposta → não é excluído."""
        criar_service_existente(db, upload.id, ticket="6000", praca="Nordeste")
        db.flush()

        # Sync com outra ticket — 6000 não aparece
        linhas = [make_linha(ticket="6001")]
        sync(db, linhas, upload, agora)
        db.flush()

        assert db.query(Service).filter_by(ticket="6000").count() == 1
        assert db.query(Service).filter_by(ticket="6001").count() == 1

    def test_reexecucao_sem_mudancas(self, db, upload, agora):
        """Executar o mesmo conjunto duas vezes: segunda execução → 0 inserções, 0 updates."""
        linhas = [make_linha(ticket="7000"), make_linha(ticket="7001")]

        r1 = sync(db, linhas, agora=agora)
        assert r1["inserted"] == 2

        r2 = sync(db, linhas, agora=agora)
        assert r2["inserted"] == 0
        assert r2["updated"] == 0
        assert r2["unchanged"] == 2

    def test_linha_sem_ticket_rejeitada(self, db, agora):
        linha_invalida = make_linha(ticket="")  # ticket vazio → None após normalização
        linha_invalida["field_values"]["ticket"]["value"] = None
        resultado = sync(db, [linha_invalida], agora=agora)

        assert resultado["rejected"] == 1
        assert resultado["inserted"] == 0

    def test_praca_escritorio_filtrada(self, db, agora):
        """Praça 'Escritório' original é descartada pelas regras de negócio."""
        linha = make_linha(ticket="8000", praca="Escritório")
        resultado = sync(db, [linha], agora=agora)

        assert resultado["rejected"] == 1
        assert db.query(Service).filter_by(ticket="8000").count() == 0

    def test_praca_brasil_vira_escritorio(self, db, agora):
        """Praça 'Brasil' é renomeada para 'Escritório'."""
        linha = make_linha(ticket="9000", praca="Brasil")
        sync(db, [linha], agora=agora)
        db.flush()

        svc = db.query(Service).filter_by(ticket="9000").one()
        assert svc.praca == "Escritório"

    def test_lista_vazia_nao_escreve(self, db, agora):
        resultado = sync(db, [], agora=agora)
        assert resultado["inserted"] == 0
        assert resultado["updated"] == 0
        assert db.query(Service).count() == 0

    def test_preserva_id_e_created_on_no_update(self, db, upload, agora):
        """Atualização não deve recriar o registro: id é preservado."""
        svc = criar_service_existente(
            db, upload.id, ticket="10000",
            status="BackLog", praca="Nordeste",
            created_on=None,  # compatível com make_linha padrão (created_on=None)
        )
        id_original = svc.id
        db.flush()

        # Status muda via fornecedor
        linhas = [make_linha(ticket="10000", supplier="Novo Fornecedor")]
        resultado = sync(db, linhas, upload, agora)

        assert resultado["updated"] == 1
        db.flush()
        svc_atualizado = db.query(Service).filter_by(ticket="10000").one()
        assert svc_atualizado.id == id_original
        assert svc_atualizado.supplier == "Novo Fornecedor"

    def test_synced_at_atualizado_em_unchanged(self, db, upload):
        """synced_at deve ser atualizado mesmo quando o registro não mudou.
        SQLite strip tzinfo — comparamos apenas o valor naive.
        """
        agora1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        agora2 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        agora1_naive = agora1.replace(tzinfo=None)
        agora2_naive = agora2.replace(tzinfo=None)

        criar_service_existente(db, upload.id, ticket="11000", praca="Nordeste")
        linhas = [make_linha(ticket="11000")]

        sync(db, linhas, upload, agora1)
        db.flush()
        svc = db.query(Service).filter_by(ticket="11000").one()
        # Compara sem tzinfo para compatibilidade com SQLite
        assert svc.synced_at.replace(tzinfo=None) == agora1_naive

        sync(db, linhas, upload, agora2)
        db.flush()
        svc = db.query(Service).filter_by(ticket="11000").one()
        assert svc.synced_at.replace(tzinfo=None) == agora2_naive


# ---------------------------------------------------------------------------
# Critério de aceitação principal
# ---------------------------------------------------------------------------

class TestCriterioAceitacao:

    def _criar_base_1000(self, db, upload_id: int) -> None:
        """Insere 1000 registros base no banco."""
        servicos = [
            Service(
                ticket=str(i),
                status="BackLog",
                praca="Nordeste",
                store_name=f"Loja {i}",
                bpcs_number=str(i),
                sap_number=str(i),
                service_description=f"Descrição {i}",
                upload_id=upload_id,
            )
            for i in range(1, 1001)
        ]
        db.add_all(servicos)
        db.flush()

    def test_1000_base_20_novos_10_mudaram(self, db, agora):
        u = Upload(source_file_name="base", total_rows=1000)
        db.add(u)
        db.flush()
        self._criar_base_1000(db, u.id)
        db.commit()

        # Monta a nova coleta: 1000 iguais + 10 com status mudado + 20 novos
        linhas = []

        for i in range(1, 1001):
            if i <= 10:
                # Tickets 1-10: status muda para "Em atendimento" via fornecedor
                linhas.append(make_linha(
                    ticket=str(i),
                    praca="Nordeste",
                    store_name=f"Loja {i} | BCPS: {i} | SAP: {i}",
                    service_description=f"Descrição {i}",
                    supplier="Fornecedor Novo",
                ))
            else:
                linhas.append(make_linha(
                    ticket=str(i),
                    praca="Nordeste",
                    store_name=f"Loja {i} | BCPS: {i} | SAP: {i}",
                    service_description=f"Descrição {i}",
                ))

        # 20 registros novos
        for i in range(1001, 1021):
            linhas.append(make_linha(
                ticket=str(i),
                praca="Nordeste",
                store_name=f"Loja {i} | BCPS: {i} | SAP: {i}",
                service_description=f"Descrição {i}",
            ))

        resultado = sync(db, linhas, agora=agora)
        db.commit()

        assert resultado["inserted"] == 20,  f"Esperado 20 inserções, obteve {resultado['inserted']}"
        assert resultado["updated"] == 10,   f"Esperado 10 atualizações, obteve {resultado['updated']}"
        assert resultado["unchanged"] == 990, f"Esperado 990 sem mudança, obteve {resultado['unchanged']}"
        assert resultado["rejected"] == 0

        total = db.query(Service).count()
        assert total == 1020, f"Esperado 1020 registros, obteve {total}"

    def test_reexecucao_1020_sem_mudanca(self, db, agora):
        """Segunda execução com os mesmos 1020 registros → 0 inserções, 0 updates."""
        u = Upload(source_file_name="base", total_rows=0)
        db.add(u)
        db.flush()
        self._criar_base_1000(db, u.id)
        db.commit()

        linhas = []
        for i in range(1, 1021):
            linhas.append(make_linha(
                ticket=str(i),
                praca="Nordeste",
                store_name=f"Loja {i} | BCPS: {i} | SAP: {i}",
                service_description=f"Descrição {i}",
            ))

        r1 = sync(db, linhas, agora=agora)
        db.commit()

        r2 = sync(db, linhas, agora=agora)
        db.commit()

        assert r2["inserted"] == 0
        assert r2["updated"] == 0
        assert r2["unchanged"] == r1["inserted"] + r1["unchanged"] + r1["updated"]


# ---------------------------------------------------------------------------
# Teste de importar_servicos_tape (integração com mock da API)
# ---------------------------------------------------------------------------

class TestImportarServicosTape:

    def test_coleta_vazia_nao_altera_banco(self, db, upload):
        """Resposta vazia da API → banco preservado, sem escrita."""
        criar_service_existente = __import__(
            "tests.conftest", fromlist=["criar_service_existente"]
        )

        # Cria um serviço existente direto
        svc = Service(
            ticket="99999", status="BackLog", praca="Nordeste",
            upload_id=upload.id,
        )
        db.add(svc)
        db.commit()

        with patch("app.services.importer.carregar_token", return_value="fake-token"), \
             patch("app.services.importer.TapeClient") as mock_client_cls:

            mock_client = MagicMock()
            mock_client.get_records_tratados.return_value = []
            mock_client.__enter__ = lambda s: mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client_cls.return_value = mock_client

            resultado = importar_servicos_tape(db=db)

        assert resultado["total_rows"] == 0
        assert "preservado" in resultado["message"].lower()
        # Serviço existente permanece intacto
        assert db.query(Service).filter_by(ticket="99999").count() == 1

    def test_sync_basica_via_importar(self, db):
        """importar_servicos_tape com 2 registros novos."""
        linhas = [make_linha(ticket="A1"), make_linha(ticket="A2")]

        with patch("app.services.importer.carregar_token", return_value="fake-token"), \
             patch("app.services.importer.TapeClient") as mock_client_cls:

            mock_client = MagicMock()
            mock_client.get_records_tratados.return_value = linhas
            mock_client.__enter__ = lambda s: mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client_cls.return_value = mock_client

            resultado = importar_servicos_tape(db=db)

        assert resultado["inserted"] == 2
        assert resultado["updated"] == 0
        assert db.query(Service).count() == 2
