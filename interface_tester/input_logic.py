from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .models import AircraftDefinition, SignalDefinition


INPUT_DIRECTION = "CI"
FLIP_FLAG = "FLIP"

LABELED_WORD_VALUE_RE = re.compile(
    r"(?ix)"
    r"\b(?:w|word)\s*[:=#]?\s*(?P<word>\d{1,4})\b"
    r"[^\r\n]*?"
    r"(?<![a-z0-9])(?:0x)?(?P<value>[0-9a-f]{2,4})\b"
)
KEY_VALUE_WORD_RE = re.compile(
    r"(?ix)"
    r"\bword\s*[:=]\s*(?P<word>\d{1,4})\b"
    r".{0,40}?"
    r"\b(?:value|hex|pattern)\s*[:=]\s*(?:0x)?(?P<value>[0-9a-f]{1,4})\b"
)
COMPACT_WORD_VALUE_RE = re.compile(
    r"(?ix)"
    r"^\s*(?:ver\s*3\s*[:=-]?\s*)?"
    r"(?:w\s*)?(?P<word>\d{1,4})\s*(?:[:=,]|\s)\s*(?:0x)?(?P<value>[0-9a-f]{1,4})\s*$"
)


@dataclass(frozen=True)
class WordValueUpdate:
    word: int
    value: int
    raw_line: str


@dataclass(frozen=True)
class DecodedInputSignal:
    signal: SignalDefinition
    raw_value: int
    logical_value: int
    previous_raw_value: int | None = None
    previous_logical_value: int | None = None

    @property
    def changed(self) -> bool:
        return self.previous_raw_value is not None and self.previous_raw_value != self.raw_value


def parse_ver3_word_values(text: str) -> list[WordValueUpdate]:
    updates: list[WordValueUpdate] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parsed = parse_ver3_word_value_line(line)
        if parsed:
            updates.append(parsed)
    return updates


def parse_ver3_word_value_line(line: str) -> WordValueUpdate | None:
    for pattern in (KEY_VALUE_WORD_RE, LABELED_WORD_VALUE_RE, COMPACT_WORD_VALUE_RE):
        match = pattern.search(line)
        if not match:
            continue
        try:
            word = int(match.group("word"), 10)
            value = int(match.group("value"), 16)
        except ValueError:
            continue
        if value > 0xFFFF:
            continue
        return WordValueUpdate(word=word, value=value, raw_line=line)
    return None


def is_input_signal(signal: SignalDefinition) -> bool:
    if signal.direction != INPUT_DIRECTION:
        return False
    if signal.start_bit < 0 or signal.end_bit > 15 or signal.end_bit < signal.start_bit:
        return False
    return True


def input_signals_for_panels(
    aircraft: AircraftDefinition,
    panel_names: Iterable[str] | None = None,
) -> list[SignalDefinition]:
    allowed = set(panel_names) if panel_names is not None else None
    signals = [
        signal
        for signal in aircraft.signals
        if is_input_signal(signal) and (allowed is None or signal.panel_name in allowed)
    ]
    return sorted(signals, key=lambda item: (item.panel_name, item.word, item.start_bit, item.end_bit, item.name))


def input_signals_by_word(signals: Iterable[SignalDefinition]) -> dict[int, tuple[SignalDefinition, ...]]:
    grouped: dict[int, list[SignalDefinition]] = defaultdict(list)
    for signal in signals:
        grouped[signal.word].append(signal)
    return {
        word: tuple(sorted(items, key=lambda item: (item.start_bit, item.end_bit, item.panel_name, item.name)))
        for word, items in grouped.items()
    }


def build_input_test_plan_text(
    signals: Iterable[SignalDefinition],
    target_label: str,
    metadata: dict[str, str] | None = None,
) -> str:
    signal_list = sorted(
        signals,
        key=lambda item: (item.panel_name, item.word, item.start_bit, item.end_bit, item.name),
    )
    lines = [
        "# Interface Tester Input Test Plan",
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
            "2. Send `VER 3` from the input monitor.",
            "3. Move a switch, knob, lever, encoder, potentiometer, or CB.",
            "4. Compare the `word/hex` change with the `VER3 decode` lines.",
            "5. Verify the raw and logical values when the signal has `FLIP`.",
            "",
            "## Word Summary",
            "",
        ]
    )

    if not signal_list:
        lines.append("No CI inputs are mapped for this target.")
        lines.append("")
        return "\n".join(lines)

    lines.extend(
        [
            "| Word | Inputs | Signals |",
            "|---|---:|---|",
        ]
    )
    for word, word_signals in input_signals_by_word(signal_list).items():
        signal_names = ", ".join(signal.name for signal in word_signals)
        lines.append(f"| w{word} | {len(word_signals)} | {markdown_cell(signal_names)} |")

    lines.extend(
        [
            "",
            "## Inputs",
            "",
            "| Panel | Signal | Type | Word | Bits | Flags | Comment |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for signal in signal_list:
        lines.append(
            "| "
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


def decode_input_update(
    update: WordValueUpdate,
    signals: Iterable[SignalDefinition],
    previous_value: int | None = None,
) -> list[DecodedInputSignal]:
    decoded: list[DecodedInputSignal] = []
    for signal in signals:
        if signal.word != update.word:
            continue
        raw_value = signal_raw_value(signal, update.value)
        previous_raw_value = None if previous_value is None else signal_raw_value(signal, previous_value)
        decoded.append(
            DecodedInputSignal(
                signal=signal,
                raw_value=raw_value,
                logical_value=signal_logical_value(signal, raw_value),
                previous_raw_value=previous_raw_value,
                previous_logical_value=None
                if previous_raw_value is None
                else signal_logical_value(signal, previous_raw_value),
            )
        )
    return decoded


def decode_input_update_with_fallback(
    update: WordValueUpdate,
    signals: Iterable[SignalDefinition],
    previous_value: int | None = None,
) -> tuple[list[DecodedInputSignal], bool]:
    signal_list = list(signals)
    decoded = decode_input_update(update, signal_list, previous_value)
    if previous_value is None or previous_value == update.value or any(item.changed for item in decoded):
        return decoded, False

    mirrored_update = WordValueUpdate(
        word=update.word,
        value=reverse_word_bits(update.value),
        raw_line=update.raw_line,
    )
    mirrored_previous = reverse_word_bits(previous_value)
    mirrored = decode_input_update(mirrored_update, signal_list, mirrored_previous)
    if any(item.changed for item in mirrored):
        return mirrored, True
    return decoded, False


def reverse_word_bits(value: int) -> int:
    value &= 0xFFFF
    result = 0
    for _ in range(16):
        result = (result << 1) | (value & 1)
        value >>= 1
    return result


def format_ver3_decoded_lines(
    update: WordValueUpdate,
    signals: Iterable[SignalDefinition],
    previous_value: int | None = None,
    max_signals: int = 12,
) -> list[str]:
    decoded, mirrored = decode_input_update_with_fallback(update, signals, previous_value)
    if not decoded:
        return [f"VER3 decode w{update.word}: {update.value:04x} (no CI signals mapped for this word)"]

    if previous_value is None:
        shown = [item for item in decoded if item.raw_value != 0] or decoded
        header = f"VER3 decode w{update.word}: {update.value:04x} (baseline, {len(decoded)} CI signals)"
    else:
        changed_mask = previous_value ^ update.value
        shown = [item for item in decoded if item.changed]
        order_note = " (inferred reversed bit order)" if mirrored else ""
        header = (
            f"VER3 decode w{update.word}: {previous_value:04x} -> {update.value:04x}, "
            f"change {changed_mask:04x}{order_note}"
        )
        if not shown:
            expected = "; ".join(
                f"{item.signal.name} bits {item.signal.bit_range} mask {item.signal.mask:04x}"
                for item in decoded[:4]
            )
            suffix = f"; expected: {expected}" if expected else ""
            return [f"{header} (no mapped CI changes{suffix})"]

    lines = [header]
    for item in shown[:max_signals]:
        lines.append(format_decoded_input_signal(item))
    if len(shown) > max_signals:
        lines.append(f"  - ... {len(shown) - max_signals} additional signals")
    return lines


def format_decoded_input_signal(item: DecodedInputSignal) -> str:
    signal = item.signal
    flag_text = " FLIP" if is_flipped_signal(signal) else ""
    comment = f" // {signal.comment}" if signal.comment else ""
    if item.previous_raw_value is None:
        value_text = f"raw {item.raw_value}, logical {item.logical_value}"
    else:
        value_text = (
            f"raw {item.previous_raw_value}->{item.raw_value}, "
            f"logical {item.previous_logical_value}->{item.logical_value}"
        )
    return (
        f"  - {signal.panel_name}.{signal.name} "
        f"w{signal.word} bits {signal.bit_range}: {value_text}{flag_text}{comment}"
    )


def signal_raw_value(signal: SignalDefinition, word_value: int) -> int:
    return (word_value & signal.mask) >> (15 - signal.end_bit)


def signal_logical_value(signal: SignalDefinition, raw_value: int) -> int:
    if is_flipped_signal(signal) and signal.width == 1:
        return 0 if raw_value else 1
    return raw_value


def is_flipped_signal(signal: SignalDefinition) -> bool:
    return FLIP_FLAG in signal.flags


def signal_flags_text(signal: SignalDefinition) -> str:
    return ", ".join(signal.flags)


def markdown_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")
