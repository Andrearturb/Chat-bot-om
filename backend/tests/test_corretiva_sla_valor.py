"""Testes dos campos de SLA, valor aprovado e status cru da manutenção corretiva."""

from decimal import Decimal
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.services.importer import converter_decimal, derivar_sla_atrasado


BADGE_ATRASADO = (
    '<div><div style="background-color:#ff0000;color: #fff;border: none;'
    'text-align: center;padding: 10px 20px;border-radius: 5px;font-size: 16px;'
    'width: 70px;height: 12px;">Atrasado</div></div>'
)


def test_sla_atrasado_vem_de_dentro_do_html():
    """A Tape devolve a marca como badge HTML, não como texto puro."""
    assert derivar_sla_atrasado(BADGE_ATRASADO) == "Atrasado"


def test_sla_atrasado_tolera_caixa_e_acento():
    assert derivar_sla_atrasado("<div>ATRASADO</div>") == "Atrasado"
    assert derivar_sla_atrasado("<div>atrasado</div>") == "Atrasado"
    assert derivar_sla_atrasado("Atrasado") == "Atrasado"


def test_sla_sem_marca_e_nulo():
    assert derivar_sla_atrasado(None) is None
    assert derivar_sla_atrasado("") is None
    assert derivar_sla_atrasado("<div></div>") is None
    assert derivar_sla_atrasado("<p>📦0 dia(s) passado(s) de 3 dia(s) - 0%</p>") is None


def test_valor_aprovado_converte_numero():
    assert converter_decimal("350") == Decimal("350")
    assert converter_decimal(150) == Decimal("150")
    assert converter_decimal("1.234,56") == Decimal("1234.56")


def test_valor_aprovado_zero_nao_vira_nulo():
    """338 registros da fotografia têm valor zero: zero é valor, não ausência."""
    assert converter_decimal(0) == Decimal("0")
    assert converter_decimal("0") == Decimal("0")


def test_valor_aprovado_ilegivel_e_nulo():
    assert converter_decimal(None) is None
    assert converter_decimal("") is None
    assert converter_decimal("sem valor") is None


from datetime import datetime

from app.integrations.transformar_chamados import TapeTransformer
from app.models.service import Service
from app.services.importer import extrair_campos_negocio, sincronizar_servicos
from tests.conftest import make_linha


def test_transformer_captura_campos_620293_e_613329():
    transformer = TapeTransformer()
    record = {
        "record_id": "abc",
        "app_record_id": "7000",
        "created_on": "2026-09-25T08:00:00Z",
        "fields": [
            {"field_id": 620293, "label": "  ", "values": [{"value": BADGE_ATRASADO}]},
            {"field_id": 613329, "label": "Valor Aprovado", "values": [{"value": "350"}]},
        ],
    }

    transformed = transformer.transformar_record(record)

    assert transformed["field_values"]["sla_late"]["field_id"] == 620293
    assert transformed["field_values"]["sla_late"]["value"] == BADGE_ATRASADO
    assert transformed["field_values"]["approved_value"]["value"] == "350"


def test_extrai_sla_valor_e_status_cru():
    campos = extrair_campos_negocio(
        make_linha(
            ticket="7001",
            status="Chamado Concluído",
            sla_late=BADGE_ATRASADO,
            approved_value="350",
        )
    )

    assert campos["sla_late"] == "Atrasado"
    assert campos["approved_value"] == Decimal("350")
    # O status cru preserva o texto da Tape; o canônico continua normalizado.
    assert campos["raw_status"] == "Chamado Concluído"
    assert campos["status"] == "Concluído"


def test_solicitacao_finalizada_mantem_cru_e_vira_concluido():
    campos = extrair_campos_negocio(
        make_linha(ticket="7002", status="Solicitação Finalizada")
    )

    assert campos["raw_status"] == "Solicitação Finalizada"
    assert campos["status"] == "Concluído"


def test_campos_novos_nulos():
    campos = extrair_campos_negocio(
        make_linha(ticket="7003", sla_late=None, approved_value=None)
    )

    assert campos["sla_late"] is None
    assert campos["approved_value"] is None


def test_persiste_e_atualiza_campos_novos(db, upload, agora):
    primeira = make_linha(
        ticket="7004", status="Chamado Concluído",
        sla_late=BADGE_ATRASADO, approved_value="350",
    )
    resultado = sincronizar_servicos(db, [primeira], upload.id, agora)
    db.flush()

    assert resultado["inserted"] == 1
    service = db.query(Service).filter_by(ticket="7004").one()
    assert service.sla_late == "Atrasado"
    assert service.approved_value == Decimal("350.00")
    assert service.raw_status == "Chamado Concluído"

    # Sai do atraso e o valor muda: os três campos entram na comparação.
    segunda = make_linha(
        ticket="7004", status="Solicitação Finalizada",
        sla_late=None, approved_value="420",
    )
    resultado = sincronizar_servicos(db, [segunda], upload.id, agora)
    db.flush()

    assert resultado["updated"] == 1
    db.refresh(service)
    assert service.sla_late is None
    assert service.approved_value == Decimal("420.00")
    assert service.raw_status == "Solicitação Finalizada"
