"""Entry point of the packaged application (PyInstaller).

Points the back end at the files bundled next to the executable: the compiled interface, the
component catalogue and ngspice. Anything the user already set in the environment wins, so a
local ngspice or another catalogue folder can still be used.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _bundle_dir() -> Path:
    frozen = getattr(sys, "_MEIPASS", None)
    return Path(frozen) if frozen else Path(__file__).resolve().parent


def configure() -> None:
    base = _bundle_dir()
    os.environ.setdefault("CIRCUITOS_FRONTEND_DIST", str(base / "frontend"))
    os.environ.setdefault("CIRCUITOS_CATALOG_DIR", str(base / "data" / "components"))
    os.environ.setdefault("CIRCUITOS_DATASHEET_QUEUE", str(base / "data" / "datasheet-queue.yaml"))
    exe = base / "ngspice" / "bin" / "ngspice_con.exe"
    dll = base / "ngspice" / "dll" / "ngspice.dll"
    if exe.exists():
        os.environ.setdefault("CIRCUITOS_NGSPICE_EXE", str(exe))
    if dll.exists():
        os.environ.setdefault("CIRCUITOS_NGSPICE_LIB", str(dll))


def main() -> None:
    configure()
    # worker processes of the simulation queue re-enter here on Windows (spawn)
    import multiprocessing

    multiprocessing.freeze_support()
    from circuitos.__main__ import main as run

    run()


if __name__ == "__main__":
    main()
