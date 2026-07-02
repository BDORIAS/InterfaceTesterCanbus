from __future__ import annotations

import re
from pathlib import Path

from .models import AircraftDefinition, PanelDefinition, SignalDefinition


DEFINE_RE = re.compile(r"^define\s+(\S+)\s+(\S+)")
ADDRESS_RE = re.compile(r"^@(\d+)\.(\d+)$")
SIGNAL_FLAGS = {"FLIP"}


def parse_interface_file(path: Path) -> AircraftDefinition:
    text = path.read_text(errors="replace")
    panels: dict[str, PanelDefinition] = {}
    signals: list[SignalDefinition] = []
    metadata = _parse_header_metadata(text)
    aircraft_name = _aircraft_name_from_metadata(metadata, path)

    for line_number, raw_line in enumerate(text.splitlines(), 1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("//"):
            continue

        code, _, comment = raw_line.partition("//")
        code = code.strip()
        if not code:
            continue

        tokens = re.split(r"\s+", code)
        if tokens[0] == "define":
            panel = _parse_define(tokens, path.name, line_number)
            if panel:
                panels[panel.name] = panel
            continue

        signal = _parse_signal(tokens, raw_line, comment.strip(), path.name, line_number)
        if signal:
            signals.append(signal)

    return AircraftDefinition(
        name=aircraft_name,
        path=path,
        panels=panels,
        signals=signals,
        metadata=metadata,
    )


def load_interface_definitions(directory: Path) -> list[AircraftDefinition]:
    definitions = [
        parse_interface_file(path)
        for path in sorted(directory.glob("*.dat"))
    ]
    return sorted(definitions, key=lambda item: item.name)


def _parse_define(tokens: list[str], source_file: str, line_number: int) -> PanelDefinition | None:
    if len(tokens) < 3:
        return None

    name = tokens[1]
    target = tokens[2]
    address_match = ADDRESS_RE.match(target)
    if address_match:
        return PanelDefinition(
            name=name,
            source_file=source_file,
            line=line_number,
            channel=int(address_match.group(1)),
            address=int(address_match.group(2)),
            target=target,
        )

    if target.startswith("^"):
        return PanelDefinition(
            name=name,
            source_file=source_file,
            line=line_number,
            target=target,
        )

    return None


def _parse_signal(
    tokens: list[str],
    raw_line: str,
    comment: str,
    source_file: str,
    line_number: int,
) -> SignalDefinition | None:
    direction_index = None
    for index, token in enumerate(tokens):
        if token in {"CI", "CO"}:
            direction_index = index
            break

    if direction_index is None or len(tokens) <= direction_index + 4:
        return None

    name = tokens[0]
    direction = tokens[direction_index]
    panel_name = tokens[direction_index + 1]
    signal_type = tokens[direction_index + 2]

    try:
        word = int(tokens[direction_index + 3])
        start_bit = int(tokens[direction_index + 4])
    except ValueError:
        return None

    end_bit = start_bit
    flag_start_index = direction_index + 5
    if len(tokens) > direction_index + 5 and tokens[direction_index + 5].isdigit():
        end_bit = int(tokens[direction_index + 5])
        flag_start_index = direction_index + 6

    flags = tuple(
        token.upper()
        for token in tokens[flag_start_index:]
        if token.upper() in SIGNAL_FLAGS
    )

    return SignalDefinition(
        name=name,
        direction=direction,
        panel_name=panel_name,
        signal_type=signal_type,
        word=word,
        start_bit=start_bit,
        end_bit=end_bit,
        comment=comment,
        source_file=source_file,
        line=line_number,
        raw_line=raw_line.rstrip(),
        flags=flags,
    )


def _parse_header_metadata(text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for raw_line in text.splitlines()[:40]:
        line = raw_line.strip(" *\t")
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip().upper()] = value.strip()
    return metadata


def _aircraft_name_from_metadata(metadata: dict[str, str], path: Path) -> str:
    project = metadata.get("PROJECT", "")
    upper_project = project.upper()
    if "A320" in upper_project:
        return f"A320 ({path.name})"
    if "ATR" in upper_project:
        return f"ATR ({path.name})"
    if project:
        return f"{project} ({path.name})"
    return path.name
