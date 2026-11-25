"""Stateful transient bench. One isolated ngspice process per session, stop/alter/resume.

ngspice manual, interactive interpreter: Stop, Alter and Resume. No operating-point restart
between acquisitions. Polling drives bounded chunks, so closing the page stops computation.
"""

from __future__ import annotations

import ctypes
import multiprocessing as mp
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from circuitos.components.models import ComponentRecord
from circuitos.schematic.library import element_name, param, pin_defs
from circuitos.schematic.model import Analysis, Probe, Schematic
from circuitos.schematic.netlist import Netlist, SchematicError, build_netlist
from circuitos.schematic.runs import add_probe_vectors
from circuitos.schematic.values import parse_value
from circuitos.simulation.backend import SharedNgspiceBackend
from circuitos.simulation.diagnostics import raise_for_log
from circuitos.simulation.results import Plot

SOURCES = re.compile(r"[vi](dc|sin|pulse|pwl)")
SWITCHES = {"switch_manual", "tact_switch", "tact_switch4", "push_nc"}
MAX_POINTS = 5_000_000
MAX_WINDOWS = 10_000
TAIL = 4000


@dataclass
class BenchPlan:
    schematic: Schematic
    records: dict[str, ComponentRecord]
    window: float
    step: float
    netlist: Netlist
    sources: dict[str, list[str]]
    signature: str


def prepare(sch: Schematic, records: dict[str, ComponentRecord], window: float) -> BenchPlan:
    """Instrument every two-terminal branch once; probes can then move without rewiring."""
    if not 1e-6 <= window <= 1:
        raise SchematicError("O intervalo de aquisição deve ficar entre 1 µs e 1 s.")
    if sch.sweep.kind != "none":
        raise SchematicError("Desative a varredura para usar a bancada interativa.")
    if sch.directives.strip():
        raise SchematicError("Nesta etapa, a bancada interativa não aceita diretivas SPICE extras.")
    circuit = sch.model_copy(deep=True)
    circuit.probes = [
        Probe(id=f"live-{c.ref}", name=f"i({c.ref.lower()})", kind="i", component=c.ref)
        for c in circuit.components
        if c.kind != "ground" and len(pin_defs(c)) == 2
    ]
    tran = next((a for a in sch.analyses if a.enabled and a.kind == "tran"), None)
    step = (
        min(window / 1000, parse_value(tran.params["tmax"]))
        if tran and tran.params.get("tmax")
        else window / 1000
    )
    if not np.isfinite(step) or step <= 0 or window / step > 20_000:
        raise SchematicError(
            "Passo inválido ou mais de 20.000 passos por aquisição. Reduza o intervalo."
        )
    circuit.analyses = [Analysis(kind="op")]
    nl = build_netlist(circuit, records)
    external = re.search(r"^[vi]\S+\s+\S+\s+\S+\s+external(?:\s|$)", nl.text, re.I | re.M)
    if nl.controllers or nl.digital_sensors or external:
        raise SchematicError(
            "Use Simular para firmware/CLP ou sensores digitais; esta etapa da bancada é analógica."
        )
    lines = nl.text.splitlines()
    sources: dict[str, list[str]] = {}
    signature = []
    for index, line in enumerate(lines):
        fields = line.split()
        name = fields[0] if fields else ""
        comp = next(
            (
                c
                for c in circuit.components
                if element_name(c).lower() == name.lower() and SOURCES.fullmatch(c.kind)
            ),
            None,
        )
        switch = next(
            (
                c
                for c in circuit.components
                if c.kind in SWITCHES and name.lower() == f"b{c.ref}_ctl".lower()
            ),
            None,
        )
        if comp:
            wave = re.search(r"\b(SIN|PULSE|PWL)\(([^)]*)\)", line, re.I)
            if wave:
                values = [parse_value(v) for v in wave[2].split()]
                if not all(np.isfinite(v) for v in values):
                    raise SchematicError("Parâmetro de fonte não finito.")
                if wave[1].upper() == "SIN" and values[2] <= 0:
                    raise SchematicError("Use frequência positiva na bancada interativa.")
                numbers = " ".join(f"{v:.17g}" for v in values)
                command = f"alter @{name}[{wave[1].lower()}] = [ {numbers} ]"
                period = (
                    1 / values[2]
                    if wave[1].upper() == "SIN" and values[2] > 0
                    else (values[6] if wave[1].upper() == "PULSE" else None)
                )
                if period is not None and period > 0 and step > period / 20:
                    raise SchematicError(
                        f"{comp.ref}: menos de 20 pontos por período. "
                        "Reduza o intervalo de aquisição ou o passo máximo antes de iniciar."
                    )
            else:
                value = parse_value(fields[fields.index("DC") + 1])
                if not np.isfinite(value):
                    raise SchematicError("Valor de fonte não finito.")
                command = f"alter @{name}[dc] = {value:.17g}"
            dc = parse_value(fields[fields.index("DC") + 1])
            sources[comp.ref] = [f"alter @{name}[dc] = {dc:.17g}", command]
            repeat = param(comp, "repeat") if comp.kind.endswith("pwl") else ""
            signature.append(f"{name} {fields[1]} {fields[2]} {comp.kind} repeat={repeat}")
        elif switch:
            value = parse_value(param(switch, "state"))
            if value not in (0, 1):
                raise SchematicError(f"{switch.ref}: use estado 0 ou 1 na bancada interativa.")
            if switch.kind == "push_nc":
                value = 1 - value
            source = f"vlive_{switch.ref}"
            line = f"{source} {fields[1]} {fields[2]} DC {value:g}"
            sources[switch.ref] = [f"alter @{source}[dc] = {value:g}"]
            signature.append(f"{source} {fields[1]} {fields[2]}")
        else:
            signature.append(line)
        if fields and name.lower().startswith("b") and switch:
            lines[index] = line
    nl.text = "\n".join(lines)
    return BenchPlan(
        sch.model_copy(deep=True), records, window, step, nl, sources, "\n".join(signature)
    )


class TransientBench(SharedNgspiceBackend):
    def __init__(self, plan: BenchPlan):
        super().__init__()
        self.plan = plan
        self.windows = 0
        self._command("destroy all")
        self._command("remcirc")
        lines = plan.netlist.text.splitlines()
        array = (ctypes.c_char_p * (len(lines) + 1))(*[ln.encode() for ln in lines], None)
        self._lib.ngSpice_Circ(array)

    def advance(self, controls: dict[str, dict[str, str]]) -> dict[str, Any]:
        if self.windows >= MAX_WINDOWS:
            raise SchematicError("Limite da sessão atingido. Pare e reinicie para nova aquisição.")
        self._log.clear()
        if controls:
            sch = self.plan.schematic.model_copy(deep=True)
            for ref, params in controls.items():
                if ref not in self.plan.sources:
                    raise SchematicError(f"{ref}: controle não disponível durante a execução.")
                comp = sch.component(ref)
                if comp.kind in SWITCHES and set(params) != {"state"}:
                    raise SchematicError("Durante a execução, altere apenas o estado da chave.")
                comp.params.update(params)
            changed = prepare(sch, self.plan.records, self.plan.window)
            if changed.signature != self.plan.signature or changed.step != self.plan.step:
                raise SchematicError("A alteração exige reiniciar a bancada.")
            for ref in controls:
                for command in changed.sources[ref]:
                    self._command(command)
            self.plan = changed
        target = (self.windows + 1) * self.plan.window
        self._command("delete all")
        self._command(f"stop when time = {target:.17g}")
        if self.windows:
            self._command("resume")
        else:
            step = self.plan.step
            horizon = self.plan.window * (MAX_WINDOWS + 1)
            self._command(f"tran {step:.17g} {horizon:.17g} 0 {step:.17g}")
        self.windows += 1
        now = self._read_last("time")
        raise_for_log("\n".join(self._log), no_output=now is None or self._exited)
        if now is None or abs(now - target) > max(1e-12, self.plan.window * 1e-6):
            raise SchematicError("A transitória não avançou até o instante solicitado.")
        plot_name = self._strings(self._lib.ngSpice_AllPlots())[0]
        # Read only a bounded tail, without copying the growing native plot into Python.
        info = self._lib.ngGet_Vec_Info(f"{plot_name}.time".encode()).contents
        size = info.v_length * len(self._strings(self._lib.ngSpice_AllVecs(plot_name.encode())))
        if info.v_length > MAX_POINTS or size > 50_000_000:
            raise SchematicError("Limite de pontos atingido. Pare e reinicie a bancada.")
        plot = self._tail_plot(plot_name)
        add_probe_vectors(plot, self.plan.netlist.probes)
        exposed = {pv.name.lower() for pv in self.plan.netlist.probes} | {
            f"v({node.lower()})"
            for pins in self.plan.netlist.pin_nodes.values()
            for node in pins.values()
            if node != "0"
        }
        if not all(np.isfinite(v.data).all() for v in plot.vectors.values()):
            raise SchematicError("A simulação produziu valores não finitos; confira o circuito.")
        return {
            "time": now,
            "data": {
                "x": {"unit": "s", "values": plot.vectors["time"].data.tolist()},
                "traces": {
                    k: {"unit": v.unit, "values": v.data.tolist()}
                    for k, v in plot.vectors.items()
                    if k in exposed and v.unit in ("V", "A")
                },
            },
        }

    def _tail_plot(self, name: str) -> Plot:
        from circuitos.simulation.results import Plot, Vector, canonical_name, unit_for

        plot = Plot(name=name, kind="tran", scale="time")
        wanted = (
            {"time"}
            | {pv.expr.lower() for pv in self.plan.netlist.probes}
            | {
                f"v({node.lower()})"
                for pins in self.plan.netlist.pin_nodes.values()
                for node in pins.values()
                if node != "0"
            }
        )
        for key in self._strings(self._lib.ngSpice_AllVecs(name.encode())):
            ptr = self._lib.ngGet_Vec_Info(f"{name}.{key}".encode())
            if not ptr or not ptr.contents.v_realdata:
                continue
            info = ptr.contents
            kind = {1: "time", 3: "voltage", 4: "current"}.get(info.v_type, "")
            canonical = canonical_name(key, kind)
            if canonical not in wanted:
                continue
            start = max(0, info.v_length - TAIL)
            data = np.ctypeslib.as_array(info.v_realdata, shape=(info.v_length,))[start:].copy()
            plot.vectors[canonical] = Vector(canonical, unit_for(kind, canonical), data)
        return plot


def _worker(pipe: Any, plan: BenchPlan) -> None:
    try:
        bench = TransientBench(plan)
        pipe.send({"ready": True})
        while pipe.poll(900):
            controls = pipe.recv()
            pipe.send(bench.advance(controls))
    except EOFError:
        pass
    except Exception as exc:
        pipe.send({"error": str(exc)})
    finally:
        pipe.close()


@dataclass
class Session:
    process: Any
    pipe: Any
    touched: float = field(default_factory=time.monotonic)
    lock: Any = field(default_factory=threading.Lock)


class BenchSessions:
    """Bounded ownership, command serialization, timeout and idle-worker cleanup."""

    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.lock = threading.RLock()

    def start(self, plan: BenchPlan) -> str:
        with self.lock:
            for key, session in list(self.sessions.items()):
                if time.monotonic() - session.touched > 900:
                    self.stop(key)
            if len(self.sessions) >= 2:
                raise SchematicError(
                    "Já há duas bancadas abertas. Pare uma delas antes de iniciar outra."
                )
            ctx = mp.get_context("spawn")
            parent, child = ctx.Pipe()
            process = ctx.Process(target=_worker, args=(child, plan), daemon=True)
            try:
                process.start()
            except Exception as exc:
                parent.close()
                child.close()
                raise SchematicError("Não foi possível iniciar o processo da bancada.") from exc
            child.close()
            key = uuid.uuid4().hex
            self.sessions[key] = Session(process, parent)
        try:
            self._receive(key)
        except Exception:
            self.stop(key)
            raise
        return key

    def _receive(self, key: str) -> dict[str, Any]:
        session = self.sessions[key]
        if not session.pipe.poll(15):
            raise SchematicError(
                "A bancada excedeu 15 s por aquisição. Reduza o intervalo ou aumente o passo."
            )
        try:
            result: dict[str, Any] = session.pipe.recv()
        except EOFError as exc:
            raise SchematicError("O processo do simulador encerrou.") from exc
        if "error" in result:
            raise SchematicError(result["error"])
        return result

    def advance(self, key: str, controls: dict[str, dict[str, str]]) -> dict[str, Any]:
        session = self.sessions[key]
        with session.lock:
            session.touched = time.monotonic()
            try:
                session.pipe.send(controls)
                return self._receive(key)
            except Exception:
                self.stop(key)
                raise

    def stop(self, key: str) -> None:
        with self.lock:
            session = self.sessions.pop(key, None)
        if session:
            if session.process.is_alive():
                session.process.terminate()
            session.process.join(timeout=2)
            session.pipe.close()

    def close(self) -> None:
        for key in list(self.sessions):
            self.stop(key)
