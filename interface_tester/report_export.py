from __future__ import annotations

import csv
from pathlib import Path


METADATA_COLUMNS = (
    "generated_at",
    "aircraft",
    "dat_path",
    "port",
    "baud_rate",
    "newline",
    "board_info",
    "detected_panel",
    "selected_panel",
    "light_filter",
    "output_filter",
    "intensity_mode",
    "auto_off",
    "response_wait_seconds",
    "response_quiet_seconds",
    "command_delay_seconds",
    "diagnostic_seconds",
)

RESULT_COLUMNS = (
    *METADATA_COLUMNS,
    "panel",
    "variants",
    "lights",
    "light_words",
    "inputs",
    "input_words",
    "outputs",
    "output_words",
    "result",
    "comment",
    "updated_at",
)

COMMAND_COLUMNS = (
    *METADATA_COLUMNS,
    "time",
    "status",
    "command",
    "response",
)

INPUT_COLUMNS = (
    *METADATA_COLUMNS,
    "time",
    "event",
    "word",
    "previous_word_value",
    "word_value",
    "changed_mask",
    "panel",
    "signal",
    "signal_type",
    "bits",
    "flags",
    "previous_raw",
    "raw",
    "previous_logical",
    "logical",
    "comment",
    "raw_line",
)


def write_report_csvs(
    report_path: Path,
    result_rows: list[dict[str, str]],
    command_history: list[dict[str, str]],
    input_history: list[dict[str, str]],
    metadata: dict[str, str],
) -> tuple[Path, Path, Path]:
    results_path = report_path.with_name(f"{report_path.stem}_results.csv")
    commands_path = report_path.with_name(f"{report_path.stem}_commands.csv")
    inputs_path = report_path.with_name(f"{report_path.stem}_inputs.csv")

    write_results_csv(results_path, result_rows, metadata)
    write_commands_csv(commands_path, command_history, metadata)
    write_inputs_csv(inputs_path, input_history, metadata)
    return results_path, commands_path, inputs_path


def write_results_csv(
    path: Path,
    result_rows: list[dict[str, str]],
    metadata: dict[str, str],
) -> Path:
    rows = []
    for row in result_rows:
        rows.append(
            {
                **metadata_row(metadata),
                "panel": row.get("panel", ""),
                "variants": row.get("variants", ""),
                "lights": row.get("lights", ""),
                "light_words": row.get("light_words", ""),
                "inputs": row.get("inputs", ""),
                "input_words": row.get("input_words", ""),
                "outputs": row.get("outputs", ""),
                "output_words": row.get("output_words", ""),
                "result": row.get("result", ""),
                "comment": row.get("comment", ""),
                "updated_at": row.get("updated_at", ""),
            }
        )
    _write_dict_csv(path, RESULT_COLUMNS, rows)
    return path


def write_commands_csv(
    path: Path,
    command_history: list[dict[str, str]],
    metadata: dict[str, str],
) -> Path:
    rows = []
    for event in command_history:
        rows.append(
            {
                **metadata_row(metadata),
                "time": event.get("time", ""),
                "status": event.get("status", ""),
                "command": event.get("command", ""),
                "response": event.get("response", ""),
            }
        )
    _write_dict_csv(path, COMMAND_COLUMNS, rows)
    return path


def write_inputs_csv(
    path: Path,
    input_history: list[dict[str, str]],
    metadata: dict[str, str],
) -> Path:
    rows = []
    for event in input_history:
        rows.append(
            {
                **metadata_row(metadata),
                "time": event.get("time", ""),
                "event": event.get("event", ""),
                "word": event.get("word", ""),
                "previous_word_value": event.get("previous_word_value", ""),
                "word_value": event.get("word_value", ""),
                "changed_mask": event.get("changed_mask", ""),
                "panel": event.get("panel", ""),
                "signal": event.get("signal", ""),
                "signal_type": event.get("signal_type", ""),
                "bits": event.get("bits", ""),
                "flags": event.get("flags", ""),
                "previous_raw": event.get("previous_raw", ""),
                "raw": event.get("raw", ""),
                "previous_logical": event.get("previous_logical", ""),
                "logical": event.get("logical", ""),
                "comment": event.get("comment", ""),
                "raw_line": event.get("raw_line", ""),
            }
        )
    _write_dict_csv(path, INPUT_COLUMNS, rows)
    return path


def metadata_row(metadata: dict[str, str]) -> dict[str, str]:
    return {
        column: metadata.get(column, "")
        for column in METADATA_COLUMNS
    }


def _write_dict_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
