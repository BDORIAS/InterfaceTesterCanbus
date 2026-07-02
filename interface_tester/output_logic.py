from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .input_logic import markdown_cell, signal_flags_text
from .light_logic import is_light_signal
from .models import AircraftDefinition, SignalDefinition


OUTPUT_DIRECTION = "CO"
OUTPUT_CATEGORY_DISPLAY = "DISPLAY"
OUTPUT_CATEGORY_INDICATOR = "INDICATOR"
OUTPUT_CATEGORY_ENABLE = "ENABLE"
OUTPUT_CATEGORY_MATRIX = "MATRIX/SIGN"
OUTPUT_CATEGORY_ACTUATOR = "ACTUATOR"
OUTPUT_CATEGORY_DISCRETE_CB = "DISCRETE/CB"
OUTPUT_FILTER_ALL = "all"
OUTPUT_CATEGORY_ORDER = (
    OUTPUT_CATEGORY_DISPLAY,
    OUTPUT_CATEGORY_INDICATOR,
    OUTPUT_CATEGORY_ENABLE,
    OUTPUT_CATEGORY_MATRIX,
    OUTPUT_CATEGORY_ACTUATOR,
    OUTPUT_CATEGORY_DISCRETE_CB,
)
OUTPUT_CATEGORY_FILTER_LABELS = {
    OUTPUT_FILTER_ALL: "All",
    OUTPUT_CATEGORY_DISPLAY: "Display",
    OUTPUT_CATEGORY_INDICATOR: "Indicator",
    OUTPUT_CATEGORY_ENABLE: "Enable",
    OUTPUT_CATEGORY_MATRIX: "Matrix/Sign",
    OUTPUT_CATEGORY_ACTUATOR: "Actuator",
    OUTPUT_CATEGORY_DISCRETE_CB: "Discrete/CB",
}

DISPLAY_RE = re.compile(
    r"("
    r"dspl|display|digit|segment|seven\s*segment|decimal\s*point|"
    r"(?<![a-z0-9])dp(?![a-z0-9])|colon|clock|lcd"
    r")",
    re.IGNORECASE,
)
INDICATOR_RE = re.compile(
    r"("
    r"indicator|(?<![a-z0-9])ind(?![a-z0-9])|gauge|meter|"
    r"repeater|brushless|instrument|needle|compass"
    r")",
    re.IGNORECASE,
)
ENABLE_RE = re.compile(
    r"("
    r"always[_\s-]?on|enable|photocell|pot\s+enable|brightness\s+pot"
    r")",
    re.IGNORECASE,
)
MATRIX_RE = re.compile(r"(matrix|sign)", re.IGNORECASE)
ACTUATOR_RE = re.compile(
    r"("
    r"valve|(?<![a-z0-9])vlv(?![a-z0-9])|solenoid|motor|(?<![a-z0-9])mot\d?(?![a-z0-9])"
    r")",
    re.IGNORECASE,
)
CB_OUTPUT_RE = re.compile(
    r"("
    r"cb[_\s-]?out|circuit\s*breaker.*\bout\b"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DisplayWordGroup:
    word: int
    signals: tuple[SignalDefinition, ...]

    @property
    def signal_names(self) -> str:
        return ", ".join(signal.name for signal in self.signals)


@dataclass(frozen=True)
class DisplaySweepFrame:
    label: str
    commands: tuple[str, ...]


def signal_search_text(signal: SignalDefinition) -> str:
    return f"{signal.name} {signal.comment}"


def is_valid_output_signal(signal: SignalDefinition) -> bool:
    if signal.direction != OUTPUT_DIRECTION:
        return False
    if signal.start_bit < 0 or signal.end_bit > 15 or signal.end_bit < signal.start_bit:
        return False
    return True


def special_output_category(signal: SignalDefinition) -> str | None:
    text = signal_search_text(signal)
    if ENABLE_RE.search(text):
        return OUTPUT_CATEGORY_ENABLE
    if DISPLAY_RE.search(text):
        return OUTPUT_CATEGORY_DISPLAY
    if INDICATOR_RE.search(text):
        return OUTPUT_CATEGORY_INDICATOR
    if MATRIX_RE.search(text):
        return OUTPUT_CATEGORY_MATRIX
    if CB_OUTPUT_RE.search(text):
        return OUTPUT_CATEGORY_DISCRETE_CB
    if ACTUATOR_RE.search(text):
        return OUTPUT_CATEGORY_ACTUATOR
    return None


def is_special_output_signal(signal: SignalDefinition) -> bool:
    if not is_valid_output_signal(signal):
        return False
    if is_light_signal(signal):
        return False
    return special_output_category(signal) is not None


def special_output_signals_for_panels(
    aircraft: AircraftDefinition,
    panel_names: Iterable[str] | None = None,
    category_filter: str = OUTPUT_FILTER_ALL,
) -> list[SignalDefinition]:
    allowed = set(panel_names) if panel_names is not None else None
    signals = [
        signal
        for signal in aircraft.signals
        if (
            is_special_output_signal(signal)
            and (allowed is None or signal.panel_name in allowed)
            and output_category_matches_filter(signal, category_filter)
        )
    ]
    return sorted(signals, key=lambda item: (item.panel_name, item.word, item.start_bit, item.end_bit, item.name))


def output_category_matches_filter(signal: SignalDefinition, category_filter: str) -> bool:
    if category_filter == OUTPUT_FILTER_ALL:
        return True
    return special_output_category(signal) == category_filter


def special_outputs_by_word(signals: Iterable[SignalDefinition]) -> dict[int, tuple[SignalDefinition, ...]]:
    grouped: dict[int, list[SignalDefinition]] = defaultdict(list)
    for signal in signals:
        grouped[signal.word].append(signal)
    return {
        word: tuple(sorted(items, key=lambda item: (item.start_bit, item.end_bit, item.panel_name, item.name)))
        for word, items in sorted(grouped.items())
    }


def display_word_groups(signals: Iterable[SignalDefinition]) -> tuple[DisplayWordGroup, ...]:
    grouped: dict[int, list[SignalDefinition]] = defaultdict(list)
    for signal in signals:
        if (
            special_output_category(signal) == OUTPUT_CATEGORY_DISPLAY
            and signal.signal_type == "BIT-FLD"
            and signal.width >= 7
        ):
            grouped[signal.word].append(signal)
    return tuple(
        DisplayWordGroup(
            word=word,
            signals=tuple(sorted(items, key=lambda item: (item.start_bit, item.end_bit, item.name))),
        )
        for word, items in sorted(grouped.items())
    )


def normalize_display_sweep_characters(value: str) -> str:
    characters = []
    for character in value:
        if not character.isascii() or not character.isalnum() or character in characters:
            continue
        characters.append(character)
    return "".join(characters)


def build_display_sweep_frames(
    signals: Iterable[SignalDefinition],
    characters: str = "0123456789",
) -> tuple[DisplaySweepFrame, ...]:
    groups = display_word_groups(signals)
    sequence = normalize_display_sweep_characters(characters)
    if not groups or not sequence:
        return ()

    locator_commands = []
    locator_values = []
    for index, group in enumerate(groups):
        first = str((index * 2 + 1) % 10)
        second = str((index * 2 + 2) % 10)
        marker = f"{first}{second}"
        locator_values.append(marker)
        locator_commands.append(f"S {group.word} {marker}")

    frames = [
        DisplaySweepFrame(
            label=f"Mapa {' '.join(locator_values)}",
            commands=tuple(locator_commands),
        )
    ]
    frames.extend(
        DisplaySweepFrame(
            label=f"Digito {character}",
            commands=tuple(f"S {group.word} {character * 2}" for group in groups),
        )
        for character in sequence
    )
    return tuple(frames)


def build_special_output_plan_text(
    signals: Iterable[SignalDefinition],
    target_label: str,
    metadata: dict[str, str] | None = None,
) -> str:
    signal_list = sorted(
        signals,
        key=lambda item: (item.panel_name, item.word, item.start_bit, item.end_bit, item.name),
    )
    lines = [
        "# Interface Tester Non-Light Output Plan",
        "",
        f"Target: {target_label}",
    ]
    if metadata:
        for key, value in metadata.items():
            if value:
                lines.append(f"{key}: {value}")

    lines.extend(
        [
            "",
            "## Procedure",
            "",
            "1. Confirm Direct Mode with Sim Host downloaded.",
            "2. Identify the words/bits for non-light CO outputs in this plan.",
            "3. For firmware-supported displays, use the automatic sweep or test with `S <word> <text>`.",
            "4. For indicators or repeaters, test `demo`, `ST`, or `ST_Brushless` only when applicable to the panel.",
            "5. For discrete/CB outputs, valves, or solenoids, review the word/bit and panel procedure before using `w <word> <hex>`.",
            "6. The display sweep uses two characters per word; it does not generate raw commands for other outputs.",
            "",
        ]
    )

    if not signal_list:
        lines.append("No non-light CO outputs are mapped for this target.")
        lines.append("")
        return "\n".join(lines)

    lines.extend(
        [
            "## Category Summary",
            "",
            "| Category | Words | Signals |",
            "|---|---|---:|",
        ]
    )
    for category, category_signals in sorted(signals_by_category(signal_list).items(), key=lambda item: category_sort_key(item[0])):
        words = ", ".join(f"w{word}" for word in sorted({signal.word for signal in category_signals}))
        lines.append(f"| {category} | {markdown_cell(words)} | {len(category_signals)} |")

    lines.extend(
        [
            "",
            "## Word Summary",
            "",
            "| Word | Categories | Signals | Bits |",
            "|---|---|---:|---|",
        ]
    )
    for word, word_signals in special_outputs_by_word(signal_list).items():
        categories = category_count_text(word_signals)
        bits = ", ".join(signal.bit_range for signal in word_signals)
        lines.append(f"| w{word} | {markdown_cell(categories)} | {len(word_signals)} | {markdown_cell(bits)} |")

    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "| Category | Panel | Signal | Type | Word | Bits | Flags | Comment |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for signal in signal_list:
        lines.append(
            "| "
            f"{special_output_category(signal) or ''} | "
            f"{markdown_cell(signal.panel_name)} | "
            f"{markdown_cell(signal.name)} | "
            f"{markdown_cell(signal.signal_type)} | "
            f"w{signal.word} | "
            f"{signal.bit_range} | "
            f"{markdown_cell(signal_flags_text(signal))} | "
            f"{markdown_cell(signal.comment)} |"
        )
    lines.append("")
    return "\n".join(lines)


def signals_by_category(signals: Iterable[SignalDefinition]) -> dict[str, list[SignalDefinition]]:
    grouped: dict[str, list[SignalDefinition]] = defaultdict(list)
    for signal in signals:
        category = special_output_category(signal)
        if category:
            grouped[category].append(signal)
    return grouped


def category_count_text(signals: Iterable[SignalDefinition]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for signal in signals:
        category = special_output_category(signal)
        if category:
            counts[category] += 1
    return ", ".join(
        f"{category}: {counts[category]}"
        for category in sorted(counts, key=category_sort_key)
    )


def category_sort_key(category: str) -> tuple[int, str]:
    try:
        return (OUTPUT_CATEGORY_ORDER.index(category), category)
    except ValueError:
        return (len(OUTPUT_CATEGORY_ORDER), category)
