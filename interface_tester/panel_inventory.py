from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from .input_logic import input_signals_for_panels
from .light_logic import (
    INTENSITY_MODE_RAW,
    LIGHT_FILTER_ALL,
    PanelFamilyLightTest,
    PanelLightTest,
    WordLightGroup,
    build_panel_light_test,
    is_light_signal,
    panel_family_name,
)
from .models import AircraftDefinition, PanelDefinition, SignalDefinition
from .output_logic import special_output_signals_for_panels


@dataclass(frozen=True)
class PanelCapabilityStats:
    light_count: int = 0
    light_word_count: int = 0
    input_count: int = 0
    input_word_count: int = 0
    output_count: int = 0
    output_word_count: int = 0

    @property
    def total_count(self) -> int:
        return self.light_count + self.input_count + self.output_count


def build_panel_inventory(
    aircraft: AircraftDefinition,
    intensity_mode: str = INTENSITY_MODE_RAW,
    light_filter: str = LIGHT_FILTER_ALL,
) -> tuple[list[PanelFamilyLightTest], dict[str, PanelCapabilityStats]]:
    light_signals = _defined_signals(aircraft, [signal for signal in aircraft.signals if is_light_signal(signal, light_filter)])
    input_signals = _defined_signals(aircraft, input_signals_for_panels(aircraft))
    output_signals = _defined_signals(aircraft, special_output_signals_for_panels(aircraft))

    panels_by_family = _panels_by_family(aircraft.panels.values())
    capable_panel_names = {
        signal.panel_name
        for signal in (*light_signals, *input_signals, *output_signals)
    }

    families: list[PanelFamilyLightTest] = []
    stats_by_family: dict[str, PanelCapabilityStats] = {}
    for family_name, panels in sorted(panels_by_family.items()):
        capable_panels = [panel for panel in panels if panel.name in capable_panel_names]
        if not capable_panels:
            continue

        tests = tuple(
            build_panel_light_test(aircraft, panel.name, intensity_mode, light_filter)
            or PanelLightTest(panel=panel, groups=())
            for panel in capable_panels
        )
        family = _build_family_light_test(family_name, tests)
        families.append(family)
        stats_by_family[family_name] = _family_stats(
            family,
            family_name,
            light_signals,
            input_signals,
            output_signals,
        )

    return families, stats_by_family


def _defined_signals(
    aircraft: AircraftDefinition,
    signals: list[SignalDefinition],
) -> tuple[SignalDefinition, ...]:
    return tuple(signal for signal in signals if signal.panel_name in aircraft.panels)


def _panels_by_family(panels: Iterable[PanelDefinition]) -> dict[str, list[PanelDefinition]]:
    grouped: dict[str, list[PanelDefinition]] = defaultdict(list)
    for panel in panels:
        grouped[panel_family_name(panel.name)].append(panel)
    return {
        family_name: sorted(items, key=lambda panel: panel.name)
        for family_name, items in grouped.items()
    }


def _build_family_light_test(
    family_name: str,
    tests: tuple[PanelLightTest, ...],
) -> PanelFamilyLightTest:
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


def _family_stats(
    family: PanelFamilyLightTest,
    family_name: str,
    light_signals: tuple[SignalDefinition, ...],
    input_signals: tuple[SignalDefinition, ...],
    output_signals: tuple[SignalDefinition, ...],
) -> PanelCapabilityStats:
    family_panel_names = set(family.variant_names)
    family_lights = [
        signal
        for signal in light_signals
        if signal.panel_name in family_panel_names or panel_family_name(signal.panel_name) == family_name
    ]
    family_inputs = [
        signal
        for signal in input_signals
        if signal.panel_name in family_panel_names or panel_family_name(signal.panel_name) == family_name
    ]
    family_outputs = [
        signal
        for signal in output_signals
        if signal.panel_name in family_panel_names or panel_family_name(signal.panel_name) == family_name
    ]
    return PanelCapabilityStats(
        light_count=len(family_lights),
        light_word_count=len({signal.word for signal in family_lights}),
        input_count=len(family_inputs),
        input_word_count=len({signal.word for signal in family_inputs}),
        output_count=len(family_outputs),
        output_word_count=len({signal.word for signal in family_outputs}),
    )
