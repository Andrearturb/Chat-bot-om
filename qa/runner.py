from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from qa.config import DATABASE_URL, QA_BACKEND_URL, QA_N8N_WEBHOOK_URL
from qa.database_client import execute_oracle_query
from qa.models import Scenario, ScenarioStep
from qa.report import print_report, write_report


def _load_scenarios() -> list[Scenario]:
    scenario_dir = Path(__file__).resolve().parent / "scenarios"
    scenarios: list[Scenario] = []
    for path in sorted(scenario_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            steps = []
            for step in payload.get("steps", []):
                oracle = step.get("oracle")
                steps.append(
                    ScenarioStep(
                        message=step.get("message", ""),
                        expected_state=step.get("expected_state"),
                        must_be_null=step.get("must_be_null", []),
                        oracle=None if oracle is None else type("O", (), {"type": oracle.get("type"), "sql": oracle.get("sql"), "max_asserted_tickets": oracle.get("max_asserted_tickets")})(),
                        max_asserted_tickets=step.get("max_asserted_tickets"),
                    )
                )
            scenarios.append(
                Scenario(
                    id=payload.get("id", path.stem),
                    name=payload.get("name", path.stem),
                    category=payload.get("category"),
                    steps=steps,
                )
            )
    return scenarios


def _run() -> int:
    parser = argparse.ArgumentParser(description="QA Gentileza")
    parser.add_argument("--scenario", dest="scenario")
    parser.add_argument("--category", dest="category")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    scenarios = _load_scenarios()
    if args.scenario:
        scenarios = [item for item in scenarios if item.id == args.scenario or item.name == args.scenario]
    if args.category:
        scenarios = [item for item in scenarios if item.category == args.category]

    report = {
        "scenarios": len(scenarios),
        "steps": sum(len(item.steps) for item in scenarios),
        "pass_count": 0,
        "fail_count": 0,
        "results": [],
    }

    for scenario in scenarios:
        for step in scenario.steps:
            result = {
                "scenario": scenario.name,
                "step_message": step.message,
                "passed": True,
                "layer": None,
                "message": "OK",
            }
            if args.verbose:
                print(f"[QA] {scenario.name} :: {step.message}")
            if step.oracle is not None:
                try:
                    oracle = execute_oracle_query(step.oracle.sql)
                    result["oracle_rows"] = oracle["rows"]
                except Exception as exc:  # pragma: no cover - placeholder runner
                    result["passed"] = False
                    result["layer"] = "DATABASE_QUERY"
                    result["message"] = f"Erro no oráculo: {exc}"
            if result["passed"]:
                report["pass_count"] += 1
            else:
                report["fail_count"] += 1
            report["results"].append(result)

    print_report(report)
    write_report(report)
    return 0 if report["fail_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_run())
