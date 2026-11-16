# PyInstaller spec: one-folder Windows build of the whole application.
# Run through packaging/build_windows.ps1, which prepares frontend/dist and the ngspice folder.
# ruff: noqa
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent  # repository root
NGSPICE = Path(os.environ["CIRCUITOS_BUNDLE_NGSPICE"])  # staged by the build script

datas = [
    (str(ROOT / "frontend" / "dist"), "frontend"),
    (str(ROOT / "data" / "components"), "data/components"),
    (str(ROOT / "data" / "datasheet-queue.yaml"), "data"),
    (str(NGSPICE), "ngspice"),
]
# YAML schemas, report templates, KaTeX, alias table…
datas += collect_data_files("circuitos", includes=["**/*.yaml", "**/*.j2", "**/*.css", "**/*.js", "**/*.woff2"])

hidden = collect_submodules("circuitos") + collect_submodules("uvicorn")

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "backend" / "src")],
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "pytest", "hypothesis", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Circuitos",
    console=True,  # the window shows the server log; closing it stops the application
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Circuitos")
