from __future__ import annotations

from typing import Iterable

from .input_logic import input_signals_by_word, markdown_cell, signal_flags_text
from .light_logic import (
    INTENSITY_MODE_RAW,
    PanelFamilyLightTest,
    PanelLightTest,
    command_target_label,
    signal_off_command,
    signal_on_command,
)
from .models import SignalDefinition
from .output_logic import special_output_category, special_outputs_by_word
from .panel_inventory import PanelCapabilityStats


def build_panel_capability_detail_text(
    target: PanelLightTest | PanelFamilyLightTest,
    input_signals: Iterable[SignalDefinition],
    output_signals: Iterable[SignalDefinition],
    stats: PanelCapabilityStats | None = None,
    metadata: dict[str, str] | None = None,
    intensity_mode: str = INTENSITY_MODE_RAW,
) -> str:
    input_list = sorted(
        input_signals,
        key=lambda item: (item.panel_name, item.word, item.start_bit, item.end_bit, item.name),
    )
    output_list = sorted(
        output_signals,
        key=lambda item: (item.panel_name, item.word, item.start_bit, item.end_bit, item.name),
    )
    stats = stats or capability_stats_from_target(target, input_list, output_list)

    lines = [
        "# Interface Tester Panel Capability Detail",
        "",
        f"Panel: {command_target_label(target)}",
    ]
    if metadata:
        for key, value in metadata.items():
            if value:
                lines.append(f"{key}: {value}")

    lines.extend(build_variant_section(target, input_list, output_list))
    lines.extend(build_capability_summary_section(stats))
    lines.extend(build_light_section(target, intensity_mode))
    lines.extend(build_input_section(input_list))
    lines.extend(build_output_section(output_list))
    lines.append("")
    return "\n".join(lines)


def capability_stats_from_target(
    target: PanelLightTest | PanelFamilyLightTest,
    input_signals: list[SignalDefinition],
    output_signals: list[SignalDefinition],
) -> PanelCapabilityStats:
    return PanelCapabilityStats(
        light_count=target.light_count,
        light_word_count=len(target.groups),
        input_count=len(input_signals),
        input_word_count=len({signal.word for signal in input_signals}),
        output_count=len(output_signals),
        output_word_count=len({signal.word for signal in output_signals}),
    )


def build_variant_section(
    target: PanelLightTest | PanelFamilyLightTest,
    input_signals: list[SignalDefinition],
    output_signals: list[SignalDefinition],
) -> list[str]:
    tests = (target,) if isinstance(target, PanelLightTest) else target.tests
    lines = [
        "",
        "## Variants",
        "",
        "| Panel | Channel | Address | Lights | Inputs | Outputs |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for test in tests:
        panel = test.panel
        channel = "" if panel.channel is None else str(panel.channel)
        address = "" if panel.address is None else str(panel.address)
        panel_inputs = sum(1 for signal in input_signals if signal.panel_name == panel.name)
        panel_outputs = sum(1 for signal in output_signals if signal.panel_name == panel.name)
        lines.append(
            "| "
            f"{markdown_cell(panel.name)} | "
            f"{channel} | "
            f"{address} | "
            f"{test.light_count} | "
            f"{panel_inputs} | "
            f"{panel_outputs} |"
        )
    return lines


def build_capability_summary_section(stats: PanelCapabilityStats) -> list[str]:
    return [
        "",
        "## Capability Summary",
        "",
        "| Capability | Signals | Words |",
        "|---|---:|---:|",
        f"| Lights CO | {stats.light_count} | {stats.light_word_count} |",
        f"| Inputs CI | {stats.input_count} | {stats.input_word_count} |",
        f"| Non-light CO outputs | {stats.output_count} | {stats.output_word_count} |",
    ]


def build_light_section(
    target: PanelLightTest | PanelFamilyLightTest,
    intensity_mode: str,
) -> list[str]:
    lines = [
        "",
        "## Light Commands",
        "",
    ]
    if not target.groups:
        lines.extend(["No CO lights are mapped with the current filter.", ""])
        return lines

    lines.extend(
        [
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
            "## Light Signals",
            "",
            "| Panel | Signal | Type | Word | Bits | ON | OFF | Comment |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for group in target.groups:
        for signal in group.signals:
            lines.append(
                "| "
                f"{markdown_cell(signal.panel_name)} | "
                f"{markdown_cell(signal.name)} | "
                f"{markdown_cell(signal.signal_type)} | "
                f"w{signal.word} | "
                f"{signal.bit_range} | "
                f"`{signal_on_command(signal, intensity_mode)}` | "
                f"`{signal_off_command(signal)}` | "
                f"{markdown_cell(signal.comment)} |"
            )
    return lines


def build_input_section(input_signals: list[SignalDefinition]) -> list[str]:
    lines = [
        "",
        "## Inputs CI",
        "",
    ]
    if not input_signals:
        lines.extend(["No CI inputs are mapped for this panel.", ""])
        return lines

    lines.extend(
        [
            "| Word | Inputs | Signals |",
            "|---|---:|---|",
        ]
    )
    for word, word_signals in input_signals_by_word(input_signals).items():
        signal_names = ", ".join(signal.name for signal in word_signals)
        lines.append(f"| w{word} | {len(word_signals)} | {markdown_cell(signal_names)} |")

    lines.extend(
        [
            "",
            "### Input Signals",
            "",
            "| Panel | Signal | Type | Word | Bits | Flags | Comment |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for signal in input_signals:
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
    return lines


def build_output_section(output_signals: list[SignalDefinition]) -> list[str]:
    lines = [
        "",
        "## Non-Light CO Outputs",
        "",
    ]
    if not output_signals:
        lines.extend(["No non-light CO outputs are mapped for this panel.", ""])
        return lines

    lines.extend(
        [
            "| Word | Categories | Outputs |",
            "|---|---|---:|",
        ]
    )
    for word, word_signals in special_outputs_by_word(output_signals).items():
        categories = ", ".join(sorted({special_output_category(signal) or "" for signal in word_signals}))
        lines.append(f"| w{word} | {markdown_cell(categories)} | {len(word_signals)} |")

    lines.extend(
        [
            "",
            "### Output Signals",
            "",
            "| Category | Panel | Signal | Type | Word | Bits | Flags | Comment |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for signal in output_signals:
        lines.append(
            "| "
            f"{markdown_cell(special_output_category(signal) or '')} | "
            f"{markdown_cell(signal.panel_name)} | "
            f"{markdown_cell(signal.name)} | "
            f"{markdown_cell(signal.signal_type)} | "
            f"w{signal.word} | "
            f"{signal.bit_range} | "
            f"{markdown_cell(signal_flags_text(signal))} | "
            f"{markdown_cell(signal.comment)} |"
        )
    return lines
