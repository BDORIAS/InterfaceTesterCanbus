from __future__ import annotations

import re

from .light_logic import panel_family_name
from .models import AircraftDefinition, PanelDefinition


INDEXED_SIDE_FAMILIES = {"ACP", "CDU", "DCDU", "MCDU", "RMP"}
PANEL_INDEX_RE = re.compile(r"\[(\d+)\]$")
CAP_RE = re.compile(r"(?:^|[^a-z])(?:capt|captain)(?:[^a-z]|$)", re.IGNORECASE)
FO_RE = re.compile(r"(?:^|[^a-z])(?:f/o|fo|first officer)(?:[^a-z]|$)", re.IGNORECASE)


def panel_side_label(aircraft: AircraftDefinition, panel: PanelDefinition) -> str:
    panel_text = panel.name.replace("_", " ")
    explicit = _side_from_text(panel_text)
    if explicit:
        return explicit

    signal_text = " ".join(
        f"{signal.name} {signal.comment}"
        for signal in aircraft.signals
        if signal.panel_name == panel.name
    ).replace("_", " ")
    inferred = _side_from_text(signal_text)
    if inferred:
        return inferred

    family = panel_family_name(panel.name)
    match = PANEL_INDEX_RE.search(panel.name)
    if family in INDEXED_SIDE_FAMILIES and match:
        index = int(match.group(1))
        if index == 0:
            return "CAP"
        if index == 1:
            return "F/O"
    return "-"


def panel_assignment_search_text(aircraft: AircraftDefinition, panel: PanelDefinition) -> str:
    return (
        f"{panel.name} {panel_side_label(aircraft, panel)} "
        f"{panel.channel if panel.channel is not None else ''} "
        f"{panel.address if panel.address is not None else ''}"
    ).lower()


def address_assignment_panels(aircraft: AircraftDefinition) -> list[PanelDefinition]:
    return sorted(
        (panel for panel in aircraft.panels.values() if panel.address is not None),
        key=lambda panel: (panel_family_name(panel.name), panel.name, panel.address or 0),
    )


def _side_from_text(text: str) -> str:
    has_cap = bool(CAP_RE.search(text))
    has_fo = bool(FO_RE.search(text))
    if has_cap and not has_fo:
        return "CAP"
    if has_fo and not has_cap:
        return "F/O"
    return ""
