from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PanelDefinition:
    name: str
    source_file: str
    line: int
    channel: int | None = None
    address: int | None = None
    target: str | None = None

    @property
    def display_name(self) -> str:
        if self.channel is not None and self.address is not None:
            return f"{self.name}  @{self.channel}.{self.address}"
        if self.target:
            return f"{self.name}  {self.target}"
        return self.name


@dataclass(frozen=True)
class SignalDefinition:
    name: str
    direction: str
    panel_name: str
    signal_type: str
    word: int
    start_bit: int
    end_bit: int
    comment: str
    source_file: str
    line: int
    raw_line: str
    flags: tuple[str, ...] = ()

    @property
    def width(self) -> int:
        return self.end_bit - self.start_bit + 1

    @property
    def mask(self) -> int:
        if self.start_bit < 0 or self.end_bit > 15 or self.end_bit < self.start_bit:
            raise ValueError(
                f"Invalid bit range {self.start_bit}-{self.end_bit} "
                f"for {self.name} at {self.source_file}:{self.line}"
            )
        return ((1 << self.width) - 1) << (15 - self.end_bit)

    @property
    def bit_range(self) -> str:
        return (
            str(self.start_bit)
            if self.start_bit == self.end_bit
            else f"{self.start_bit}-{self.end_bit}"
        )


@dataclass(frozen=True)
class AircraftDefinition:
    name: str
    path: Path
    panels: dict[str, PanelDefinition]
    signals: list[SignalDefinition]
    metadata: dict[str, str] = field(default_factory=dict)

    def panels_by_address(self, address: int) -> list[PanelDefinition]:
        return [
            panel
            for panel in self.panels.values()
            if panel.address == address
        ]
