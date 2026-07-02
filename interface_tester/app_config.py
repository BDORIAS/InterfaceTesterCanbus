from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


APP_NAME = "InterfaceTester"
CONFIG_FILE_NAME = "settings.json"


@dataclass(frozen=True)
class AppSettings:
    last_dat_path: str = ""
    last_definition_dir: str = ""
    serial_port: str = ""
    baud_rate: str = "115200"
    newline: str = "CR"
    intensity_mode: str = "raw_ff"
    light_filter: str = "all"
    output_filter: str = "all"
    duration_seconds: float = 1.0
    response_wait_seconds: float = 1.2
    response_quiet_seconds: float = 0.25
    command_delay_seconds: float = 0.05
    diagnostic_seconds: float = 2.0
    auto_off: bool = True
    display_word: str = "38"
    display_text: str = "105435"


def default_config_path() -> Path:
    override = os.environ.get("INTERFACE_TESTER_CONFIG_DIR")
    if override:
        return Path(override) / CONFIG_FILE_NAME

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_NAME / CONFIG_FILE_NAME

    return Path.home() / ".config" / APP_NAME / CONFIG_FILE_NAME


def load_app_settings(path: Path | None = None) -> AppSettings:
    config_path = path or default_config_path()
    if not config_path.exists():
        return AppSettings()

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return AppSettings()

    if not isinstance(data, dict):
        return AppSettings()

    return _settings_from_mapping(data)


def save_app_settings(settings: AppSettings, path: Path | None = None) -> Path:
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(settings), indent=2, ensure_ascii=True)
    tmp_path = config_path.with_suffix(f"{config_path.suffix}.tmp")
    tmp_path.write_text(payload + "\n", encoding="utf-8")
    tmp_path.replace(config_path)
    return config_path


def _settings_from_mapping(data: dict[str, Any]) -> AppSettings:
    defaults = AppSettings()
    duration = _coerce_float(data.get("duration_seconds"), defaults.duration_seconds)
    response_wait = _coerce_float(data.get("response_wait_seconds"), defaults.response_wait_seconds)
    response_quiet = _coerce_float(data.get("response_quiet_seconds"), defaults.response_quiet_seconds)
    command_delay = _coerce_float(data.get("command_delay_seconds"), defaults.command_delay_seconds)
    diagnostic_seconds = _coerce_float(data.get("diagnostic_seconds"), defaults.diagnostic_seconds)
    return AppSettings(
        last_dat_path=_coerce_string(data.get("last_dat_path"), defaults.last_dat_path),
        last_definition_dir=_coerce_string(data.get("last_definition_dir"), defaults.last_definition_dir),
        serial_port=_coerce_string(data.get("serial_port"), defaults.serial_port),
        baud_rate=_coerce_string(data.get("baud_rate"), defaults.baud_rate),
        newline=_coerce_string(data.get("newline"), defaults.newline),
        intensity_mode=_coerce_string(data.get("intensity_mode"), defaults.intensity_mode),
        light_filter=_coerce_string(data.get("light_filter"), defaults.light_filter),
        output_filter=_coerce_string(data.get("output_filter"), defaults.output_filter),
        duration_seconds=duration if duration > 0 else defaults.duration_seconds,
        response_wait_seconds=response_wait if response_wait > 0 else defaults.response_wait_seconds,
        response_quiet_seconds=response_quiet if response_quiet >= 0 else defaults.response_quiet_seconds,
        command_delay_seconds=command_delay if command_delay >= 0 else defaults.command_delay_seconds,
        diagnostic_seconds=diagnostic_seconds if diagnostic_seconds > 0 else defaults.diagnostic_seconds,
        auto_off=bool(data.get("auto_off", defaults.auto_off)),
        display_word=_coerce_string(data.get("display_word"), defaults.display_word),
        display_text=_coerce_string(data.get("display_text"), defaults.display_text),
    )


def _coerce_string(value: Any, default: str) -> str:
    if value is None:
        return default
    return str(value)


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
