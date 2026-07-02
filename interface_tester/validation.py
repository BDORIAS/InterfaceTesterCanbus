from __future__ import annotations

from collections.abc import Iterable
from collections import defaultdict
from dataclasses import dataclass

from .input_logic import is_input_signal
from .light_logic import is_light_signal
from .models import AircraftDefinition, PanelDefinition, SignalDefinition
from .output_logic import is_special_output_signal


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    title: str
    details: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]
    panel_count: int
    signal_count: int
    testable_panel_count: int

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    @property
    def info_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "info")

    @property
    def summary(self) -> str:
        return (
            f"Validation: {self.warning_count} warnings, {self.info_count} info, "
            f"{self.testable_panel_count}/{self.panel_count} testable panels"
        )


def validate_aircraft_definition(aircraft: AircraftDefinition) -> ValidationReport:
    issues: list[ValidationIssue] = []
    testable_panel_names = _testable_panel_names(aircraft.signals)

    issues.extend(_undefined_panel_issues(aircraft))
    issues.extend(_duplicate_address_issues(aircraft.panels.values()))
    issues.extend(_unusual_light_field_issues(aircraft.signals))

    panels_without_lights = sorted(set(aircraft.panels) - testable_panel_names)
    if panels_without_lights:
        sample = panels_without_lights[:20]
        suffix = " ..." if len(panels_without_lights) > len(sample) else ""
        issues.append(
            ValidationIssue(
                severity="info",
                title=f"{len(panels_without_lights)} defined panels have no testable features",
                details=tuple(sample + ([suffix.strip()] if suffix else [])),
            )
        )

    return ValidationReport(
        issues=tuple(issues),
        panel_count=len(aircraft.panels),
        signal_count=len(aircraft.signals),
        testable_panel_count=len(testable_panel_names),
    )


def _testable_panel_names(signals: list[SignalDefinition]) -> set[str]:
    return {
        signal.panel_name
        for signal in signals
        if is_light_signal(signal) or is_input_signal(signal) or is_special_output_signal(signal)
    }


def _undefined_panel_issues(aircraft: AircraftDefinition) -> list[ValidationIssue]:
    undefined = sorted({
        signal.panel_name
        for signal in aircraft.signals
        if signal.panel_name not in aircraft.panels
    })
    if not undefined:
        return []
    return [
        ValidationIssue(
            severity="warning",
            title=f"{len(undefined)} panels used by signals have no active definition",
            details=tuple(undefined[:30]),
        )
    ]


def _duplicate_address_issues(panels: Iterable[PanelDefinition]) -> list[ValidationIssue]:
    by_address: dict[int, list[PanelDefinition]] = defaultdict(list)
    by_channel_address: dict[tuple[int, int], list[PanelDefinition]] = defaultdict(list)

    for panel in panels:
        if panel.address is None:
            continue
        by_address[panel.address].append(panel)
        if panel.channel is not None:
            by_channel_address[(panel.channel, panel.address)].append(panel)

    issues: list[ValidationIssue] = []
    ambiguous_addresses = {
        address: items
        for address, items in by_address.items()
        if len(items) > 1
    }
    if ambiguous_addresses:
        details = [
            f"{address}: {', '.join(panel.display_name for panel in items)}"
            for address, items in sorted(ambiguous_addresses.items())[:20]
        ]
        issues.append(
            ValidationIssue(
                severity="warning",
                title=f"{len(ambiguous_addresses)} addresses appear in more than one panel",
                details=tuple(details),
            )
        )

    duplicate_full_addresses = {
        address: items
        for address, items in by_channel_address.items()
        if len(items) > 1
    }
    if duplicate_full_addresses:
        details = [
            f"@{channel}.{address}: {', '.join(panel.name for panel in items)}"
            for (channel, address), items in sorted(duplicate_full_addresses.items())[:20]
        ]
        issues.append(
            ValidationIssue(
                severity="warning",
                title=f"{len(duplicate_full_addresses)} duplicate channel.address entries",
                details=tuple(details),
            )
        )

    return issues


def _unusual_light_field_issues(signals: list[SignalDefinition]) -> list[ValidationIssue]:
    unusual = [
        signal
        for signal in signals
        if (
            is_light_signal(signal)
            and signal.signal_type == "FLOAT-FLD"
            and signal.width not in {8, 16}
        )
    ]
    if not unusual:
        return []

    details = [
        (
            f"{signal.source_file}:{signal.line} {signal.panel_name} "
            f"{signal.name} w{signal.word} bits {signal.bit_range}"
        )
        for signal in unusual[:30]
    ]
    return [
        ValidationIssue(
            severity="warning",
            title=f"{len(unusual)} FLOAT-FLD lights do not use 8 or 16 bits",
            details=tuple(details),
        )
    ]
