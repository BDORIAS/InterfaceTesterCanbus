from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from .models import AircraftDefinition, PanelDefinition, SignalDefinition


INTENSITY_MODE_RAW = "raw_ff"
INTENSITY_MODE_PERCENT = "percent_100"
INTENSITY_MODE_LABELS = {
    INTENSITY_MODE_RAW: "Raw FF",
    INTENSITY_MODE_PERCENT: "Percent 100",
}

LIGHT_FILTER_ALL = "all"
LIGHT_FILTER_BACKLIGHT = "backlight"
LIGHT_FILTER_LAMPS = "lamps"
LIGHT_FILTER_LABELS = {
    LIGHT_FILTER_ALL: "All",
    LIGHT_FILTER_BACKLIGHT: "Backlight",
    LIGHT_FILTER_LAMPS: "Lights / Ann",
}

PANEL_INDEX_RE = re.compile(r"^(?P<base>.+?)\[\d+\]$")

BACKLIGHT_RE = re.compile(r"bklt|backlight|backlighting", re.IGNORECASE)

LAMP_RE = re.compile(
    r"("
    r"(?<![a-z])lt(?![a-z])|light|"
    r"annunciator|(?<![a-z])ann(?![a-z])|_ann(?:\W|$)"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class WordLightGroup:
    word: int
    mask: int
    signals: tuple[SignalDefinition, ...]
    on_value: int | None = None

    @property
    def command_value(self) -> int:
        return self.mask if self.on_value is None else self.on_value

    @property
    def on_command(self) -> str:
        return format_raw_write_command(self.word, self.command_value)

    @property
    def off_command(self) -> str:
        return format_raw_write_command(self.word, 0)

    @property
    def signal_names(self) -> str:
        names = []
        seen = set()
        for signal in self.signals:
            label = f"{signal.name} ({signal.bit_range})"
            if label not in seen:
                names.append(label)
                seen.add(label)
        return ", ".join(names)


@dataclass(frozen=True)
class PanelLightTest:
    panel: PanelDefinition
    groups: tuple[WordLightGroup, ...]

    @property
    def on_commands(self) -> list[str]:
        return [group.on_command for group in self.groups]

    @property
    def off_commands(self) -> list[str]:
        return [group.off_command for group in self.groups]

    @property
    def light_count(self) -> int:
        return sum(len(group.signals) for group in self.groups)


@dataclass(frozen=True)
class PanelFamilyLightTest:
    family_name: str
    tests: tuple[PanelLightTest, ...]
    groups: tuple[WordLightGroup, ...]

    @property
    def variant_count(self) -> int:
        return len(self.tests)

    @property
    def variant_names(self) -> list[str]:
        return [test.panel.name for test in self.tests]

    @property
    def light_count(self) -> int:
        return sum(test.light_count for test in self.tests)

    @property
    def on_commands(self) -> list[str]:
        return [group.on_command for group in self.groups]

    @property
    def off_commands(self) -> list[str]:
        return [group.off_command for group in self.groups]

    def test_for_panel(self, panel_name: str) -> PanelLightTest | None:
        for test in self.tests:
            if test.panel.name == panel_name:
                return test
        return None


def command_target_label(target: PanelLightTest | PanelFamilyLightTest) -> str:
    if isinstance(target, PanelLightTest):
        return target.panel.display_name
    return f"{target.family_name} ({', '.join(target.variant_names)})"


def build_command_plan_text(
    target: PanelLightTest | PanelFamilyLightTest,
    metadata: dict[str, str] | None = None,
) -> str:
    lines = [
        "# Interface Tester Command Plan",
        "",
        f"Panel: {command_target_label(target)}",
    ]
    if metadata:
        for key, value in metadata.items():
            if value:
                lines.append(f"{key}: {value}")

    lines.extend(
        [
            "",
            "ON commands:",
            *(target.on_commands or ["No light ON commands for this target."]),
            "",
            "OFF commands:",
            *(target.off_commands or ["No light OFF commands for this target."]),
            "",
            "| Word | ON | OFF | Mask | Lights | Signals |",
            "|---|---|---|---|---:|---|",
        ]
    )
    if not target.groups:
        lines.append("| - | - | - | - | 0 | No CO lights mapped with the current filter. |")
    for group in target.groups:
        lines.append(
            "| "
            f"w{group.word} | "
            f"`{group.on_command}` | "
            f"`{group.off_command}` | "
            f"{group.mask:04x} | "
            f"{len(group.signals)} | "
            f"{group.signal_names.replace('|', '/')} |"
        )
    lines.append("")
    return "\n".join(lines)


def build_panel_detail_text(
    target: PanelLightTest | PanelFamilyLightTest,
    metadata: dict[str, str] | None = None,
    intensity_mode: str = INTENSITY_MODE_RAW,
) -> str:
    lines = [
        "# Interface Tester Panel Detail",
        "",
        f"Panel: {command_target_label(target)}",
    ]
    if metadata:
        for key, value in metadata.items():
            if value:
                lines.append(f"{key}: {value}")

    tests = (target,) if isinstance(target, PanelLightTest) else target.tests
    lines.extend(
        [
            "",
            "## Variants",
            "",
            "| Panel | Channel | Address | Lights | Words |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for test in tests:
        panel = test.panel
        channel = "" if panel.channel is None else str(panel.channel)
        address = "" if panel.address is None else str(panel.address)
        lines.append(
            "| "
            f"{panel.name} | "
            f"{channel} | "
            f"{address} | "
            f"{test.light_count} | "
            f"{len(test.groups)} |"
        )

    lines.extend(
        [
            "",
            "## Word Summary",
            "",
            "| Word | ON | OFF | Mask | Signals |",
            "|---|---|---|---|---:|",
        ]
    )
    for group in target.groups:
        lines.append(
            "| "
            f"w{group.word} | "
            f"`{group.on_command}` | "
            f"`{group.off_command}` | "
            f"{group.mask:04x} | "
            f"{len(group.signals)} |"
        )

    lines.extend(
        [
            "",
            "## Signals",
            "",
            "| Panel | Signal | Type | Word | Bits | ON | OFF | Comment |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for group in target.groups:
        for signal in group.signals:
            lines.append(
                "| "
                f"{signal.panel_name} | "
                f"{signal.name.replace('|', '/')} | "
                f"{signal.signal_type} | "
                f"w{signal.word} | "
                f"{signal.bit_range} | "
                f"`{signal_on_command(signal, intensity_mode)}` | "
                f"`{signal_off_command(signal)}` | "
                f"{signal.comment.replace('|', '/')} |"
            )
    lines.append("")
    return "\n".join(lines)


def panel_family_name(panel_name: str) -> str:
    match = PANEL_INDEX_RE.match(panel_name)
    if match:
        return match.group("base")
    return panel_name


def test_target_includes_panel(
    target: PanelLightTest | PanelFamilyLightTest,
    panel: PanelDefinition | None,
) -> bool:
    if panel is None:
        return True
    if isinstance(target, PanelLightTest):
        return target.panel.name == panel.name
    if panel_family_name(panel.name) != target.family_name:
        return False
    return any(test.panel.name == panel.name for test in target.tests)


def signal_search_text(signal: SignalDefinition) -> str:
    return f"{signal.name} {signal.comment}"


def is_backlight_signal(signal: SignalDefinition) -> bool:
    return bool(BACKLIGHT_RE.search(signal_search_text(signal)))


def is_lamp_or_annunciator_signal(signal: SignalDefinition) -> bool:
    if is_backlight_signal(signal):
        return False
    return bool(LAMP_RE.search(signal_search_text(signal)))


def is_light_signal(
    signal: SignalDefinition,
    light_filter: str = LIGHT_FILTER_ALL,
) -> bool:
    if signal.direction != "CO":
        return False
    if signal.start_bit < 0 or signal.end_bit > 15 or signal.end_bit < signal.start_bit:
        return False
    if light_filter == LIGHT_FILTER_BACKLIGHT:
        return is_backlight_signal(signal)
    if light_filter == LIGHT_FILTER_LAMPS:
        return is_lamp_or_annunciator_signal(signal)
    return is_backlight_signal(signal) or is_lamp_or_annunciator_signal(signal)


def signal_on_value(signal: SignalDefinition, intensity_mode: str = INTENSITY_MODE_RAW) -> int:
    if intensity_mode == INTENSITY_MODE_PERCENT and signal.signal_type == "FLOAT-FLD":
        max_value = (1 << signal.width) - 1
        return min(100, max_value) << signal.start_bit
    return signal_write_mask(signal)


def signal_write_mask(signal: SignalDefinition) -> int:
    """Return the RAW WRITE mask; firmware numbers output bits from the LSB."""
    return ((1 << signal.width) - 1) << signal.start_bit


def signal_command_label(signal: SignalDefinition) -> str:
    return f"{signal.panel_name}.{signal.name} ({signal.bit_range})"


def format_raw_write_command(word: int, value: int) -> str:
    return f"w {word} {value:04x}"


def signal_on_command(signal: SignalDefinition, intensity_mode: str = INTENSITY_MODE_RAW) -> str:
    return format_raw_write_command(signal.word, signal_on_value(signal, intensity_mode))


def signal_off_command(signal: SignalDefinition) -> str:
    return format_raw_write_command(signal.word, 0)


def signal_group_values(
    signals: list[SignalDefinition],
    intensity_mode: str = INTENSITY_MODE_RAW,
) -> tuple[int, int]:
    mask = 0
    on_value = 0
    for signal in signals:
        mask |= signal_write_mask(signal)
        on_value |= signal_on_value(signal, intensity_mode)
    return mask, on_value


def build_panel_light_test(
    aircraft: AircraftDefinition,
    panel_name: str,
    intensity_mode: str = INTENSITY_MODE_RAW,
    light_filter: str = LIGHT_FILTER_ALL,
) -> PanelLightTest | None:
    panel = aircraft.panels.get(panel_name)
    if not panel:
        return None

    by_word: dict[int, list[SignalDefinition]] = defaultdict(list)
    for signal in aircraft.signals:
        if signal.panel_name == panel_name and is_light_signal(signal, light_filter):
            by_word[signal.word].append(signal)

    groups: list[WordLightGroup] = []
    for word, signals in sorted(by_word.items()):
        mask, on_value = signal_group_values(signals, intensity_mode)
        groups.append(
            WordLightGroup(
                word=word,
                mask=mask,
                on_value=on_value,
                signals=tuple(sorted(signals, key=lambda item: (item.start_bit, item.end_bit, item.line))),
            )
        )

    return PanelLightTest(panel=panel, groups=tuple(groups))


def list_panels_with_lights(
    aircraft: AircraftDefinition,
    intensity_mode: str = INTENSITY_MODE_RAW,
    light_filter: str = LIGHT_FILTER_ALL,
) -> list[PanelLightTest]:
    tests = []
    for panel_name in sorted(aircraft.panels):
        test = build_panel_light_test(aircraft, panel_name, intensity_mode, light_filter)
        if test and test.groups:
            tests.append(test)
    return tests


def build_panel_family_light_test(
    aircraft: AircraftDefinition,
    family_name: str,
    intensity_mode: str = INTENSITY_MODE_RAW,
    light_filter: str = LIGHT_FILTER_ALL,
) -> PanelFamilyLightTest | None:
    tests = [
        test
        for test in list_panels_with_lights(aircraft, intensity_mode, light_filter)
        if panel_family_name(test.panel.name) == family_name
    ]
    if not tests:
        return None

    groups_by_word: dict[int, list[WordLightGroup]] = defaultdict(list)
    for test in tests:
        for group in test.groups:
            groups_by_word[group.word].append(group)

    merged_groups = []
    for word, groups in sorted(groups_by_word.items()):
        mask = 0
        on_value = 0
        signals: list[SignalDefinition] = []
        seen_signals = set()
        for group in groups:
            mask |= group.mask
            on_value |= group.command_value
            for signal in group.signals:
                key = (signal.panel_name, signal.name, signal.word, signal.start_bit, signal.end_bit)
                if key in seen_signals:
                    continue
                seen_signals.add(key)
                signals.append(signal)
        merged_groups.append(
            WordLightGroup(
                word=word,
                mask=mask,
                on_value=on_value,
                signals=tuple(sorted(signals, key=lambda item: (item.panel_name, item.start_bit, item.end_bit, item.line))),
            )
        )

    return PanelFamilyLightTest(
        family_name=family_name,
        tests=tuple(sorted(tests, key=lambda item: item.panel.name)),
        groups=tuple(merged_groups),
    )


def list_panel_families_with_lights(
    aircraft: AircraftDefinition,
    intensity_mode: str = INTENSITY_MODE_RAW,
    light_filter: str = LIGHT_FILTER_ALL,
) -> list[PanelFamilyLightTest]:
    family_names = sorted({
        panel_family_name(test.panel.name)
        for test in list_panels_with_lights(aircraft, intensity_mode, light_filter)
    })
    families = []
    for family_name in family_names:
        family = build_panel_family_light_test(aircraft, family_name, intensity_mode, light_filter)
        if family:
            families.append(family)
    return families
