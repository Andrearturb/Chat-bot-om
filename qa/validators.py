from __future__ import annotations

import re
from typing import Any


def normalize_statuses(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value.strip()} if value.strip() else set()
    if isinstance(value, list):
        items = []
        for item in value:
            if isinstance(item, str):
                item = item.strip()
            if item is not None and str(item).strip():
                items.append(str(item).strip())
        return set(items)
    if isinstance(value, tuple):
        return normalize_statuses(list(value))
    if isinstance(value, set):
        return {str(item).strip() for item in value if str(item).strip()}
    return {str(value).strip()} if str(value).strip() else set()


def compare_expected_state(expected: dict[str, Any] | None, actual: dict[str, Any] | None) -> tuple[bool, str | None]:
    if expected is None:
        return True, None
    if actual is None:
        return False, "estado real ausente"

    for key, expected_value in expected.items():
        actual_value = actual.get(key)
        if key == "statuses":
            expected_set = normalize_statuses(expected_value)
            actual_set = normalize_statuses(actual_value)
            if expected_set != actual_set:
                return False, f"statuses esperado={sorted(expected_set)} encontrado={sorted(actual_set)}"
            continue
        if key in {"group_by", "limit", "date_field", "year", "month", "praca", "store_name", "category", "subcategory", "missing_field", "event", "location_term"}:
            if actual_value != expected_value:
                return False, f"{key} esperado={expected_value!r} encontrado={actual_value!r}"
            continue
        if actual_value != expected_value:
            return False, f"{key} esperado={expected_value!r} encontrado={actual_value!r}"
    return True, None


def compare_must_be_null(actual: dict[str, Any] | None, fields: list[str]) -> tuple[bool, str | None]:
    if actual is None:
        return True, None
    for field_name in fields:
        if field_name in actual and actual[field_name] is not None:
            return False, f"campo {field_name} deveria ser nulo, encontrado={actual[field_name]!r}"
    return True, None


def parse_count_from_response(text: str) -> int | None:
    numbers = re.findall(r"(?<!\d)(\d+)(?!\d)", text or "")
    if not numbers:
        return None
    return int(numbers[0])


def validate_count_result(expected_total: int, response_text: str) -> tuple[bool, str | None]:
    found = parse_count_from_response(response_text)
    if found is None:
        return False, f"não foi possível localizar o número {expected_total} na resposta"
    if found != expected_total:
        return False, f"valor esperado={expected_total} encontrado={found}"
    return True, None


def validate_tickets_result(expected_ticket_numbers: list[str], response_text: str, max_asserted_tickets: int | None = None) -> tuple[bool, str | None]:
    normalized_expected = [str(ticket).strip() for ticket in expected_ticket_numbers if str(ticket).strip()]
    if max_asserted_tickets is not None and max_asserted_tickets > 0:
        normalized_expected = normalized_expected[:max_asserted_tickets]

    missing = [ticket for ticket in normalized_expected if ticket not in (response_text or "")]
    if missing:
        return False, f"tickets esperados ausentes: {missing}"
    return True, None
