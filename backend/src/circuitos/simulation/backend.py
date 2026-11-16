"""Simulator backends behind a common interface (prompt, section 8).

``SharedNgspiceBackend`` drives ``libngspice`` through ctypes; ``BatchNgspiceBackend`` runs the
``ngspice`` executable and parses its rawfile. Both are meant to run inside a worker process
(see :mod:`circuitos.simulation.jobs`), because ngspice is not re-entrant.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar, Protocol

import numpy as np

from circuitos.core.errors import SimulationError, SimulatorUnavailableError
from circuitos.simulation.diagnostics import raise_for_log
from circuitos.simulation.rawfile import parse_rawfile
from circuitos.simulation.results import (
    Plot,
    SimulationResult,
    Vector,
    canonical_name,
    kind_for,
    unit_for,
)

ProgressCallback = Callable[[float, str], None]

_PROGRESS = re.compile(r"(\w+):\s*([\d.]+)%")


def _noop(_fraction: float, _message: str) -> None:
    return None


def normalise_netlist(netlist: str) -> list[str]:
    lines = netlist.strip().splitlines()
    if not lines:
        raise SimulationError("Netlist vazia")
    if lines[-1].strip().lower() != ".end":
        lines.append(".end")
    return lines


class SimulatorBackend(ABC):
    name: ClassVar[str]

    @classmethod
    @abstractmethod
    def available(cls) -> bool: ...

    @abstractmethod
    def run(self, netlist: str, progress: ProgressCallback = _noop) -> SimulationResult: ...


# ---------------------------------------------------------------------------------------------
# Batch (executable + rawfile)
# ---------------------------------------------------------------------------------------------


class BatchNgspiceBackend(SimulatorBackend):
    name = "ngspice-batch"

    def __init__(self, executable: str | None = None, timeout_s: float = 120.0):
        self.executable = executable or os.environ.get("CIRCUITOS_NGSPICE_EXE") or "ngspice"
        self.timeout_s = timeout_s

    @classmethod
    def available(cls) -> bool:
        exe = os.environ.get("CIRCUITOS_NGSPICE_EXE") or "ngspice"
        return shutil.which(exe) is not None

    def run(self, netlist: str, progress: ProgressCallback = _noop) -> SimulationResult:
        if shutil.which(self.executable) is None:
            raise SimulatorUnavailableError("Executável do ngspice não encontrado")
        start = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="circuitos-") as tmp:
            cir = Path(tmp) / "circuit.cir"
            raw = Path(tmp) / "circuit.raw"
            cir.write_text("\n".join(normalise_netlist(netlist)) + "\n", encoding="utf-8")
            progress(0.0, "iniciando ngspice")
            try:
                proc = subprocess.run(
                    [self.executable, "-b", "-r", str(raw), str(cir)],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s,
                    cwd=tmp,
                )
            except subprocess.TimeoutExpired as exc:
                raise SimulationError(
                    f"Tempo limite de {self.timeout_s:g} s excedido",
                    suggestions=["Reduza o tempo simulado ou aumente o passo máximo."],
                ) from exc
            log = proc.stdout + proc.stderr
            try:
                plots = parse_rawfile(raw.read_bytes()) if raw.exists() else []
            except ValueError:
                plots = []  # rawfile cut short by a fatal error: the log says why
        raise_for_log(log, no_output=not plots)
        progress(1.0, "concluído")
        return SimulationResult(
            backend=self.name, plots=plots, log=log, elapsed_s=time.perf_counter() - start
        )


# ---------------------------------------------------------------------------------------------
# Shared library (ctypes)
# ---------------------------------------------------------------------------------------------


class _VectorInfo(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, Any]]] = [
        ("v_name", ctypes.c_char_p),
        ("v_type", ctypes.c_int),
        ("v_flags", ctypes.c_short),
        ("v_realdata", ctypes.POINTER(ctypes.c_double)),
        ("v_compdata", ctypes.POINTER(ctypes.c_double)),  # ngcomplex_t = {double re, im}
        ("v_length", ctypes.c_int),
    ]


_SV_TYPES = {1: "time", 2: "frequency", 3: "voltage", 4: "current"}
_VF_COMPLEX = 2

_SendChar = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
_SendStat = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
_ControlledExit = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.c_int, ctypes.c_bool, ctypes.c_bool, ctypes.c_int, ctypes.c_void_p
)
_BGThreadRunning = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)


_GetVSRCData = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_double),
    ctypes.c_double,
    ctypes.c_char_p,
    ctypes.c_int,
    ctypes.c_void_p,
)


class CoSimulation(Protocol):
    """What the shared backend needs from a co-simulation session (``circuitos.cosim``)."""

    read: Callable[[str], float | None]  # last accepted value of a vector (set by the backend)

    def source(self, name: str, t: float) -> float: ...


def find_ngspice_library() -> str | None:
    explicit = os.environ.get("CIRCUITOS_NGSPICE_LIB")
    if explicit:
        return explicit
    found = ctypes.util.find_library("ngspice")
    if found:
        return found
    names = {
        "win32": ["ngspice.dll"],
        "darwin": ["libngspice.dylib", "libngspice.0.dylib"],
    }.get(sys.platform, ["libngspice.so.0", "libngspice.so"])
    for name in names:
        try:
            ctypes.CDLL(name)
        except OSError:
            continue
        return name
    return None


def _load_library(path: str) -> ctypes.CDLL:
    """Load libngspice. On Windows the DLL's own folder must be on the DLL search path, because
    the official build ships its dependencies (``libomp140.x86_64.dll``) next to it and Python
    3.8+ no longer searches there."""
    if sys.platform == "win32" and os.path.dirname(path):
        os.add_dll_directory(os.path.dirname(os.path.abspath(path)))
    return ctypes.CDLL(path)


class SharedNgspiceBackend(SimulatorBackend):
    """One instance per process: libngspice keeps global state."""

    name = "ngspice-shared"

    def __init__(self, library: str | None = None):
        path = library or find_ngspice_library()
        if path is None:
            raise SimulatorUnavailableError("Biblioteca compartilhada do ngspice não encontrada")
        try:
            self._lib = _load_library(path)
        except OSError as exc:
            raise SimulatorUnavailableError(f"Falha ao carregar {path}: {exc}") from exc
        self._log: list[str] = []
        self._exited = False
        self._progress: ProgressCallback = _noop
        # Keep references to the callbacks: ctypes would garbage-collect them otherwise.
        self._cb_char = _SendChar(self._on_char)
        self._cb_stat = _SendStat(self._on_stat)
        self._cb_exit = _ControlledExit(self._on_exit)
        self._cb_bg = _BGThreadRunning(lambda _running, _id, _user: 0)
        self._cosim: CoSimulation | None = None
        self._cb_vsrc = _GetVSRCData(self._on_vsrc)
        lib = self._lib
        lib.ngSpice_Init.argtypes = [
            _SendChar,
            _SendStat,
            _ControlledExit,
            ctypes.c_void_p,  # SendData: none (needs SendInitData, which crashes on bad input)
            ctypes.c_void_p,
            _BGThreadRunning,
            ctypes.c_void_p,
        ]
        lib.ngSpice_Init_Sync.argtypes = [
            _GetVSRCData,
            ctypes.c_void_p,
            ctypes.c_void_p,  # GetSyncData: none (it would alter the time step of every run)
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_void_p,
        ]
        lib.ngSpice_Command.argtypes = [ctypes.c_char_p]
        lib.ngSpice_Circ.argtypes = [ctypes.POINTER(ctypes.c_char_p)]
        lib.ngSpice_AllPlots.restype = ctypes.POINTER(ctypes.c_char_p)
        lib.ngSpice_AllVecs.argtypes = [ctypes.c_char_p]
        lib.ngSpice_AllVecs.restype = ctypes.POINTER(ctypes.c_char_p)
        lib.ngGet_Vec_Info.argtypes = [ctypes.c_char_p]
        lib.ngGet_Vec_Info.restype = ctypes.POINTER(_VectorInfo)
        lib.ngSpice_Init(
            self._cb_char,
            self._cb_stat,
            self._cb_exit,
            None,
            None,
            self._cb_bg,
            None,
        )
        self._ident = ctypes.c_int(0)
        self._synced = False

    @classmethod
    def available(cls) -> bool:
        return find_ngspice_library() is not None

    # callbacks ----------------------------------------------------------------------------
    def _on_char(self, text: bytes, _id: int, _user: object) -> int:
        line = text.decode("utf-8", "replace")
        for prefix in ("stdout ", "stderr "):
            if line.startswith(prefix):
                line = line[len(prefix) :]
        self._log.append(line)
        return 0

    def _on_stat(self, text: bytes, _id: int, _user: object) -> int:
        message = text.decode("utf-8", "replace")
        match = _PROGRESS.search(message)
        if match:
            self._progress(min(float(match.group(2)) / 100.0, 1.0), match.group(1))
        return 0

    def _on_exit(self, status: int, _unload: bool, _quit: bool, _id: int, _user: object) -> int:
        self._exited = True
        self._log.append(f"ngspice encerrou com status {status}")
        return 0

    def _read_last(self, name: str) -> float | None:
        """Last accepted point of a vector of the running analysis (co-simulation inputs)."""
        info_ptr = self._lib.ngGet_Vec_Info(name.encode())
        if not info_ptr:
            return None
        info = info_ptr.contents
        if info.v_length <= 0 or not info.v_realdata:
            return None
        return float(info.v_realdata[info.v_length - 1])

    def _on_vsrc(self, ret: Any, t: float, name: bytes, _id: int, _user: object) -> int:
        cosim = self._cosim
        ret[0] = cosim.source(name.decode(errors="replace"), t) if cosim is not None else 0.0
        return 0

    # helpers ------------------------------------------------------------------------------
    def _command(self, command: str) -> None:
        self._lib.ngSpice_Command(command.encode())

    @staticmethod
    def _strings(ptr: Any) -> list[str]:
        out: list[str] = []
        if not ptr:
            return out
        i = 0
        while ptr[i]:
            out.append(ptr[i].decode())
            i += 1
        return out

    def _read_plot(self, plot_name: str) -> Plot:
        kind = kind_for(plot_name)
        plot = Plot(name=plot_name, kind=kind, scale=None)
        for vec_name in self._strings(self._lib.ngSpice_AllVecs(plot_name.encode())):
            info_ptr = self._lib.ngGet_Vec_Info(f"{plot_name}.{vec_name}".encode())
            if not info_ptr:
                continue
            info = info_ptr.contents
            n = info.v_length
            if info.v_flags & _VF_COMPLEX and info.v_compdata:
                pairs = np.ctypeslib.as_array(info.v_compdata, shape=(n * 2,)).copy()
                data: np.ndarray[Any, Any] = pairs[0::2] + 1j * pairs[1::2]
            elif info.v_realdata:
                data = np.ctypeslib.as_array(info.v_realdata, shape=(n,)).copy()
            else:
                continue
            type_name = _SV_TYPES.get(info.v_type, "")
            name = canonical_name(vec_name, type_name)
            if plot.scale is None and (
                type_name in ("time", "frequency") or name.endswith("-sweep")
            ):
                plot.scale = name
                data = data.real if np.iscomplexobj(data) else data
            plot.vectors[name] = Vector(name, unit_for(type_name, name), data)
        return plot

    # public -------------------------------------------------------------------------------
    def run(
        self,
        netlist: str,
        progress: ProgressCallback = _noop,
        cosim: CoSimulation | None = None,
    ) -> SimulationResult:
        start = time.perf_counter()
        self._log.clear()
        self._progress = progress
        self._command("destroy all")
        self._command("remcirc")
        lines = normalise_netlist(netlist)
        array = (ctypes.c_char_p * (len(lines) + 1))(*[ln.encode() for ln in lines], None)
        self._lib.ngSpice_Circ(array)
        progress(0.0, "iniciando ngspice")
        if cosim is not None and not self._synced:
            # EXTERNAL sources (co-simulation, Fase 11) ask _on_vsrc for their value. Registered
            # only when needed: it is per process, and plain runs stay exactly as before.
            self._lib.ngSpice_Init_Sync(self._cb_vsrc, None, None, ctypes.byref(self._ident), None)
            self._synced = True
        self._cosim = cosim
        if cosim is not None:
            cosim.read = self._read_last
        try:
            self._command("run")
        finally:
            self._cosim = None
        log = "\n".join(self._log)
        plots = [
            self._read_plot(name)
            for name in self._strings(self._lib.ngSpice_AllPlots())
            if name != "const"
        ]
        plots = [p for p in plots if p.vectors]
        plots.reverse()  # ngspice lists the newest plot first
        raise_for_log(log, no_output=not plots or self._exited)
        progress(1.0, "concluído")
        return SimulationResult(
            backend=self.name, plots=plots, log=log, elapsed_s=time.perf_counter() - start
        )


def make_backend(preference: str = "auto", timeout_s: float = 120.0) -> SimulatorBackend:
    """Shared library first (faster, gives progress), executable as fallback."""
    if preference in ("auto", "shared") and SharedNgspiceBackend.available():
        try:
            return SharedNgspiceBackend()
        except SimulatorUnavailableError:
            if preference == "shared":
                raise
    if preference in ("auto", "batch") and BatchNgspiceBackend.available():
        return BatchNgspiceBackend(timeout_s=timeout_s)
    raise SimulatorUnavailableError(
        "ngspice não encontrado. Instale o ngspice ou defina CIRCUITOS_NGSPICE_LIB / "
        "CIRCUITOS_NGSPICE_EXE."
    )
