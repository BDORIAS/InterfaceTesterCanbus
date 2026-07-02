from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXE_PATH = ROOT / "dist" / "InterfaceTester" / "InterfaceTester.exe"


def read_app_version() -> str:
    init_path = ROOT / "interface_tester" / "__init__.py"
    match = re.search(r'__version__\s*=\s*"([^"]+)"', init_path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"No se pudo leer __version__ desde {init_path}")
    return match.group(1)


def powershell_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run_exe_smoke(timeout_seconds: int = 12) -> list[str]:
    version = read_app_version()
    if not EXE_PATH.exists():
        raise FileNotFoundError(f"No existe el ejecutable: {EXE_PATH}")

    ps_script = f"""
$ErrorActionPreference = "Stop"
$exe = {powershell_literal(str(EXE_PATH))}
$expectedTitle = {powershell_literal(f"Interface Tester v{version}")}
$process = Start-Process -FilePath $exe -PassThru
$deadline = (Get-Date).AddSeconds({timeout_seconds})
$title = ""
$handle = 0
while ((Get-Date) -lt $deadline) {{
    $process.Refresh()
    if ($process.HasExited) {{
        throw "InterfaceTester.exe se cerro antes de mostrar ventana. ExitCode=$($process.ExitCode)"
    }}
    if ($process.MainWindowHandle -ne 0 -and -not [string]::IsNullOrWhiteSpace($process.MainWindowTitle)) {{
        $title = $process.MainWindowTitle
        $handle = $process.MainWindowHandle
        break
    }}
    Start-Sleep -Milliseconds 250
}}
if ([string]::IsNullOrWhiteSpace($title) -or $handle -eq 0) {{
    Stop-Process -Id $process.Id -Force
    throw "InterfaceTester.exe arranco, pero no se detecto ventana principal visible."
}}
if ($title -ne $expectedTitle) {{
    $closed = $process.CloseMainWindow()
    Start-Sleep -Seconds 1
    $process.Refresh()
    if (-not $process.HasExited) {{
        Stop-Process -Id $process.Id -Force
    }}
    throw "Titulo inesperado: '$title' (esperado '$expectedTitle')"
}}
$closed = $process.CloseMainWindow()
Start-Sleep -Seconds 2
$process.Refresh()
$forced = $false
if (-not $process.HasExited) {{
    Stop-Process -Id $process.Id -Force
    $forced = $true
}}
"pid=$($process.Id)"
"title=$title"
"handle=$handle"
"forced_close=$forced"
"""
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
        raise RuntimeError(output or f"PowerShell smoke fallo con codigo {completed.returncode}")

    return [line for line in completed.stdout.splitlines() if line.strip()]


def main() -> int:
    try:
        lines = run_exe_smoke()
    except Exception as exc:  # noqa: BLE001 - command-line smoke for release.
        print(f"EXE smoke FAIL: {exc}", file=sys.stderr)
        return 1

    print("EXE smoke OK")
    for line in lines:
        print(f"- {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
