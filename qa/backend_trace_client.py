from __future__ import annotations

import json
from typing import Any

import requests

from qa.config import API_KEY, QA_BACKEND_URL


class BackendTraceClientError(RuntimeError):
    pass


def fetch_trace(qa_run_id: str) -> list[dict[str, Any]] | None:
    if not qa_run_id:
        return None

    url = f"{QA_BACKEND_URL.rstrip('/')}/chatbot/qa-traces/{qa_run_id}"
    response = requests.get(
        url,
        headers={"x-api-key": API_KEY},
        timeout=20,
    )

    if response.status_code == 404:
        return None
    response.raise_for_status()

    payload = response.json()
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return [payload]
    raise BackendTraceClientError("Resposta inesperada do backend de trace.")
