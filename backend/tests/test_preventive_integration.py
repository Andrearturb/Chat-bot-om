"""Integração do app Tape 57532 sem misturar chamados corretivos."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.integrations.preventive_fields import PREVENTIVE_FIELD_ALIASES, PREVENTIVE_REFERENCE_FIELDS
from app.integrations.transformar_chamados import TapeTransformer
from app.models.preventive_service import PreventiveService
from app.models.service import Service
from app.models.upload import Upload
from app.services.importer import importar_servicos_tape
from app.services.preventive_importer import (
    classificar_sla,
    extrair_campos_preventivos,
    sincronizar_preventivas,
)


def raw_record(status="Serviço Finalizado", value=2500):
    signature = '[{"status":"completo","url_pdf_assinado":"https://api.autentique.com.br/pdf/1"}]'
    fields = {
        677154: 2728,
        676273: {"text": status},
        580460: {"title": "Loja Norte | BCPS: 21417 | SAP: 4071"},
        580462: {"text": "São Luís"},
        580461: {"text": "Climatização"},
        676274: {"text": "Limpeza"},
        676275: {"text": "Ana"},
        680415: value,
        693107: {"text": "Mensal"},
        681369: signature,
        676271: '<div>100% do progresso</div>',
    }
    return {
        "app_record_id": "2728",
        "created_on": "2026-09-25T08:00:00Z",
        "fields": [
            {"field_id": field_id, "label": "", "values": [{"value": item}]}
            for field_id, item in fields.items()
        ],
    }


def transform(record):
    return TapeTransformer(
        reference_fields=PREVENTIVE_REFERENCE_FIELDS,
        field_aliases=PREVENTIVE_FIELD_ALIASES,
    ).transformar_record(record)


def test_transformer_usa_ids_preventivos_e_campos_necessarios():
    row = transform(raw_record())
    ticket, fields = extrair_campos_preventivos(row)

    assert ticket == "2728"
    assert fields["status"] == "Serviço Finalizado"
    assert fields["store_name"] == "Loja Norte"
    assert fields["praca"] == "São Luís"
    assert fields["category"] == "Climatização"
    assert fields["subcategory"] == "Limpeza"
    assert fields["approved_value"] == Decimal("2500")
    assert fields["periodicity"] == "Mensal"
    assert fields["signature_status"] == "completo"
    assert fields["signed_pdf_url"] == "https://api.autentique.com.br/pdf/1"
    assert fields["created_on"] is not None
    assert fields["sla_status"] is None
    assert "580453" not in row  # ID de status da corretiva não entra neste mapeamento.


def test_praca_segue_a_mesma_regra_da_corretiva():
    """"Brasil" vira "Escritório" igual na corretiva — mesma loja não pode
    aparecer com nomes de praça diferentes entre os dois painéis."""
    record = raw_record()
    for item in record["fields"]:
        if item["field_id"] == 580462:
            item["values"] = [{"value": "Brasil"}]
    ticket, fields = extrair_campos_preventivos(transform(record))

    assert ticket == "2728"
    assert fields["praca"] == "Escritório"


def test_sla_progress_sem_marca_nao_vira_100_por_cento():
    assert classificar_sla('<div style="width:100%">100%</div>') is None
    assert classificar_sla('<div>Atrasado</div>') == "Atrasado"
    assert classificar_sla('<div>No prazo</div>') == "No prazo"


def test_sla_progress_nao_classifica_texto_negado():
    """"Não atrasado" contém a palavra "atrasado", mas significa o oposto —
    uma busca por substring/palavra inverteria o veredito."""
    assert classificar_sla('<div>Não atrasado</div>') is None
    assert classificar_sla('<span>Não concluído no prazo</span>') is None


def test_sync_preventivo_nao_altera_corretivo_com_mesmo_ticket(db, upload, agora):
    db.add(Service(ticket="2728", status="Concluído", upload_id=upload.id))
    db.flush()
    first = sincronizar_preventivas(db, [transform(raw_record())], upload.id, agora)
    db.flush()
    assert first == {"inserted": 1, "updated": 0, "unchanged": 0, "rejected": 0}
    assert db.query(Service).filter_by(ticket="2728").one().status == "Concluído"

    second = sincronizar_preventivas(db, [transform(raw_record())], upload.id, agora)
    assert second["unchanged"] == 1

    changed = sincronizar_preventivas(
        db, [transform(raw_record(status="Backlog", value=3000))], upload.id, agora
    )
    db.flush()
    assert changed["updated"] == 1
    preventive = db.query(PreventiveService).filter_by(ticket="2728").one()
    assert preventive.status == "Backlog"
    assert preventive.approved_value == Decimal("3000.00")
    assert db.query(Service).filter_by(ticket="2728").one().status == "Concluído"


def test_importer_existente_despacha_57532_sem_outro_token(db, monkeypatch):
    calls = []

    def fake_import(db, limit):
        calls.append(limit)
        return {"total_rows": 1}

    monkeypatch.setattr("app.services.preventive_importer.importar_preventivas_tape", fake_import)
    assert importar_servicos_tape(db, app_id=57532, limit=50)["total_rows"] == 1
    assert calls == [50]


def test_api_preventiva_expoe_status_cru_e_pdf(db, upload):
    upload.source_file_name = "Tape API - 57532"
    db.add(PreventiveService(
        ticket="2728", status="Serviço Finalizado", store_name="Loja Norte",
        praca="São Luís", category="Climatização", subcategory="Limpeza",
        signature_status="completo", signed_pdf_url="https://api.autentique.com.br/pdf/1",
        approved_value=Decimal("2500.00"), periodicity="Mensal", upload_id=upload.id,
    ))
    db.commit()

    from app.api.routes.preventive_services import listar_preventivas

    response = listar_preventivas(db=db)
    item = response.dados[0]
    assert item.status == "Concluído"
    assert item.raw_status == "Serviço Finalizado"
    assert item.signed_pdf_url == "https://api.autentique.com.br/pdf/1"
    assert item.periodicity == "Mensal"
    assert response.upload_data is not None


def test_services_ignora_sync_mais_novo_da_preventiva_no_ultima_atualizacao(db, upload, agora):
    """Um sync da preventiva depois do sync da corretiva não pode fazer o painel
    de corretivos mostrar "atualizado agora" — isso esconderia justamente uma
    falha de sync da própria corretiva."""
    from app.api.routes.services import listar_servicos

    upload.source_file_name = "Tape API - 57531"
    upload.uploaded_at = agora
    db.add(Service(ticket="9001", status="Concluído", upload_id=upload.id))

    upload_preventiva = Upload(
        source_file_name="Tape API - 57532",
        total_rows=1,
        uploaded_at=agora + timedelta(hours=1),  # sync da preventiva, mais recente
    )
    db.add(upload_preventiva)
    db.commit()

    result = listar_servicos(db=db)

    assert result.upload_data is not None
    assert result.upload_data.astimezone(timezone.utc) == agora


def test_um_agendador_tenta_os_dois_apps_mesmo_se_um_falhar(monkeypatch):
    from app.tasks import tape_scheduler

    calls = []
    sessions = []

    class FakeSession:
        def rollback(self):
            calls.append("rollback")

        def close(self):
            calls.append("close")

    def make_session():
        session = FakeSession()
        sessions.append(session)
        return session

    def fake_import(db, app_id):
        calls.append(app_id)
        if app_id == 57531:
            raise RuntimeError("falha isolada")
        return {"total_rows": 2, "upload_data": None}

    monkeypatch.setattr(tape_scheduler, "SessionLocal", make_session)
    monkeypatch.setattr(tape_scheduler, "importar_servicos_tape", fake_import)

    tape_scheduler.executar_sincronizacao_tape()

    assert [item for item in calls if isinstance(item, int)] == [57531, 57532]
    assert len(sessions) == 2
    assert calls.count("close") == 2
    assert calls.count("rollback") == 1
