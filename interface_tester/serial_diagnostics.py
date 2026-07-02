from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .serial_client import decode_serial_bytes


SERIAL_TRACE_MAX_EVENTS = 5000


@dataclass(frozen=True)
class SerialTraceEvent:
    time: str
    direction: str
    source: str
    text: str
    hex_data: str


def make_serial_trace_event(
    time: str,
    direction: str,
    source: str,
    data: bytes | str,
) -> SerialTraceEvent:
    if isinstance(data, bytes):
        text = decode_serial_bytes(data)
        raw = data
    else:
        text = data
        raw = data.encode("utf-8", errors="replace")

    return SerialTraceEvent(
        time=time,
        direction=direction,
        source=source,
        text=escape_control_chars(text),
        hex_data=bytes_to_hex(raw),
    )


def write_serial_trace_log(
    path: Path,
    events: list[SerialTraceEvent],
    metadata: dict[str, str],
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_serial_trace_text(events, metadata), encoding="utf-8")
    return path


def trim_serial_trace_events(
    events: list[SerialTraceEvent],
    max_events: int = SERIAL_TRACE_MAX_EVENTS,
) -> int:
    if max_events < 1:
        removed_count = len(events)
        events.clear()
        return removed_count

    overflow = len(events) - max_events
    if overflow <= 0:
        return 0

    del events[:overflow]
    return overflow


def build_serial_trace_text(
    events: list[SerialTraceEvent],
    metadata: dict[str, str],
) -> str:
    lines = [
        "# Interface Tester Serial Trace",
        "",
        f"Generated: {metadata.get('generated_at', '')}",
        f"Port: {metadata.get('port', '')}",
        f"Baud: {metadata.get('baud_rate', '')}",
        f"Newline: {metadata.get('newline', '')}",
        f"DAT: {metadata.get('dat_path', '')}",
        f"Panel: {metadata.get('panel', '')}",
        f"Detected panel: {metadata.get('detected_panel', '')}",
        f"Response wait: {metadata.get('response_wait_seconds', '')} s",
        f"Response quiet: {metadata.get('response_quiet_seconds', '')} s",
        f"Command delay: {metadata.get('command_delay_seconds', '')} s",
        f"Diagnostic window: {metadata.get('diagnostic_seconds', '')} s",
        f"Trace events kept: {metadata.get('trace_events_kept', len(events))}",
        f"Trace event limit: {metadata.get('trace_event_limit', '')}",
        f"Trace events discarded: {metadata.get('trace_events_discarded', '0')}",
        "",
    ]

    if not events:
        lines.append("No serial trace events recorded.")
        lines.append("")
        return "\n".join(lines)

    for event in events:
        lines.extend(
            [
                f"[{event.time}] {event.direction} {event.source}",
                f"TEXT: {event.text}",
                f"HEX : {event.hex_data}",
                "",
            ]
        )
    return "\n".join(lines)


def escape_control_chars(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )


def bytes_to_hex(data: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in data)
