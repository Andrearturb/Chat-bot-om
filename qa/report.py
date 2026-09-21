from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from qa.config import REPORTS_DIR

console = Console()


def write_report(report: dict[str, Any]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    latest_json = REPORTS_DIR / "latest.json"
    latest_md = REPORTS_DIR / "latest.md"
    latest_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")

    stamp_json = REPORTS_DIR / f"{timestamp}.json"
    stamp_md = REPORTS_DIR / f"{timestamp}.md"
    if not stamp_json.exists():
        stamp_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if not stamp_md.exists():
        stamp_md.write_text(render_markdown(report), encoding="utf-8")


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GENTILEZA QA",
        "",
        f"- Cenários: {report.get('scenarios', 0)}",
        f"- Passos: {report.get('steps', 0)}",
        f"- PASS: {report.get('pass_count', 0)}",
        f"- FAIL: {report.get('fail_count', 0)}",
        "",
    ]
    for item in report.get("results", []):
        status = "PASS" if item.get("passed") else "FAIL"
        lines.append(f"## {status} - {item.get('scenario', 'Sem cenário')}")
        if item.get("step_message"):
            lines.append(f"- Passo: {item['step_message']}")
        if item.get("layer"):
            lines.append(f"- Camada: {item['layer']}")
        if item.get("message"):
            lines.append(f"- Mensagem: {item['message']}")
        lines.append("")
    return "\n".join(lines)


def print_report(report: dict[str, Any]) -> None:
    console.print("[bold]GENTILEZA QA[/bold]")
    console.print("=" * 40)
    console.print(f"Cenários: {report.get('scenarios', 0)}")
    console.print(f"Passos: {report.get('steps', 0)}")
    console.print(f"[green]PASS: {report.get('pass_count', 0)}[/green]")
    console.print(f"[red]FAIL: {report.get('fail_count', 0)}[/red]")

    table = Table(show_header=False, box=None)
    table.add_column("Status")
    table.add_column("Cenário")
    for item in report.get("results", []):
        status = "PASS" if item.get("passed") else "FAIL"
        color = "green" if item.get("passed") else "red"
        table.add_row(f"[{color}]{status}[/{color}]", item.get("scenario", "Sem cenário"))
    console.print(table)
