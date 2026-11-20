"""Run a schematic with controllers: time step, the ngspice run with a session, the result."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from circuitos.components.models import ComponentRecord
from circuitos.cosim.arduino import BOARDS
from circuitos.cosim.engine import CoSession
from circuitos.schematic.model import Schematic
from circuitos.schematic.netlist import Netlist, SchematicError, build_netlist
from circuitos.schematic.values import format_value, try_parse
from circuitos.simulation.results import RunInfo, SimulationResult

Progress = Callable[[float, str], None]


def time_step(sch: Schematic, nominal: Netlist) -> float:
    """Largest time step that lets every controller see its own timing.

    tstop/20000 bounded to 10 µs .. 2 ms; at most half a PLC scan; with switched PWM, 1/40 of
    the PWM period; 20 µs with a stepper driver (it must see each STEP pulse); 1/40 of the
    carrier with an SPWM inverter. A smaller step given by the user is kept.
    """
    tran = next((a for a in sch.analyses if a.enabled and a.kind == "tran"), None)
    if tran is None:
        raise SchematicError(
            "A co-simulação com controladores precisa da análise transitória (.tran)"
        )
    tstop = try_parse(tran.params.get("tstop", "10m")) or 10e-3
    step = min(max(tstop / 20000, 1e-5), 2e-3)
    for spec in nominal.controllers:
        if spec.kind == "plc":
            scan = (try_parse(spec.params.get("scan_ms", "10")) or 10) / 1000
            step = min(step, scan / 2)
        elif spec.kind == "stepper_driver":
            step = min(step, 20e-6)
        elif spec.params.get("pwm") == "chaveado":
            freqs = BOARDS[spec.kind].pwm.values()
            if freqs:
                step = min(step, 1 / (40 * max(freqs)))
    user = try_parse(tran.params.get("tmax", "") or "")
    if user is not None and user > 0:
        step = min(step, user)
    return step


def run_cosim(
    sch: Schematic,
    records: Mapping[str, ComponentRecord],
    nominal: Netlist,
    backend: Any,
    progress: Progress,
    add_probes: Callable[[Any, list[Any]], None],
) -> SimulationResult:
    start = time.perf_counter()
    if sch.sweep.kind != "none":
        raise SchematicError(
            "A co-simulação com controladores ainda não aceita varredura, Monte Carlo ou pior "
            "caso: desligue a varredura"
        )
    if getattr(backend, "name", "") != "ngspice-shared":
        raise SchematicError(
            "A co-simulação precisa da biblioteca compartilhada do ngspice (simulador "
            "'compartilhado'); o executável em lote não chama o programa durante a simulação"
        )
    step = time_step(sch, nominal)
    sch2 = sch.model_copy(deep=True)
    for a in sch2.analyses:
        if a.kind == "tran":
            a.params["tmax"] = format_value(step, 4)
    nl = build_netlist(sch2, records)
    session = CoSession(nl.controllers, nl.digital_sensors)
    progress(0.0, "co-simulando (programa e circuito)")
    res = backend.run(nl.text, progress, cosim=session)
    if session.errors:
        raise SchematicError(session.errors[0])
    for p in res.plots:
        add_probes(p, nl.probes)
        p.base = p.name
        if p.kind == "tran":
            session.finish(p)
    progress(1.0, "concluído")
    return SimulationResult(
        backend=getattr(backend, "name", "ngspice"),
        plots=res.plots,
        log=res.log,
        warnings=list(dict.fromkeys(nl.warnings + res.warnings + session.warnings)),
        elapsed_s=time.perf_counter() - start,
        runs=[RunInfo(0, "", {})],
        summary={
            "kind": "none",
            "cosim": {
                "step": step,
                "controllers": [s.ref for s in nl.controllers],
                "serial": {k: [[t, text] for t, text in v] for k, v in session.serial.items()},
            },
        },
    )
