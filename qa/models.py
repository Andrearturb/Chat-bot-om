from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OracleSpec:
    type: str
    sql: str
    max_asserted_tickets: int | None = None


@dataclass
class ScenarioStep:
    message: str
    expected_state: dict[str, Any] | None = None
    must_be_null: list[str] = field(default_factory=list)
    oracle: OracleSpec | None = None
    max_asserted_tickets: int | None = None


@dataclass
class Scenario:
    id: str
    name: str
    category: str | None = None
    steps: list[ScenarioStep] = field(default_factory=list)
