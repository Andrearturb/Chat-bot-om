from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

"""Transformações de payload da Tape API para um JSON padronizado."""


JsonDict = dict[str, Any]
JsonList = list[JsonDict]


FIELDS_REFERENCE: list[int] = [
    580427,  # Imagem
    580430,  # Ticket
    580431,  # Origem
    580436,  # Requisitante
    580441,  # Local de Atendimento
    580450,  # Praça
    580453,  # Status
    580455,  # Feedback do aprovador
    601507,  # lojasList
    601597,  # Categoria
    601598,  # Subcategoria
    603181,  # --infromação prestador-- tag
    603182,  # --tratativa do chamado--tag
    603575,  # Fornecedor
    603645,  # Analista Responsável
    603651,  # Mau uso?
    604384,  # -- data de criação--  
    604414,  # Progresso do SLA
    607968,  # Recorrente
    608283,  # Valor do Saving
    609863,  # Descrição da Requisição
    612795,  # Alçadas
    613329,  # Valor Aprovado
    613642,  # feriados
    613694,  # --Data limite de execução
    613992,  # prazo
    614601,  # Data da Conclusão
    615144,  # diasUteisPassados
    615173,  # Relation
    615596,  # data de conclusão
    615963,  # Minutos Desconsiderados no Sla
    616075,  # dict_sla_desconsiderado
    617018,  # campoAux
    617147,  # Retorno de Alçadas
    617148,  # FeedBack do Aprovador
    617502,  # Motivo da Não Aprovação
    620293,  # 
    620444,  # Email Requisitante
    621026,  # Replicar Para Segurança
    621046,  # Informações do Prestador de Serviço
    622874,  # Data da Visita
    623224,  # Solução
    623225,  # Tikcket
    631827,  # Código do Ar Condicionado
    638539,  # Descrição do Serviço
    645360,  # CNPJ_LOJA
    645362,  # CPF-CNPJ_FORNECEDOR
    645364,  # GERENTE_RESPONSAVEL_LOJA
    645385,  # telefone_fornecedor
    645386,  # email_fornecedor
    645424,  # email_loja
    645460,  # email_gerente_gvo
    645882,  # Enviar ordem de manutenção?
    645992,  # Status da Assinatura
    645994,  # Status da ordem de serviço
    649329,  # endereço_loja
    649491,  # PDF_VIEW
    649503,  # Valor do serviço informado pelo prestador
    669126,  # NovoDiasUteisPassados
    671058,  # Categoria
    671061,  # Subcategoria
    672025,  # historicoAtendimentos
    672411,  # array_de_registros
    672479,  # data_inicio_atendimento
    672581,  # 
    675033,  # diasUteisPassadosEmAberto
    679847,  # 
    726602,  # Email do Setor do Solicitante (Escritório)
    726684,  # Setor
]

FIELD_ALIASES: dict[str, dict[str, Any]] = {
    "ticket": {
        "field_ids": [623225, 580430],
        "labels": ["Tikcket", "Ticket"],
    },
    "status": {
        "field_ids": [580453],
        "labels": ["Status"],
    },
    "raw_location": {
        "field_ids": [580441],
        "labels": ["Local de Atendimento"],
    },
    "praca": {
        "field_ids": [580450],
        "labels": ["Praça", "Praca"],
    },
    "service_description": {
        "field_ids": [638539],
        "labels": ["Descrição do Serviço", "Descricao do Servico"],
    },
    "supplier": {
        "field_ids": [603575],
        "labels": ["Fornecedor"],
    },
    "visit_date": {
        "field_ids": [622874],
        "labels": ["Data da Visita"],
    },
    "solution_text": {
        "field_ids": [623224],
        "labels": ["Solução", "Solucao"],
    },
    "raw_signature": {
        "field_ids": [645992],
        "labels": ["Status da Assinatura"],
    },
    "completion_date": {
        "field_ids": [615596],
        "labels": ["Data de conclusão", "Data da Conclusão"],
    },
}


def normalizar_chave(valor: str | None) -> str | None:
    if valor is None:
        return None

    chave = re.sub(r"[^a-z0-9]+", "_", valor.strip().lower())
    chave = chave.strip("_")

    return chave or None


def construir_indice_aliases() -> dict[int, str]:
    indice: dict[int, str] = {}

    for alias, definicao in FIELD_ALIASES.items():
        for field_id in definicao.get("field_ids", []):
            indice[field_id] = alias

        for label in definicao.get("labels", []):
            chave = normalizar_chave(label)

            if chave is not None:
                indice[chave] = alias

    return indice


FIELD_ALIAS_INDEX = construir_indice_aliases()


class TapeTransformer:
    """Normaliza registros da Tape em uma estrutura previsível para BI/integrações."""

    def __init__(self, reference_fields: list[int] | None = None):
        """Define lista de campos esperados para completar chaves ausentes."""
        self.reference_fields = reference_fields or FIELDS_REFERENCE.copy()

    def extrair_registros(self, dados: Any) -> JsonList:
        """Aceita múltiplos formatos de entrada e retorna apenas registros válidos."""
        if isinstance(dados, dict) and isinstance(dados.get("records"), list):
            return dados["records"]

        if isinstance(dados, dict):
            return [dados]

        if isinstance(dados, list):
            return [item for item in dados if isinstance(item, dict)]

        return []

    def normalizar_valor(self, valor: Any) -> Any:
        """Converte valores complexos da API para tipos simples serializáveis."""
        if isinstance(valor, list):
            return [self.normalizar_valor(item) for item in valor]

        if isinstance(valor, dict):
            if "file_id" in valor:
                # Arquivos retornam metadados úteis para download e auditoria.
                return {
                    "file_id": valor.get("file_id"),
                    "name": valor.get("name"),
                    "url": valor.get("download_url") or valor.get("link") or valor.get("view_url"),
                    "mimetype": valor.get("mimetype"),
                    "size": valor.get("size"),
                }

            if "text" in valor:
                return valor["text"]

            if "title" in valor:
                return valor["title"]

            if "name" in valor:
                return valor["name"]

            if "start_date" in valor:
                return valor["start_date"]

            if "start" in valor:
                return valor["start"]

            if "start_date_utc" in valor:
                return valor["start_date_utc"]

            if "start_utc" in valor:
                return valor["start_utc"]

            if "value" in valor:
                # Alguns campos aninham valor real dentro da chave "value".
                return self.normalizar_valor(valor["value"])

        return valor

    def extrair_valor_campo(self, campo: JsonDict) -> Any:
        """Extrai o primeiro valor do campo, padrão de payload da Tape API."""
        valores = campo.get("values") or []

        if not valores:
            return None

        primeiro_item = valores[0]

        if isinstance(primeiro_item, dict) and "value" in primeiro_item:
            return self.normalizar_valor(primeiro_item["value"])

        return self.normalizar_valor(primeiro_item)

    def transformar_record(self, record: JsonDict) -> JsonDict:
        """Transforma um registro bruto em objeto de saída com metadados e campos.

        Além dos campos (fields), extrai metadados do nível raiz do record:
        - created_on: data de criação do chamado na Tape.
        """
        objeto: JsonDict = {
            "record_id": record.get("record_id"),
            "record_url": record.get("record_url"),
            "ticket": record.get("app_record_id"),
            # Extrai a data de criação do nível raiz do record (metadado da Tape)
            "created_on": (
                record.get("created_on")
                or record.get("creation_date")
                or record.get("created_at")
            ),
            "field_values": {},
        }

        for campo in record.get("fields", []):
            field_id = campo.get("field_id")

            if field_id is None:
                continue

            label = campo.get("label")
            valor = self.extrair_valor_campo(campo)

            entrada = {
                "field_id": field_id,
                "label": label,
                "value": valor,
            }

            objeto[str(field_id)] = entrada

            alias = FIELD_ALIAS_INDEX.get(field_id)

            if alias is None:
                alias = FIELD_ALIAS_INDEX.get(normalizar_chave(label))

            if alias is not None:
                objeto["field_values"][alias] = entrada

        self.completar_campos_ausentes(objeto)

        return objeto

    def completar_campos_ausentes(self, objeto: JsonDict) -> None:
        """Garante schema estável preenchendo campos de referência não recebidos."""
        for field_id in self.reference_fields:
            key = str(field_id)

            if key not in objeto:
                objeto[key] = {
                    "label": None,
                    "value": None,
                    "field_id": field_id,
                }

        field_values = objeto.setdefault("field_values", {})

        for alias, definicao in FIELD_ALIASES.items():
            if alias in field_values:
                continue

            field_id = next(iter(definicao.get("field_ids", [])), None)

            field_values[alias] = {
                "field_id": field_id,
                "label": definicao.get("labels", [None])[0],
                "value": None,
            }

    def transformar_dados(self, dados: Any) -> JsonList:
        """Transforma uma coleção (ou registro único) para lista de objetos tratados."""
        registros = self.extrair_registros(dados)
        return [self.transformar_record(record) for record in registros]

    def transformar_arquivo(self, entrada: Path, saida: Path) -> JsonList:
        """Lê JSON de entrada, transforma e persiste no caminho de saída."""
        dados = json.loads(entrada.read_text(encoding="utf-8"))
        tratados = self.transformar_dados(dados)

        saida.parent.mkdir(parents=True, exist_ok=True)
        saida.write_text(
            json.dumps(tratados, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return tratados