"""
Agendador da sincronização da Tape.

Este módulo executa a importação em background em um intervalo fixo.
"""

from __future__ import annotations

import logging
import os
import threading

from app.db.session import SessionLocal
from app.integrations.tape_raw import APP_MANUTENCOES_CORRETIVAS
from app.services.importer import importar_servicos_tape


logger = logging.getLogger(__name__)


def _obter_intervalo_segundos() -> float:
    valor = os.getenv("TAPE_SYNC_INTERVAL_HOURS", "24")

    try:
        horas = float(valor)
    except ValueError:
        horas = 24.0

    return max(horas, 0.1) * 3600


def executar_sincronizacao_tape() -> None:
    """Executa uma sincronização única da Tape usando uma sessão própria."""
    db = SessionLocal()

    try:
        resultado = importar_servicos_tape(db=db, app_id=APP_MANUTENCOES_CORRETIVAS)
        logger.info(
            "Sincronização Tape concluída: %s registros, upload %s",
            resultado["total_rows"],
            resultado["upload_data"],
        )
    except Exception:
        db.rollback()
        logger.exception("Falha na sincronização agendada da Tape")
    finally:
        db.close()


class TapeSyncScheduler:
    """Gerencia o loop em background que agenda a sincronização da Tape."""

    def __init__(self, interval_seconds: float | None = None):
        self.interval_seconds = interval_seconds or _obter_intervalo_segundos()
        self.run_on_startup = os.getenv("TAPE_SYNC_RUN_ON_STARTUP", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="tape-sync-scheduler",
            daemon=True,
        )
        self._started = False

    def start(self) -> None:
        if self._started:
            return

        self._started = True
        self._thread.start()
        logger.info(
            "Agendador da Tape iniciado com intervalo de %.2f horas",
            self.interval_seconds / 3600,
        )

    def stop(self) -> None:
        if not self._started:
            return

        self._stop_event.set()
        self._thread.join(timeout=5)
        logger.info("Agendador da Tape finalizado")

    def _run(self) -> None:
        if not self.run_on_startup and self._stop_event.wait(self.interval_seconds):
            return

        while not self._stop_event.is_set():
            executar_sincronizacao_tape()

            if self._stop_event.wait(self.interval_seconds):
                break


def criar_agendador_tape() -> TapeSyncScheduler:
    """Fábrica simples para o scheduler da Tape."""
    return TapeSyncScheduler()