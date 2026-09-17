"""
Serviço de importação da Tape API — sincronização por diferenças.

Responsabilidades:
- Normalizar e tratar os campos recebidos da Tape;
- Comparar os dados transformados com o estado atual do banco;
- Inserir apenas registros novos;
- Atualizar apenas registros cujos campos de negócio mudaram;
- Nunca apagar registros existentes por ausência na resposta da API;
- Registrar contadores reais no Upload (inseridos, atualizados, sem mudança).

Chave de identidade: campo `ticket` (unique=True no modelo Service).
Campos comparados: todos os campos de negócio (ver CAMPOS_SINCRONIZADOS).
Campos excluídos da comparação: id, upload_id, synced_at.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.tape_raw import APP_MANUTENCOES_CORRETIVAS, TapeClient, carregar_token
from app.integrations.transformar_chamados import FIELD_ALIASES
from app.models.service import Service
from app.models.upload import Upload


logger = logging.getLogger(__name__)

BRASILIA_TZ = ZoneInfo("America/Sao_Paulo")

# Campos de negócio que participam da comparação de diferenças.
# Qualquer alteração nesta lista afeta o critério de "registro mudou".
CAMPOS_SINCRONIZADOS: tuple[str, ...] = (
    "status",
    "store_name",
    "bpcs_number",
    "sap_number",
    "praca",
    "service_description",
    "supplier",
    "visit_date",
    "solution_text",
    "signature_status",
    "signed_pdf_url",
    "created_on",
    "completion_date",
    "requester",
    "analyst_responsible",
    "non_approval_reason",
    "category",
    "subcategory",
)


# ---------------------------------------------------------------------------
# Normalização de campos
# ---------------------------------------------------------------------------

def normalizar_texto(valor: object) -> str | None:
    """
    Converte um valor para string limpa, removendo tags HTML se presentes.

    Retorna None se o valor for nulo, vazio ou apenas espaços.
    """
    if pd.isna(valor):
        return None

    texto = str(valor).strip()

    # Remove tags HTML (ex: <p>descrição</p> → descrição)
    texto = re.sub(r"<[^>]+>", " ", texto)

    # Colapsa espaços múltiplos gerados pela remoção das tags
    texto = re.sub(r"\s{2,}", " ", texto).strip()

    return texto or None


def converter_data(valor: object) -> datetime | None:
    """
    Converte um valor para datetime, quando possível.

    Retorna None se o valor estiver ausente ou não puder ser interpretado.
    """
    if pd.isna(valor):
        return None

    data_convertida = pd.to_datetime(valor, errors="coerce")

    if pd.isna(data_convertida):
        return None

    return data_convertida.to_pydatetime()


def limpar_nome_fornecedor(valor: object) -> str | None:
    """
    Remove CPF ou CNPJ do nome do fornecedor.

    Exemplos:
        'Fornecedor XPTO - CNPJ: 12.345.678/0001-90' → 'Fornecedor XPTO'
        'Maria da Silva - CPF: 123.456.789-00'        → 'Maria da Silva'
    """
    texto = normalizar_texto(valor)

    if texto is None:
        return None

    texto = re.sub(
        r"\s*[-|/]*\s*(CPF|CNPJ)\s*:\s*[\d./-]+",
        "",
        texto,
        flags=re.IGNORECASE,
    )

    return re.sub(r"\s{2,}", " ", texto).strip(" -|/") or None


def normalizar_praca(valor: object) -> str | None:
    """
    Normaliza a praça conforme as regras de negócio do projeto.

    Regras:
    - 'Escritório' original da planilha não é importado (retorna None);
    - 'Brasil' é exibido como 'Escritório' no sistema;
    - Demais valores são mantidos sem alteração.
    """
    praca = normalizar_texto(valor)

    if praca is None:
        return None

    praca_normalizada = praca.strip().lower()

    if praca_normalizada in {"escritório", "escritorio"}:
        return None  # Filtra "Escritório" original da planilha

    if praca_normalizada == "brasil":
        return "Escritório"  # Renomeia "Brasil" para "Escritório"

    return praca


def normalizar_status(status_original: object) -> str | None:
    """
    Mapeia o status original da Tape para os cinco status internos do sistema.

    Mapeamento:
    - "Em Aberto"                          → "Em Aberto"
    - "Em Atendimento"                     → "Em atendimento"
    - "Pendente Aprovação" / variações     → "Pendente de aprovação"
    - "Não Aprovado" / variações           → "Não Aprovado"
    - "Solicitação Finalizada"             → "Concluído"
    - "Chamado Concluído"                  → "Concluído"
    - Qualquer outro valor                 → preservado como recebido (sem inferência)

    Regras:
    - Não altera o status com base em supplier, visit_date ou qualquer outro campo.
    - Tolera diferenças de maiúsculas/minúsculas e espaços extras.
    - Valores desconhecidos são preservados, não classificados arbitrariamente.
    """
    status_limpo = normalizar_texto(status_original)

    if status_limpo is None:
        return None

    chave = status_limpo.strip().lower()

    # Finalizado / concluído
    if chave in {
        "solicitação finalizada",
        "solicitacao finalizada",
        "chamado concluído",
        "chamado concluido",
    }:
        return "Concluído"

    # Não aprovado
    if chave in {"não aprovado", "nao aprovado"}:
        return "Não Aprovado"

    # Pendente de aprovação — variações conhecidas da Tape
    if chave in {
        "pendente aprovação",
        "pendente aprovacao",
        "pendente de aprovação",
        "pendente de aprovacao",
    }:
        return "Pendente de aprovação"

    # Em atendimento
    if chave == "em atendimento":
        return "Em atendimento"

    # Em aberto
    if chave == "em aberto":
        return "Em Aberto"

    # Status desconhecido — preservar o valor original sem inferir
    return status_limpo


def tratar_local_atendimento(valor: object) -> dict[str, str | None]:
    """
    Extrai store_name, bpcs_number e sap_number do campo de local de atendimento.

    Formato esperado: 'NomeLoja | BCPS: 12345 | SAP: 6789'
    """
    texto = normalizar_texto(valor)

    if texto is None:
        return {"store_name": None, "bpcs_number": None, "sap_number": None}

    partes = [parte.strip() for parte in texto.split("|")]

    if len(partes) != 3:
        return {"store_name": texto, "bpcs_number": None, "sap_number": None}

    return {
        "store_name": partes[0] or None,
        "bpcs_number": partes[1].replace("BCPS:", "").strip() or None,
        "sap_number": partes[2].replace("SAP:", "").strip() or None,
    }


def tratar_status_assinatura(valor: object) -> dict[str, str | None]:
    """
    Extrai o status e a URL do PDF assinado do campo de assinatura.
    """
    texto = normalizar_texto(valor)

    if texto is None:
        return {"signature_status": None, "signed_pdf_url": None}

    try:
        dados = json.loads(texto)
    except json.JSONDecodeError:
        match = re.search(r'src=["\']([^"\']+)["\']', texto, flags=re.IGNORECASE)
        return {
            "signature_status": None,
            "signed_pdf_url": normalizar_texto(match.group(1)) if match else None,
        }

    if not isinstance(dados, list) or not dados:
        return {"signature_status": None, "signed_pdf_url": None}

    primeiro_item = dados[0]

    if not isinstance(primeiro_item, dict):
        return {"signature_status": None, "signed_pdf_url": None}

    signature_status = normalizar_texto(primeiro_item.get("status"))

    signed_pdf_url = (
        normalizar_texto(primeiro_item.get("url_pdf_assinado"))
        or normalizar_texto(primeiro_item.get("pdf_url"))
        or normalizar_texto(primeiro_item.get("url"))
    )

    return {"signature_status": signature_status, "signed_pdf_url": signed_pdf_url}


# ---------------------------------------------------------------------------
# Acesso ao payload da Tape
# ---------------------------------------------------------------------------

def obter_valor_campo(
    linha: dict[str, object],
    chave: str,
    field_id: int | None = None,
) -> object | None:
    """
    Extrai o valor de um campo do payload tratado da Tape.

    Suporta formato achatado e aninhado (field_values), com fallback por field_id.
    """
    field_values = linha.get("field_values")

    if isinstance(field_values, dict):
        valor_alias = field_values.get(chave)

        if isinstance(valor_alias, dict):
            if "value" in valor_alias:
                return valor_alias.get("value")
            if "text" in valor_alias:
                return valor_alias.get("text")

        if valor_alias is not None:
            return valor_alias

        chave_normalizada = re.sub(r"[^a-z0-9]+", "_", chave.strip().lower()).strip("_")

        for alias, valor in field_values.items():
            if re.sub(r"[^a-z0-9]+", "_", str(alias).strip().lower()).strip("_") != chave_normalizada:
                continue
            if isinstance(valor, dict):
                return valor.get("value") if "value" in valor else valor.get("text")
            return valor

    valor = linha.get(chave)

    if isinstance(valor, dict):
        if "value" in valor:
            return valor.get("value")
        if "text" in valor:
            return valor.get("text")

    if valor is not None:
        return valor

    if field_id is None:
        return None

    valor_tape = linha.get(str(field_id))

    if isinstance(valor_tape, dict):
        return valor_tape.get("value")

    return valor_tape


def obter_field_id_por_alias(alias: str) -> int | None:
    """Retorna o primeiro field_id canônico associado a um alias de negócio."""
    definicao = FIELD_ALIASES.get(alias)

    if not definicao:
        return None

    field_ids = definicao.get("field_ids") or []

    if not field_ids:
        return None

    primeiro = field_ids[0]

    return int(primeiro) if primeiro is not None else None


def converter_para_brasilia(valor: datetime | None) -> datetime | None:
    """Converte um datetime UTC ou naive para o fuso horário de Brasília."""
    if valor is None:
        return None

    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)

    return valor.astimezone(BRASILIA_TZ)


# ---------------------------------------------------------------------------
# Extração dos campos de negócio de uma linha transformada
# ---------------------------------------------------------------------------

def extrair_campos_negocio(linha: dict[str, object]) -> dict[str, Any]:
    """
    Extrai e normaliza todos os campos de negócio de uma linha transformada.

    Retorna um dicionário com os valores prontos para comparação e persistência.
    Não inclui campos internos (id, upload_id, synced_at).
    """
    location_data = tratar_local_atendimento(
        obter_valor_campo(linha, "raw_location", obter_field_id_por_alias("raw_location"))
    )
    signature_data = tratar_status_assinatura(
        obter_valor_campo(linha, "raw_signature", obter_field_id_por_alias("raw_signature"))
    )

    supplier = limpar_nome_fornecedor(
        obter_valor_campo(linha, "supplier", obter_field_id_por_alias("supplier"))
    )
    visit_date = converter_data(
        obter_valor_campo(linha, "visit_date", obter_field_id_por_alias("visit_date"))
    )
    status = normalizar_status(
        status_original=obter_valor_campo(linha, "status", obter_field_id_por_alias("status")),
    )

    created_on = converter_data(
        obter_valor_campo(linha, "created_on")
        or obter_valor_campo(linha, "created_at")
        or obter_valor_campo(linha, "created_date")
    )

    return {
        "status": status,
        "store_name": location_data["store_name"],
        "bpcs_number": location_data["bpcs_number"],
        "sap_number": location_data["sap_number"],
        "praca": normalizar_praca(
            obter_valor_campo(linha, "praca", obter_field_id_por_alias("praca"))
        ),
        "service_description": normalizar_texto(
            obter_valor_campo(linha, "service_description", obter_field_id_por_alias("service_description"))
        ),
        "supplier": supplier,
        "visit_date": visit_date,
        "solution_text": normalizar_texto(
            obter_valor_campo(linha, "solution_text", obter_field_id_por_alias("solution_text"))
        ),
        "signature_status": signature_data["signature_status"],
        "signed_pdf_url": signature_data["signed_pdf_url"],
        "created_on": created_on,
        "completion_date": converter_data(
            obter_valor_campo(linha, "completion_date", obter_field_id_por_alias("completion_date"))
        ),
        "requester": normalizar_texto(
            obter_valor_campo(linha, "requester", obter_field_id_por_alias("requester"))
        ),
        "analyst_responsible": normalizar_texto(
            obter_valor_campo(linha, "analyst_responsible", obter_field_id_por_alias("analyst_responsible"))
        ),
        "non_approval_reason": normalizar_texto(
            obter_valor_campo(linha, "non_approval_reason", obter_field_id_por_alias("non_approval_reason"))
        ),
        "category": normalizar_texto(
            obter_valor_campo(linha, "category", obter_field_id_por_alias("category"))
        ),
        "subcategory": normalizar_texto(
            obter_valor_campo(linha, "subcategory", obter_field_id_por_alias("subcategory"))
        ),
    }


# ---------------------------------------------------------------------------
# Comparação de campos — detecta diferenças reais entre origem e banco
# ---------------------------------------------------------------------------

def _normalizar_para_comparacao(valor: Any) -> Any:
    """
    Normaliza um valor para comparação estável entre banco e origem.

    Regras:
    - datetime com tzinfo diferente são comparados pelo timestamp UTC;
    - datetime naive são tratados como UTC;
    - demais tipos são comparados diretamente.
    """
    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            return valor.replace(microsecond=0)
        return valor.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0)
    return valor


def campos_mudaram(existente: Service, novos_campos: dict[str, Any]) -> bool:
    """
    Retorna True se algum campo de negócio do registro existente difere
    do valor transformado recebido da API.

    Compara apenas os campos em CAMPOS_SINCRONIZADOS.
    Não considera id, upload_id nem synced_at.
    """
    for campo in CAMPOS_SINCRONIZADOS:
        valor_banco = _normalizar_para_comparacao(getattr(existente, campo, None))
        valor_novo = _normalizar_para_comparacao(novos_campos.get(campo))

        if valor_banco != valor_novo:
            logger.debug(
                "Campo '%s' mudou no ticket %s: %r → %r",
                campo,
                existente.ticket,
                valor_banco,
                valor_novo,
            )
            return True

    return False


# ---------------------------------------------------------------------------
# Preparação de registros (sem gravar no banco)
# ---------------------------------------------------------------------------

def preparar_registro(
    linha: dict[str, object],
) -> tuple[str, dict[str, Any]] | None:
    """
    Extrai ticket e campos de negócio de uma linha transformada.

    Retorna None se a linha for inválida (sem ticket ou praça filtrada).
    Retorna (ticket, campos) para linhas válidas.
    """
    ticket = normalizar_texto(
        obter_valor_campo(linha, "ticket", obter_field_id_por_alias("ticket"))
    )

    if ticket is None:
        return None

    campos = extrair_campos_negocio(linha)

    # Praça None significa que a linha foi filtrada pelas regras de negócio
    if campos["praca"] is None:
        return None

    return ticket, campos


# ---------------------------------------------------------------------------
# Sincronização por diferenças — núcleo da lógica
# ---------------------------------------------------------------------------

def sincronizar_servicos(
    db: Session,
    registros_tratados: list[dict[str, Any]],
    upload_id: int,
    agora: datetime,
) -> dict[str, int]:
    """
    Aplica a sincronização por diferenças na sessão fornecida.

    Algoritmo:
    1. Prepara todos os registros válidos sem tocar no banco;
    2. Carrega em lote os registros existentes pelo conjunto de tickets;
    3. Para cada registro:
       - Novo: insere;
       - Existente com mudança: atualiza apenas os campos alterados;
       - Existente sem mudança: apenas atualiza synced_at (sem UPDATE nos campos de negócio);
    4. Persiste em uma única transação.

    Não apaga registros ausentes — ausência na resposta não é exclusão.

    Args:
        db:                Sessão do SQLAlchemy (sem commit — responsabilidade do chamador).
        registros_tratados: Lista de registros já transformados pelo TapeTransformer.
        upload_id:         ID do Upload de controle para esta execução.
        agora:             Timestamp UTC desta execução (mesmo valor para todos os registros).

    Returns:
        Dicionário com inserted, updated, unchanged, rejected.
    """
    # --- Fase 1: preparar registros sem tocar no banco ---
    preparados: list[tuple[str, dict[str, Any]]] = []
    rejeitados = 0

    for linha in registros_tratados:
        try:
            resultado = preparar_registro(linha)
            if resultado is None:
                rejeitados += 1
            else:
                preparados.append(resultado)
        except Exception:
            rejeitados += 1
            logger.exception("Erro ao preparar registro")

    if not preparados:
        logger.warning("Nenhum registro válido após preparação. Nenhuma escrita realizada.")
        return {"inserted": 0, "updated": 0, "unchanged": 0, "rejected": rejeitados}

    # --- Fase 2: carregar existentes em lote (uma única query) ---
    tickets_recebidos = [ticket for ticket, _ in preparados]

    # Garante que registros adicionados anteriormente na sessão estejam visíveis
    db.flush()

    existentes: dict[str, Service] = {
        row.ticket: row
        for row in db.execute(
            select(Service).where(Service.ticket.in_(tickets_recebidos))
        ).scalars()
    }

    # --- Fase 3: classificar e aplicar mudanças ---
    inserted = 0
    updated = 0
    unchanged = 0

    novos: list[Service] = []
    atualizados: list[Service] = []

    for ticket, campos in preparados:
        existente = existentes.get(ticket)

        if existente is None:
            # Registro novo — inserir
            novo = Service(
                ticket=ticket,
                upload_id=upload_id,
                synced_at=agora,
                **campos,
            )
            novos.append(novo)
            inserted += 1

        elif campos_mudaram(existente, campos):
            # Registro existente com diferença — atualizar apenas campos alterados
            for campo in CAMPOS_SINCRONIZADOS:
                setattr(existente, campo, campos[campo])
            existente.upload_id = upload_id
            existente.synced_at = agora
            atualizados.append(existente)
            updated += 1

        else:
            # Registro idêntico — só atualiza synced_at, sem tocar campos de negócio
            existente.synced_at = agora
            unchanged += 1

    # --- Fase 4: persistir em lote ---
    if novos:
        db.add_all(novos)

    # SQLAlchemy rastreia automaticamente os objetos modificados (dirty tracking)
    # não é necessário db.add() para os registros atualizados — já estão na sessão

    logger.info(
        "Sincronização preparada: %d inserções, %d atualizações, %d sem mudança, %d rejeitados",
        inserted, updated, unchanged, rejeitados,
    )

    return {
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "rejected": rejeitados,
    }


# ---------------------------------------------------------------------------
# Ponto de entrada público
# ---------------------------------------------------------------------------

def importar_servicos_tape(
    db: Session,
    app_id: int = APP_MANUTENCOES_CORRETIVAS,
    limit: int = 100,
    source_name: str | None = None,
) -> dict[str, object]:
    """
    Importa serviços diretamente da Tape API usando sincronização por diferenças.

    Fluxo:
    1. Coleta todos os registros da Tape (fora da transação de escrita);
    2. Valida que a coleta foi concluída com sucesso;
    3. Abre transação de escrita;
    4. Cria registro de Upload;
    5. Sincroniza por diferenças (insert/update condicional, sem delete);
    6. Atualiza contadores reais no Upload;
    7. Confirma a transação.

    Falha na coleta (erro HTTP, paginação incompleta, resposta vazia) não
    afeta o banco — a transação de escrita não é aberta.

    Args:
        db:          Sessão do SQLAlchemy.
        app_id:      ID do app na Tape.
        limit:       Registros por página na paginação.
        source_name: Nome descritivo da origem.

    Returns:
        Dicionário com message, total_rows, inserted, updated, unchanged,
        rejected, upload_data, source_file_name.

    Raises:
        RuntimeError: se o token não estiver configurado.
        httpx.HTTPError: se a coleta falhar.
    """
    import time

    t0 = time.monotonic()
    token = carregar_token()

    # --- Fase de coleta (fora da transação) ---
    logger.info("Iniciando coleta da Tape API (app_id=%s)", app_id)

    with TapeClient(token) as tape:
        registros_tratados = tape.get_records_tratados(app_id=app_id, limit=limit)

    t_coleta = time.monotonic() - t0
    total_recebidos = len(registros_tratados)

    logger.info(
        "Coleta concluída: %d registros em %.2fs",
        total_recebidos,
        t_coleta,
    )

    # Proteção: não iniciar escrita se a coleta retornou vazio
    # (pode indicar falha silenciosa na API ou problema de autenticação)
    if total_recebidos == 0:
        logger.warning(
            "Coleta retornou 0 registros. Escrita cancelada para preservar dados existentes."
        )
        return {
            "message": "Coleta retornou 0 registros. Banco preservado sem alterações.",
            "total_rows": 0,
            "inserted": 0,
            "updated": 0,
            "unchanged": 0,
            "rejected": 0,
            "upload_data": None,
            "source_file_name": source_name or f"Tape API - {app_id}",
        }

    # --- Fase de escrita (dentro da transação) ---
    agora = datetime.now(timezone.utc)

    upload = Upload(
        source_file_name=source_name or f"Tape API - {app_id}",
        total_rows=0,  # atualizado após sync
        inserted_count=0,
        updated_count=0,
        unchanged_count=0,
        rejected_count=0,
    )
    db.add(upload)
    db.flush()  # garante upload.id

    t1 = time.monotonic()

    contadores = sincronizar_servicos(
        db=db,
        registros_tratados=registros_tratados,
        upload_id=upload.id,
        agora=agora,
    )

    # Atualiza contadores reais no Upload
    upload.total_rows = contadores["inserted"] + contadores["updated"] + contadores["unchanged"]
    upload.inserted_count = contadores["inserted"]
    upload.updated_count = contadores["updated"]
    upload.unchanged_count = contadores["unchanged"]
    upload.rejected_count = contadores["rejected"]

    db.commit()
    db.refresh(upload)

    t_escrita = time.monotonic() - t1
    t_total = time.monotonic() - t0

    logger.info(
        "Sincronização concluída em %.2fs (coleta=%.2fs, escrita=%.2fs) | "
        "inseridos=%d atualizados=%d sem_mudança=%d rejeitados=%d",
        t_total,
        t_coleta,
        t_escrita,
        contadores["inserted"],
        contadores["updated"],
        contadores["unchanged"],
        contadores["rejected"],
    )

    return {
        "message": "Sincronização da Tape concluída com sucesso.",
        "total_rows": upload.total_rows,
        "inserted": upload.inserted_count,
        "updated": upload.updated_count,
        "unchanged": upload.unchanged_count,
        "rejected": upload.rejected_count,
        "upload_data": converter_para_brasilia(upload.uploaded_at),
        "source_file_name": upload.source_file_name,
    }
