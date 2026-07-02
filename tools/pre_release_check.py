from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Step:
    name: str
    command: list[str]


def run_step(step: Step) -> None:
    print(f"\n== {step.name} ==", flush=True)
    completed = subprocess.run(
        step.command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout.rstrip(), flush=True)
    if completed.stderr:
        print(completed.stderr.rstrip(), flush=True)
    if completed.returncode != 0:
        raise RuntimeError(f"{step.name} fallo con codigo {completed.returncode}")


def pre_release_steps() -> list[Step]:
    python = sys.executable
    return [
        Step("Unit tests", [python, "-m", "unittest", "discover", "-s", "tests"]),
        Step("Compile check", [python, "-m", "compileall", "interface_tester", "tests", "tools", "main.py", "setup.py"]),
        Step("GUI smoke sin hardware", [python, "tools/gui_smoke.py"]),
        Step("Release readiness", [python, "tools/release_check.py"]),
        Step("EXE smoke", [python, "tools/exe_smoke.py"]),
    ]


def main() -> int:
    print("InterfaceTester pre-release check", flush=True)
    print("No genera ZIP ni modifica Releases.", flush=True)
    try:
        for step in pre_release_steps():
            run_step(step)
    except Exception as exc:  # noqa: BLE001 - command-line orchestration.
        print(f"\nPre-release check FAIL: {exc}", file=sys.stderr, flush=True)
        return 1

    print("\nPre-release check OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
