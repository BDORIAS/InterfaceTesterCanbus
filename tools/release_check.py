from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist" / "InterfaceTester"
RELEASES_DIR = ROOT / "Releases"
@dataclass(frozen=True)
class CheckResult:
    status: str
    message: str


def read_app_version() -> str:
    init_path = ROOT / "interface_tester" / "__init__.py"
    match = re.search(r'__version__\s*=\s*"([^"]+)"', init_path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"No se pudo leer __version__ desde {init_path}")
    return match.group(1)


def directory_size(path: Path) -> tuple[int, int]:
    files = [item for item in path.rglob("*") if item.is_file()]
    return len(files), sum(item.stat().st_size for item in files)


def check_release_readiness() -> tuple[str, list[CheckResult]]:
    version = read_app_version()
    package_name = f"InterfaceTester-v{version}-win"
    results: list[CheckResult] = []

    exe_path = DIST_DIR / "InterfaceTester.exe"
    if exe_path.exists() and exe_path.stat().st_size > 0:
        results.append(CheckResult("OK", f"Ejecutable encontrado: {exe_path}"))
    else:
        results.append(CheckResult("FAIL", f"No existe ejecutable valido: {exe_path}"))

    embedded_definitions = sorted(DIST_DIR.glob("InterfaceDefinition/*.dat"))
    if embedded_definitions:
        results.append(CheckResult("WARN", f"Dist contiene {len(embedded_definitions)} definiciones .dat embebidas"))
    else:
        results.append(CheckResult("OK", "Sin definiciones .dat embebidas; se cargan externamente desde la GUI"))

    if (DIST_DIR / "python312.dll").exists():
        results.append(CheckResult("OK", "Runtime Python incluido"))
    else:
        results.append(CheckResult("FAIL", "Falta python312.dll en dist"))

    if (DIST_DIR / "lib").exists() and (DIST_DIR / "share").exists():
        results.append(CheckResult("OK", "Dependencias cx_Freeze incluidas"))
    else:
        results.append(CheckResult("FAIL", "Faltan carpetas lib/share de cx_Freeze"))

    if DIST_DIR.exists():
        file_count, total_bytes = directory_size(DIST_DIR)
        results.append(CheckResult("OK", f"Dist contiene {file_count} archivos ({total_bytes / (1024 * 1024):.1f} MB)"))
    else:
        results.append(CheckResult("FAIL", f"No existe carpeta dist: {DIST_DIR}"))

    current_zip = RELEASES_DIR / f"{package_name}.zip"
    current_folder = RELEASES_DIR / package_name
    if current_zip.exists() or current_folder.exists():
        results.append(CheckResult("WARN", f"Ya existe release para {package_name}; revisar antes de regenerar"))
    else:
        results.append(CheckResult("OK", f"No hay ZIP/carpeta release existente para {package_name}"))

    return version, results


def main() -> int:
    try:
        version, results = check_release_readiness()
    except Exception as exc:  # noqa: BLE001 - command-line readiness check.
        print(f"Release check FAIL: {exc}", file=sys.stderr)
        return 1

    fail_count = sum(1 for result in results if result.status == "FAIL")
    warn_count = sum(1 for result in results if result.status == "WARN")

    print(f"InterfaceTester release check v{version}")
    for result in results:
        print(f"[{result.status}] {result.message}")

    if fail_count:
        print(f"Release check FAIL: {fail_count} error(es), {warn_count} advertencia(s)", file=sys.stderr)
        return 1

    print(f"Release check OK: {warn_count} advertencia(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
