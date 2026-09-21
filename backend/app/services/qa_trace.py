from __future__ import annotations

import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

_TRACE_STORE: dict[str, list[dict[str, Any]]] = defaultdict(list)
_TRACE_LOCK = threading.RLock()


def clear_qa_traces() -> None:
    with _TRACE_LOCK:
        _TRACE_STORE.clear()


def register_qa_trace(
    trace_id: str,
    sql: str,
    sql_validado: str,
    success: bool,
    row_count: int,
    truncated: bool = False,
    error: str | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    if not trace_id:
        return {}

    entry = {
        "sql": sql,
        "sql_validado": sql_validado,
        "success": success,
        "row_count": row_count,
        "truncated": truncated,
        "error": error,
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
    }

    with _TRACE_LOCK:
        _TRACE_STORE[trace_id].append(entry)
    return entry


def get_qa_trace(trace_id: str) -> list[dict[str, Any]] | None:
    with _TRACE_LOCK:
        trace = _TRACE_STORE.get(trace_id)
        if trace is None or not trace:
            return None
        return [dict(item) for item in trace]
