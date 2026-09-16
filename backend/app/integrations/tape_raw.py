"""
Cliente HTTP para a Tape API.

Este módulo é responsável por buscar e transformar registros da Tape API.
Expõe o `TapeClient` para uso pelo serviço de importação e pelo scheduler.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Final, TypeVar

import httpx

from app.integrations.transformar_chamados import TapeTransformer, FIELDS_REFERENCE


BASE_URL: Final[str] = "https://api.tapeapp.com/v1"

# ID do app de Manutenções Corretivas na Tape
APP_MANUTENCOES_CORRETIVAS: Final[int] = 57531

T = TypeVar("T")


class TapeClient:
    """Cliente HTTP para leitura e transformação de registros da Tape API."""

    def __init__(self, token: str, base_url: str = BASE_URL, timeout: int = 30):
        """Inicializa o cliente com autenticação Bearer e timeout padrão."""
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        # connect: tempo para estabelecer a conexão TCP
        # read: tempo para receber a resposta (APIs com muitos registros podem demorar)
        # write/pool: mantidos conservadores
        self.client = httpx.Client(
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)
        )

    def close(self) -> None:
        """Fecha as conexões abertas do cliente HTTP."""
        self.client.close()

    def __enter__(self) -> "TapeClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def get_record(self, record_id: int) -> dict[str, Any]:
        """Busca um registro bruto pelo seu identificador interno."""
        response = self.client.get(
            f"{self.base_url}/record/{record_id}",
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    def get_records_by_app(self, app_id: int, limit: int = 100) -> dict[str, list[dict[str, Any]]]:
        """
        Extrai todos os registros de um app com paginação por cursor.

        Itera automaticamente até esgotar todas as páginas disponíveis.
        Respeita o rate limit da Tape API via retry com backoff em caso de 429.
        """
        import time

        all_records: list[dict[str, Any]] = []
        cursor: str | None = None
        max_retries = 5

        while True:
            params: dict[str, Any] = {"limit": limit}
            if cursor:
                params["cursor"] = cursor

            # Retry com backoff exponencial para lidar com rate limiting (429)
            for attempt in range(max_retries):
                response = self.client.get(
                    f"{self.base_url}/record/app/{app_id}",
                    headers=self.headers,
                    params=params,
                )

                if response.status_code == 429:
                    # Respeita o header Retry-After se presente, senão usa backoff
                    retry_after = response.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else (2 ** attempt)
                    time.sleep(wait)
                    continue

                response.raise_for_status()
                break
            else:
                # Esgotou as tentativas — lança o último erro recebido
                response.raise_for_status()

            payload = response.json()

            records = payload.get("records") or []
            if not isinstance(records, list) or not records:
                break

            all_records.extend(record for record in records if isinstance(record, dict))
            cursor = payload.get("cursor")

            # Pausa mínima entre páginas para evitar disparar o rate limit
            if cursor:
                time.sleep(0.3)

        return {"records": all_records}

    def get_records_tratados(
        self,
        app_id: int,
        limit: int = 100,
        reference_fields: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Busca todos os registros de um app e normaliza o payload para consumo local."""
        dados_brutos = self.get_records_by_app(app_id=app_id, limit=limit)

        transformer = TapeTransformer(
            reference_fields=reference_fields or FIELDS_REFERENCE,
        )

        return transformer.transformar_dados(dados_brutos)

    def get_record_tratado(
        self,
        record_id: int,
        reference_fields: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Busca um único registro e aplica a transformação padronizada."""
        dado_bruto = self.get_record(record_id)

        transformer = TapeTransformer(
            reference_fields=reference_fields or FIELDS_REFERENCE,
        )

        return transformer.transformar_dados(dado_bruto)

    def consumir_objeto_tratado(
        self,
        objeto_tratado: list[dict[str, Any]],
        consumidor: Callable[[list[dict[str, Any]]], T],
    ) -> T:
        """Encaminha o objeto tratado para uma função consumidora arbitrária."""
        return consumidor(objeto_tratado)


def carregar_token() -> str:
    """
    Lê o token da Tape API via variável de ambiente.

    Lança RuntimeError explicitamente se a variável não estiver definida,
    para evitar falhas silenciosas durante a sincronização.
    """
    token = os.getenv("TAPE_API_TOKEN")

    if not token:
        raise RuntimeError("TAPE_API_TOKEN não encontrado no ambiente")

    return token
