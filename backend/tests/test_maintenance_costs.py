"""Importação FBL3N: identidade da loja, período e valores líquidos."""

from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook

from app.api.routes.maintenance_costs import list_maintenance_costs
from app.models.maintenance_cost import MaintenanceCost
from app.models.tape_center import TapeCenter
from app.models.upload import Upload
from app.services.maintenance_costs_importer import import_maintenance_costs, resolve_center


HEADERS = [
    "Conta do Razão", "Centro custo", "Data de lançamento", "Data do documento",
    "Montante em moeda interna", "Nº documento", "Chave de lançamento", "Divisão", "Nome 1", "Texto",
]


def workbook(*rows):
    book = Workbook()
    page = book.active
    page.append(HEADERS)
    for row in rows:
        page.append(row)
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


def center(db, record_id, cc, sap, status="Aberta"):
    item = TapeCenter(record_id=record_id, title=f"Loja {record_id}", name=f"Loja {record_id}",
                      cost_center=cc, sap_number=sap, status=status, upload_id=1)
    db.add(item)
    db.flush()
    return item


def test_atribuicao_respeita_centro_inteiro_e_ambiguidade(db, upload):
    centers = [
        center(db, 1, "402164027", "4027"),
        center(db, 2, "402114027", "4027", "Fechada"),
        center(db, 3, "402114027", "4027", "Fechada"),
        center(db, 4, "402124099", "4099"),
        center(db, 5, "40218A103", "A103"),
    ]
    assert resolve_center("402114027", centers) == (None, None)
    assert resolve_center("402164027", centers) == (1, "cost_center")
    assert resolve_center("402114099", centers) == (4, "sap_fallback")
    assert resolve_center("40218A103", centers) == (5, "cost_center")
    assert resolve_center("401100103", centers) == (None, None)
    centers.append(center(db, 6, "402114088", "4088", "Fechada"))
    assert resolve_center("402114088", centers) == (6, "cost_center")


def test_importacao_idempotente_periodos_e_valores(db, upload):
    center(db, 10, "402124099", "4099")
    jan = workbook(
        [41140014, "402114099", date(2026, 1, 5), date(2025, 12, 29), "1.234,56", "101", "81", "4099", "Fornecedor", "Serviço"],
        [41140014, "402114099", date(2026, 1, 8), None, "-34,56", "102", "91", "4099", "Fornecedor", "Estorno"],
        [41140014, "402114099", date(2026, 1, 8), None, "0,00", "103", "81", "4099", "Fornecedor", "Zero"],
        [41140014, "402114099", None, None, "5,00", "104", "81", "4099", "Fornecedor", "Rejeitado"],
    )
    first = import_maintenance_costs(db, jan, "janeiro.xlsx")
    db.commit()
    assert first["total_rows"] == 3 and first["rejected"] == 1
    rows = db.query(MaintenanceCost).order_by(MaintenanceCost.id).all()
    assert sum((row.amount for row in rows), Decimal()) == Decimal("1200.00")
    assert rows[0].posting_date == date(2026, 1, 5)
    assert rows[0].document_date == date(2025, 12, 29)
    assert rows[0].document_number == "101"
    assert rows[1].document_date is None
    assert all(row.tape_center_record_id == 10 and row.attribution_source == "sap_fallback" for row in rows)

    import_maintenance_costs(db, jan, "janeiro.xlsx")
    db.commit()
    assert db.query(MaintenanceCost).count() == 3
    preventive = workbook([41140026, "402124099", date(2026, 1, 12), None, 20, "201", "81", "4099", "Outro", "Preventiva"])
    import_maintenance_costs(db, preventive, "preventiva.xlsx")
    db.commit()
    assert db.query(MaintenanceCost).count() == 4
    feb = workbook([41140014, "402124099", date(2026, 2, 1), None, 5, "301", "81", "4099", "Outro", "Fevereiro"])
    import_maintenance_costs(db, feb, "fevereiro.xlsx")
    db.commit()
    assert db.query(MaintenanceCost).count() == 5


def test_leitura_ignora_upload_da_tape_mais_recente(db, upload):
    center(db, 10, "402124099", "4099")
    content = workbook([41140014, "402124099", date(2026, 1, 1), None, 12, "101", "81", "4099", "Fornecedor", "Texto"])
    import_maintenance_costs(db, content, "custos.xlsx")
    db.commit()
    expected = list_maintenance_costs(db).upload_data
    db.add(Upload(source_file_name="tape:57531", source_type=None, total_rows=0))
    db.commit()
    response = list_maintenance_costs(db)
    assert response.upload_data == expected
    assert response.dados[0].store_name == "Loja 10"
    assert response.dados[0].amount == 12


def test_planilha_sem_linhas_validas_preserva_mes(db, upload):
    center(db, 10, "402124099", "4099")
    valid = workbook([41140014, "402124099", date(2026, 1, 1), None, 12, "101", "81", "4099", "Fornecedor", "Texto"])
    import_maintenance_costs(db, valid, "valido.xlsx")
    db.commit()
    invalid = workbook([41140014, "402124099", None, None, 12, "101", "81", "4099", "Fornecedor", "Texto"])
    last_update = list_maintenance_costs(db).upload_data
    result = import_maintenance_costs(db, invalid, "invalido.xlsx")
    db.commit()
    assert result["total_rows"] == 0 and result["rejected"] == 1
    assert db.query(MaintenanceCost).count() == 1
    assert list_maintenance_costs(db).upload_data == last_update
