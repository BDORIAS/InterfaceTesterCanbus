from __future__ import annotations

import sys
from pathlib import Path

from cx_Freeze import Executable, setup

from interface_tester import __version__


ROOT = Path(__file__).resolve().parent
DEFINITIONS_DIR = ROOT / "InterfaceDefinition"

include_files = []
if DEFINITIONS_DIR.exists() and any(DEFINITIONS_DIR.glob("*.dat")):
    include_files.append((str(DEFINITIONS_DIR), "InterfaceDefinition"))

build_exe_options = {
    "build_exe": str(ROOT / "dist" / "InterfaceTester"),
    "include_files": include_files,
    "packages": [
        "interface_tester",
    ],
    "excludes": [
        "unittest",
        "test",
        "tkinter.test",
        "pydoc_data",
        "email",
        "html",
        "http",
        "xmlrpc",
    ],
    "include_msvcr": True,
    "optimize": 2,
}

base = "Win32GUI" if sys.platform == "win32" else None

setup(
    name="InterfaceTester",
    version=__version__,
    description="Direct Mode panel interface tester for TSP/CANbus hardware",
    author="CAE",
    options={"build_exe": build_exe_options},
    executables=[
        Executable(
            script="main.py",
            base=base,
            target_name="InterfaceTester.exe",
            copyright="Copyright (c) CAE",
        )
    ],
)
