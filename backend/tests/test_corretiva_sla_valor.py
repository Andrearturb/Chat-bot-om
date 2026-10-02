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
