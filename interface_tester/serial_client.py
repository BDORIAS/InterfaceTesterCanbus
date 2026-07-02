from __future__ import annotations

import re
import time
from dataclasses import dataclass

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover - exercised only without pyserial installed.
    serial = None
    list_ports = None


NEWLINES = {
    "CR": "\r",
    "LF": "\n",
    "CRLF": "\r\n",
}


def line_payload(command: str, newline: str = "CR") -> bytes:
    suffix = NEWLINES.get(newline, NEWLINES["CR"])
    return f"{command}{suffix}".encode("ascii", errors="replace")


def decode_serial_bytes(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


class SerialLineBuffer:
    def __init__(self) -> None:
        self._pending = ""

    @property
    def pending(self) -> str:
        return self._pending

    def feed(self, text: str) -> list[str]:
        combined = f"{self._pending}{text}"
        parts = re.split(r"\r\n|\r|\n", combined)
        if combined.endswith(("\r", "\n")):
            self._pending = ""
            complete = parts
        else:
            self._pending = parts.pop() if parts else combined
            complete = parts
        return [line for line in complete if line]

    def flush(self) -> list[str]:
        if not self._pending:
            return []
        line = self._pending
        self._pending = ""
        return [line]


class SerialDependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class SerialPortInfo:
    device: str
    description: str
    hwid: str

    @property
    def display_name(self) -> str:
        if self.description and self.description != "n/a":
            return f"{self.device} - {self.description}"
        return self.device


@dataclass(frozen=True)
class BoardInfo:
    raw: str
    channel: int | None = None
    address: int | None = None
    firmware: str | None = None
    hardware: str | None = None
    baud_rate: int | None = None
    bus_status: str | None = None


def pyserial_available() -> bool:
    return serial is not None and list_ports is not None


def list_serial_ports() -> list[SerialPortInfo]:
    if not pyserial_available():
        return []
    return [
        SerialPortInfo(
            device=port.device,
            description=port.description or "",
            hwid=port.hwid or "",
        )
        for port in list_ports.comports()
    ]


class SerialConnection:
    def __init__(self) -> None:
        self._serial = None

    @property
    def is_open(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    def open(self, port: str, baudrate: int) -> None:
        if serial is None:
            raise SerialDependencyError("pyserial is not installed.")
        self.close()
        self._serial = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=8,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.1,
            write_timeout=1,
        )

    def close(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None

    def send_line(self, command: str, newline: str = "CR") -> None:
        if not self.is_open:
            raise RuntimeError("Serial port is not open.")
        payload = line_payload(command, newline)
        self._serial.write(payload)
        self._serial.flush()

    def read_available_bytes(self) -> bytes:
        if not self.is_open:
            return b""
        waiting = self._serial.in_waiting
        if waiting <= 0:
            return b""
        return self._serial.read(waiting)

    def read_available(self) -> str:
        return decode_serial_bytes(self.read_available_bytes())

    def read_until_quiet(
        self,
        wait_seconds: float = 1.2,
        quiet_seconds: float = 0.25,
        max_total_seconds: float = 15.0,
    ) -> str:
        if not self.is_open:
            return ""

        wait_seconds = max(0.0, wait_seconds)
        quiet_seconds = max(0.0, quiet_seconds)
        chunks: list[str] = []
        started_at = time.monotonic()
        first_byte_deadline = started_at + wait_seconds
        overall_deadline = started_at + max(wait_seconds, max_total_seconds)
        last_data = started_at

        while time.monotonic() < overall_deadline:
            data = self.read_available()
            if data:
                chunks.append(data)
                last_data = time.monotonic()
                continue
            now = time.monotonic()
            if chunks and now - last_data >= quiet_seconds:
                break
            if not chunks and now >= first_byte_deadline:
                break
            time.sleep(0.03)

        return "".join(chunks)

    def request_info(
        self,
        newline: str = "CR",
        wait_seconds: float = 1.2,
        quiet_seconds: float = 0.25,
    ) -> BoardInfo:
        raw = self.request_command("i", newline, wait_seconds, quiet_seconds)
        return parse_board_info(raw)

    def request_command(
        self,
        command: str,
        newline: str = "CR",
        wait_seconds: float = 1.2,
        quiet_seconds: float = 0.25,
    ) -> str:
        if not self.is_open:
            raise RuntimeError("Serial port is not open.")

        self._serial.reset_input_buffer()
        self.send_line(command, newline)

        return self.read_until_quiet(wait_seconds, quiet_seconds)


def parse_board_info(raw: str) -> BoardInfo:
    channel = None
    address = None
    firmware = None
    hardware = None
    baud_rate = None
    bus_status = None

    full_address = re.search(r"@(\d+)\.(\d+)", raw)
    if full_address:
        channel = int(full_address.group(1))
        address = int(full_address.group(2))

    if channel is None:
        channel_match = re.search(r"(?i)\b(?:channel|canal|ch)\D{0,12}(\d{1,3})\b", raw)
        if channel_match:
            channel = int(channel_match.group(1))

    if address is None:
        address_match = re.search(
            r"(?i)\b(?:address|addr|direccion|direcci.n)\D{0,16}(\d{1,3})\b",
            raw,
        )
        if address_match:
            address = int(address_match.group(1))

    firmware_match = re.search(
        r"(?im)^\s*(?:firmware(?:\s+version)?|software\s+version|fw)\s*"
        r"(?:[#:=\-]+\s*)?(?:v(?:ersion)?[.#]?\s*)?([0-9]+(?:[._-][A-Za-z0-9]+)*)",
        raw,
    )
    if firmware_match:
        firmware = firmware_match.group(1)

    hardware_match = re.search(
        r"(?im)^\s*(?:hardware(?:\s+version)?|hw)\s*[:=\- ]+\s*([A-Za-z0-9_.-]+)",
        raw,
    )
    if hardware_match:
        hardware = hardware_match.group(1)

    baud_match = re.search(r"(?im)^\s*(?:baud(?:\s*rate)?)\s*[:=\- ]+\s*(\d{3,7})\b", raw)
    if baud_match:
        baud_rate = int(baud_match.group(1))

    bus_match = re.search(r"(?im)^\s*bus(?:\s+status)?\s*[:=\- ]+\s*(ok|warning|bus\s+off|off|error)\b", raw)
    if bus_match:
        bus_status = " ".join(bus_match.group(1).title().split())

    return BoardInfo(
        raw=raw,
        channel=channel,
        address=address,
        firmware=firmware,
        hardware=hardware,
        baud_rate=baud_rate,
        bus_status=bus_status,
    )
