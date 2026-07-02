from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .serial_diagnostics import SerialTraceEvent
from .session_results import PanelResult, make_panel_result


SESSION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class TestSession:
    saved_at: str
    dat_path: str = ""
    aircraft_name: str = ""
    panel_results: dict[str, PanelResult] = field(default_factory=dict)
    command_history: list[dict[str, str]] = field(default_factory=list)
    input_history: list[dict[str, str]] = field(default_factory=list)
    input_word_values: dict[int, int] = field(default_factory=dict)
    serial_trace_events: list[SerialTraceEvent] = field(default_factory=list)
    serial_trace_discarded_count: int = 0
    report_result: str = "Not tested"
    report_comment: str = ""
    current_result_key: str = ""
    detected_panel_name: str = ""
    board_info_text: str = "Board: no information"
    light_filter: str = "all"
    output_filter: str = "all"
    intensity_mode: str = "raw_ff"
    duration_seconds: float = 1.0
    response_wait_seconds: float = 1.2
    response_quiet_seconds: float = 0.25
    command_delay_seconds: float = 0.05
    diagnostic_seconds: float = 2.0
    auto_off: bool = True
    display_word: str = "38"
    display_text: str = "105435"


def save_test_session(session: TestSession, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SESSION_SCHEMA_VERSION,
        **asdict(session),
    }
    payload["panel_results"] = {
        key: asdict(value)
        for key, value in sorted(session.panel_results.items())
    }
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)
    return path


def load_test_session(path: Path) -> TestSession:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"Could not read the session: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("The session file does not contain a valid JSON object.")

    schema_version = data.get("schema_version")
    if schema_version != SESSION_SCHEMA_VERSION:
        raise ValueError(f"Unsupported session version: {schema_version!r}")

    return test_session_from_mapping(data)


def test_session_from_mapping(data: dict[str, Any]) -> TestSession:
    panel_results = _load_panel_results(data.get("panel_results"))
    return TestSession(
        saved_at=_coerce_string(data.get("saved_at")),
        dat_path=_coerce_string(data.get("dat_path")),
        aircraft_name=_coerce_string(data.get("aircraft_name")),
        panel_results=panel_results,
        command_history=_load_command_history(data.get("command_history")),
        input_history=_load_input_history(data.get("input_history")),
        input_word_values=_load_input_word_values(data.get("input_word_values")),
        serial_trace_events=_load_serial_trace_events(data.get("serial_trace_events")),
        serial_trace_discarded_count=max(0, _coerce_int(data.get("serial_trace_discarded_count")) or 0),
        report_result=_coerce_string(data.get("report_result"), "Not tested"),
        report_comment=_coerce_string(data.get("report_comment")),
        current_result_key=_coerce_string(data.get("current_result_key")),
        detected_panel_name=_coerce_string(data.get("detected_panel_name")),
        board_info_text=_coerce_string(data.get("board_info_text"), "Board: no information"),
        light_filter=_coerce_string(data.get("light_filter"), "all"),
        output_filter=_coerce_string(data.get("output_filter"), "all"),
        intensity_mode=_coerce_string(data.get("intensity_mode"), "raw_ff"),
        duration_seconds=_coerce_float(data.get("duration_seconds"), 1.0),
        response_wait_seconds=_coerce_float(data.get("response_wait_seconds"), 1.2),
        response_quiet_seconds=_coerce_float(data.get("response_quiet_seconds"), 0.25, allow_zero=True),
        command_delay_seconds=_coerce_float(data.get("command_delay_seconds"), 0.05, allow_zero=True),
        diagnostic_seconds=_coerce_float(data.get("diagnostic_seconds"), 2.0),
        auto_off=bool(data.get("auto_off", True)),
        display_word=_coerce_string(data.get("display_word"), "38"),
        display_text=_coerce_string(data.get("display_text"), "105435"),
    )


def _load_panel_results(value: Any) -> dict[str, PanelResult]:
    if not isinstance(value, dict):
        return {}
    results: dict[str, PanelResult] = {}
    for key, result_data in value.items():
        if not isinstance(result_data, dict):
            continue
        results[str(key)] = make_panel_result(
            target=_coerce_string(result_data.get("target"), str(key)),
            result=_coerce_string(result_data.get("result"), "Not tested"),
            comment=_coerce_string(result_data.get("comment")),
            updated_at=_coerce_string(result_data.get("updated_at")) or None,
        )
    return results


def _load_command_history(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    history: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        response = _coerce_string(item.get("response"))
        history.append(
            {
                "time": _coerce_string(item.get("time")),
                "status": _coerce_string(item.get("status"), "OK" if response.strip() else "No response"),
                "command": _coerce_string(item.get("command")),
                "response": response,
            }
        )
    return history


def _load_input_history(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    fields = (
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
    history: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        history.append({
            field: _coerce_string(item.get(field))
            for field in fields
        })
    return history


def _load_input_word_values(value: Any) -> dict[int, int]:
    if not isinstance(value, dict):
        return {}
    word_values: dict[int, int] = {}
    for raw_word, raw_value in value.items():
        word = _coerce_int(raw_word)
        word_value = _coerce_int(raw_value)
        if word is None or word_value is None:
            continue
        if word < 0 or word_value < 0:
            continue
        word_values[word] = word_value & 0xFFFF
    return word_values


def _load_serial_trace_events(value: Any) -> list[SerialTraceEvent]:
    if not isinstance(value, list):
        return []
    events: list[SerialTraceEvent] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        events.append(
            SerialTraceEvent(
                time=_coerce_string(item.get("time")),
                direction=_coerce_string(item.get("direction")),
                source=_coerce_string(item.get("source")),
                text=_coerce_string(item.get("text")),
                hex_data=_coerce_string(item.get("hex_data")),
            )
        )
    return events


def _coerce_string(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text, 0)
        except ValueError:
            try:
                return int(text, 16)
            except ValueError:
                return None
    return None


def _coerce_float(value: Any, default: float, *, allow_zero: bool = False) -> float:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return default
    if allow_zero:
        return converted if converted >= 0 else default
    return converted if converted > 0 else default
