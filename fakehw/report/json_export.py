from pathlib import Path

from ..models.report import Report


def export_json(report: Report, path: str | Path) -> None:
    Path(path).write_text(report.to_json() + "\n", encoding="utf-8")
