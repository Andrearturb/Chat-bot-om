"""A relação Tape é pelo record_id do dCentros, independente do nome da loja."""

from sqlalchemy import select

from app.integrations.transformar_chamados import TapeTransformer
from app.models.tape_center import TapeCenter
from app.models.service import Service
from app.models.preventive_service import PreventiveService
from app.services.importer import extrair_campos_negocio, importar_servicos_tape
from app.services.preventive_importer import extrair_campos_preventivos
from app.services.tape_centers_importer import extract_center, sync_centers
from app.integrations.preventive_fields import PREVENTIVE_FIELD_ALIASES, PREVENTIVE_REFERENCE_FIELDS


def center_record(record_id=32220251, name="Natal Shopping", unique_number=40):
    return {
        "record_id": record_id,
        "record_url": f"https://tapeapp.com/record/{record_id}",
        "title": f"{name} | BCPS: 7423 | SAP: 4002",
        "fields": [
            {"field_id": 280836, "values": [{"value": name}]},
            {"field_id": 334670, "values": [{"value": "7423"}]},
            {"field_id": 334669, "values": [{"value": "4002"}]},
            {"field_id": 522123, "values": [{"value": "402124002"}]},
            {"field_id": 280858, "values": [{"value": {"text": "Natal"}}]},
            {"field_id": 290650, "values": [{"value": unique_number}]},
        ],
    }


def call_record(field_id, record_id=32220251, title="Natal Shopping | BCPS: 7423 | SAP: 4002"):
    return {
        "record_id": 178271948,
        "app_record_id": "2727",
        "fields": [
            {"field_id": field_id, "label": "Local de Atendimento", "type": "app",
             "values": [{"value": {"app_id": 30902, "record_id": record_id, "title": title}}]},
            {"field_id": 580450, "label": "Praça", "type": "category",
             "values": [{"value": {"text": "Natal"}}]},
            {"field_id": 677154, "label": "Ticket", "type": "unique_id",
             "values": [{"value": 2727}]},
        ],
    }


def test_chamados_conservam_record_id_da_relacao_com_dcentros():
    corrective = TapeTransformer().transformar_record(call_record(580441))
    assert corrective["field_values"]["raw_location"]["value"].startswith("Natal Shopping")
    assert extrair_campos_negocio(corrective)["tape_center_record_id"] == 32220251

    preventive = TapeTransformer(
        reference_fields=PREVENTIVE_REFERENCE_FIELDS,
        field_aliases=PREVENTIVE_FIELD_ALIASES,
    ).transformar_record(call_record(580460))
    _, fields = extrair_campos_preventivos(preventive)
    assert fields["tape_center_record_id"] == 32220251


def test_relacao_de_outro_app_nao_e_tratada_como_dcentros():
    record = call_record(580460)
    record["fields"][0]["values"][0]["value"]["app_id"] = 60906
    treated = TapeTransformer(
        reference_fields=PREVENTIVE_REFERENCE_FIELDS,
        field_aliases=PREVENTIVE_FIELD_ALIASES,
    ).transformar_record(record)
    assert extrair_campos_preventivos(treated)[1]["tape_center_record_id"] is None


def test_dcentros_sincroniza_e_pode_ser_ligado_ao_chamado(db, upload, agora):
    first = sync_centers(db, [center_record()], upload.id, agora)
    db.flush()
    assert first == {"inserted": 1, "updated": 0, "unchanged": 0, "rejected": 0}
    assert sync_centers(db, [center_record()], upload.id, agora)["unchanged"] == 1
    assert sync_centers(db, [center_record(name="Natal Shopping L2")], upload.id, agora)["updated"] == 1
    center = db.execute(select(TapeCenter).where(TapeCenter.record_id == 32220251)).scalar_one()
    assert (center.unique_number, center.name, center.bcps_number) == (40, "Natal Shopping L2", "7423")
    assert extrair_campos_preventivos(TapeTransformer(
        reference_fields=PREVENTIVE_REFERENCE_FIELDS,
        field_aliases=PREVENTIVE_FIELD_ALIASES,
    ).transformar_record(call_record(580460)))[1]["tape_center_record_id"] == center.record_id


def test_importador_existente_despacha_dcentros(db, monkeypatch):
    calls = []

    def fake_import(db, limit):
        calls.append(limit)
        return {"total_rows": 1}

    monkeypatch.setattr("app.services.tape_centers_importer.importar_centros_tape", fake_import)
    assert importar_servicos_tape(db, app_id=30902, limit=25)["total_rows"] == 1
    assert calls == [25]


def test_apis_de_chamados_expoem_numero_do_dcentros(db, upload, agora):
    from app.api.routes.services import listar_servicos
    from app.api.routes.preventive_services import listar_preventivas

    sync_centers(db, [center_record()], upload.id, agora)
    db.add(Service(ticket="4987", status="Concluído", upload_id=upload.id,
                   tape_center_record_id=32220251))
    db.add(PreventiveService(ticket="2727", status="Serviço Finalizado", upload_id=upload.id,
                             tape_center_record_id=32220251))
    db.commit()

    corrective = listar_servicos(db=db).dados[0]
    preventive = listar_preventivas(db=db).dados[0]
    assert (corrective.tape_center_record_id, corrective.center_unique_number) == (32220251, 40)
    assert (preventive.tape_center_record_id, preventive.center_unique_number) == (32220251, 40)
