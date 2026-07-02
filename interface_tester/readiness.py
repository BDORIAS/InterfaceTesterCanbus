from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass


READINESS_OK = "OK"
READINESS_WARNING = "Warning"
READINESS_INFO = "Info"


@dataclass(frozen=True)
class ReadinessCheck:
    area: str
    status: str
    message: str


def readiness_status_counts(checks: Iterable[ReadinessCheck]) -> dict[str, int]:
    counts = {
        READINESS_OK: 0,
        READINESS_WARNING: 0,
        READINESS_INFO: 0,
    }
    for check in checks:
        counts[check.status] = counts.get(check.status, 0) + 1
    return counts


def build_operational_status_text(
    metadata: Mapping[str, str],
    checks: Sequence[ReadinessCheck],
    sections: Mapping[str, Sequence[str]] | None = None,
) -> str:
    counts = readiness_status_counts(checks)
    warning_count = counts.get(READINESS_WARNING, 0)
    readiness = "Ready with warnings" if warning_count else "Ready"

    lines = [
        "# Interface Tester Operational Status",
        "",
        f"Readiness: {readiness}",
        f"OK: {counts.get(READINESS_OK, 0)}",
        f"Warnings: {warning_count}",
        f"Info: {counts.get(READINESS_INFO, 0)}",
        "",
        "## Metadata",
        "",
    ]

    for key, value in metadata.items():
        if value:
            lines.append(f"- {key}: {value}")

    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| Area | Status | Details |",
            "|---|---|---|",
        ]
    )
    for check in checks:
        lines.append(
            "| "
            f"{markdown_cell(check.area)} | "
            f"{markdown_cell(check.status)} | "
            f"{markdown_cell(check.message)} |"
        )

    if sections:
        for title, items in sections.items():
            lines.extend(["", f"## {title}", ""])
            if items:
                lines.extend(f"- {item}" for item in items)
            else:
                lines.append("No data.")

    lines.append("")
    return "\n".join(lines)


def markdown_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")
