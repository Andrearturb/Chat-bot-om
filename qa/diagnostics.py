from __future__ import annotations

from typing import Any


FAILURE_CATEGORIES = {
    "INFRASTRUCTURE",
    "INTERPRETER",
    "PERSISTENCE",
    "MERGE",
    "AI_AGENT_SQL",
    "DATABASE_QUERY",
    "ASSISTANT_RESPONSE",
    "UNKNOWN",
}


def classify_failure(*, webhook_failed: bool = False, interpretation_ok: bool | None = None, previous_state: dict[str, Any] | None = None, final_state: dict[str, Any] | None = None, expected_state: dict[str, Any] | None = None, sql_ok: bool | None = None, sql_result_ok: bool | None = None, assistant_ok: bool | None = None, **_: str) -> str:
    if webhook_failed:
        return "INFRASTRUCTURE"
    if interpretation_ok is False:
        return "INTERPRETER"
    if previous_state is not None and final_state is not None and expected_state is not None:
        prev = previous_state.get("statuses") if isinstance(previous_state, dict) else None
        final = final_state.get("statuses") if isinstance(final_state, dict) else None
        if prev is not None and final is None and isinstance(expected_state, dict):
            return "PERSISTENCE"
    if interpretation_ok is True and final_state is not None and expected_state is not None and not final_state == expected_state:
        return "MERGE"
    if sql_ok is False:
        return "AI_AGENT_SQL"
    if sql_result_ok is False:
        return "DATABASE_QUERY"
    if assistant_ok is False:
        return "ASSISTANT_RESPONSE"
    return "UNKNOWN"
