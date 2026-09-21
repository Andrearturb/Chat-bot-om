from __future__ import annotations

import uuid
from typing import Any

import requests

from qa.config import QA_N8N_WEBHOOK_URL


class N8nClientError(RuntimeError):
    pass


def send_chat_message(*, chat_input: str, session_id: str | None = None, qa_run_id: str | None = None, timeout: float = 20.0) -> dict[str, Any]:
    payload = {
        "action": "sendMessage",
        "sessionId": session_id or str(uuid.uuid4()),
        "chatInput": chat_input,
        "qaMode": True,
        "qaRunId": qa_run_id or str(uuid.uuid4()),
    }

    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = requests.post(
                QA_N8N_WEBHOOK_URL,
                json=payload,
                timeout=timeout,
            )
            if response.status_code in {429, 500, 502, 503, 504}:
                raise requests.HTTPError(f"HTTP {response.status_code}")
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:  # pragma: no cover - retry only for transient HTTP
            last_error = exc
            if attempt >= 3:
                break
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= 3:
                break

    raise N8nClientError(f"Falha de comunicação com o n8n após retries: {last_error}")
