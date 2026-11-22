"""Suggested ``.tran`` settings read from the circuit: final time, output step and maximum step.

The time scales come from the schematic itself:

* periods of the excitations: sine sources (1/f), pulse sources (period, width and delay),
  PWL breakpoints, three-phase sources and the SPWM carrier of drives;
* first-order time constants of each capacitor and inductor with the resistors that touch
  its nodes (an estimate: τ = C·(R₁‖R₂‖…) and τ = L/(R₁ + R₂ + …), as in the Thévenin
  resistance of a single RC or RL branch);
* the resonance period 2π√(LC) of each inductor that shares a node with a capacitor;
* start-up ramps of drives and soft starters.

The rules are the usual ones for a transient run (ngspice manual, ``.tran``: without TMAX the
step is limited only by min(TSTEP, (TSTOP − TSTART)/50), which skips fast signals in a long
run): simulate several periods and five time constants, and limit the step to a fraction of the
fastest period or time constant. Every number is recorded as a calculation step, so the
suggestion can be checked and edited.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping
from dataclasses import dataclass, field

from circuitos.core.calc import BibRef, CalcStep, record
from circuitos.core.units import q
from circuitos.schematic.library import param
from circuitos.schematic.model import Component, Schematic
from circuitos.schematic.values import format_value, try_parse

NGSPICE_MANUAL = BibRef(book="ngspice User's Manual", chapter=".tran (transient analysis)")
HAYT_RC = BibRef(
    book="Hayt, Kemmerly & Durbin, Engineering Circuit Analysis",
    edition="8th",
    chapter="8 (basic RL and RC circuits)",
)
HAYT_RLC = BibRef(
    book="Hayt, Kemmerly & Durbin, Engineering Circuit Analysis",
    edition="8th",
    chapter="9 (the RLC circuit)",
)

CYCLES = 5  # periods of the slowest excitation shown
SETTLE = 5  # time constants to settle (e^-5 < 1 %)
PTS_SINE = 50  # steps per period of a sine
PTS_PULSE = 100  # steps per period of a pulse/PWM
PTS_WIDTH = 20  # steps per pulse width
PTS_TAU = 10  # steps per time constant
OUTPUT_POINTS = 1000  # TSTEP = TSTOP/1000, as the editor does when TSTEP is blank
MAX_STEPS = 1_000_000  # above this the run is long (memory and time)
DEFAULT_TSTOP = 10e-3

_SOURCES_SINE = ("vsin", "isin")
_SOURCES_PULSE = ("vpulse", "ipulse")
_SOURCES_PWL = ("vpwl", "ipwl")
_RAMPS = {"vfd": ("accel",), "pump_plant": ("accel",), "soft_starter": ("tacc", "kick")}


@dataclass
class TranSuggestion:
    """Suggested ``.tran`` parameters in SPICE notation (the editor fields) and why."""

    params: dict[str, str]
    tstop: float
    tstep: float
    tmax: float | None
    steps: list[CalcStep] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def show_time(x: float) -> str:
    """Time for the notes, pt-BR: 16,7 ms, 159 µs, 1,5 s."""
    for scale, unit in ((1.0, "s"), (1e-3, "ms"), (1e-6, "µs"), (1e-9, "ns")):
        if abs(x) >= scale:
            return f"{x / scale:.3g} {unit}".replace(".", ",")
    return f"{x * 1e12:.3g} ps".replace(".", ",")


def _num(comp: Component, name: str) -> float | None:
    v = try_parse(param(comp, name))
    return v if v is not None and math.isfinite(v) else None


def nice_up(x: float) -> float:
    """Smallest 1-2-5 value ≥ x (10m, 20m, 50m, 100m...)."""
    e = math.floor(math.log10(x))
    for m in (1, 2, 5, 10):
        v = m * 10.0**e
        if v >= x * (1 - 1e-9):
            return v
    return 10.0 ** (e + 1)  # pragma: no cover - the loop always returns


def nice_down(x: float) -> float:
    """Largest 1-2-5 value ≤ x."""
    e = math.floor(math.log10(x))
    for m in (5, 2, 1):
        v = m * 10.0**e
        if v <= x * (1 + 1e-9):
            return v
    return 10.0 ** (e - 1) * 5  # pragma: no cover


@dataclass
class _Scale:
    """One time scale of the circuit: what it is and the limits it puts on TSTOP and TMAX."""

    label: str
    tstop: float | None
    tmax: float | None


def _periods(sch: Schematic, log: list[CalcStep]) -> list[_Scale]:
    out: list[_Scale] = []
    for c in sch.components:
        k = c.kind
        if k in _SOURCES_SINE or k == "v3ph":
            f = _num(c, "freq")
            if not f or f <= 0:
                continue
            delay = (_num(c, "delay") or 0.0) if k != "v3ph" else 0.0
            period = 1 / f
            log.append(
                record(
                    f"T_{c.ref}",
                    f"Período da fonte senoidal {c.ref}",
                    r"T = \frac{1}{f}",
                    q(period, "s"),
                    {"f": q(f, "Hz")},
                    [f"{CYCLES} períodos na simulação, {PTS_SINE} passos por período"],
                    NGSPICE_MANUAL,
                ).step
            )
            out.append(
                _Scale(
                    f"{c.ref}: T = {show_time(period)}",
                    delay + CYCLES * period,
                    period / PTS_SINE,
                )
            )
            damping = _num(c, "damping") if k != "v3ph" else None
            if damping and damping > 0:
                out.append(_Scale(f"{c.ref}: amortecimento", delay + SETTLE / damping, None))
        elif k in _SOURCES_PULSE:
            t_per, width = _num(c, "period"), _num(c, "width")
            delay = _num(c, "delay") or 0.0
            rise, fall = _num(c, "rise") or 0.0, _num(c, "fall") or 0.0
            if not t_per or t_per <= 0:
                continue
            on = width if width and width > 0 else t_per / 2
            tmax = min(t_per / PTS_PULSE, on / PTS_WIDTH)
            if t_per > 0 and (rise + fall + on) < t_per:
                duty = on / t_per
                log.append(
                    record(
                        f"T_{c.ref}",
                        f"Período e largura do pulso de {c.ref}",
                        rf"\Delta t_{{máx}} = \min\left(\frac{{T}}{{{PTS_PULSE}}}, "
                        rf"\frac{{t_{{on}}}}{{{PTS_WIDTH}}}\right)",
                        q(tmax, "s"),
                        {"T": q(t_per, "s"), "t_on": q(on, "s"), "D": q(duty, "")},
                        [
                            f"{CYCLES} períodos na simulação; as bordas do pulso são pontos de "
                            "parada do ngspice, então subida e descida não limitam o passo"
                        ],
                        NGSPICE_MANUAL,
                    ).step
                )
                out.append(_Scale(f"{c.ref}: T = {show_time(t_per)}", delay + CYCLES * t_per, tmax))
            else:  # a single step (width or period longer than the run)
                out.append(
                    _Scale(
                        f"{c.ref}: degrau em {show_time(delay)}",
                        2 * delay if delay > 0 else None,
                        None,
                    )
                )
        elif k in _SOURCES_PWL:
            nums = [try_parse(t) for t in param(c, "points").replace(",", " ").split()]
            times = [t for t in nums[0::2] if t is not None]
            if len(times) < 2:
                continue
            gaps = [b - a for a, b in itertools.pairwise(times) if b > a]
            end = max(times)
            step_max = min(gaps) / 5 if gaps else None
            out.append(_Scale(f"{c.ref}: último ponto em {show_time(end)}", 1.2 * end, step_max))
        elif k in _RAMPS:
            ramp = sum(_num(c, n) or 0.0 for n in _RAMPS[k])
            if ramp > 0:
                out.append(_Scale(f"{c.ref}: rampa de {show_time(ramp)}", 1.5 * ramp, None))
    return out


def _time_constants(
    sch: Schematic, pin_nodes: Mapping[str, Mapping[str, str]], log: list[CalcStep]
) -> list[_Scale]:
    """τ of each C and L with the resistors on its nodes, and the LC resonance periods."""
    by_node: dict[str, list[tuple[Component, float]]] = {}
    for c in sch.components:
        if c.kind == "resistor" and (r := _num(c, "value")) and r > 0:
            for node in pin_nodes.get(c.ref, {}).values():
                by_node.setdefault(node, []).append((c, r))
    out: list[_Scale] = []
    caps: list[tuple[Component, float, set[str]]] = []
    inds: list[tuple[Component, float, set[str]]] = []
    for c in sch.components:
        nodes = set(pin_nodes.get(c.ref, {}).values())
        if c.kind == "capacitor" and (cv := _num(c, "value")) and cv > 0:
            caps.append((c, cv, nodes))
        elif c.kind == "inductor" and (lv := _num(c, "value")) and lv > 0:
            inds.append((c, lv, nodes))
        elif c.kind == "rl_load":
            r, ind = _num(c, "r"), _num(c, "l")
            if r and ind and r > 0 and ind > 0:
                tau = ind / r
                log.append(
                    record(
                        f"tau_{c.ref}",
                        f"Constante de tempo da carga {c.ref}",
                        r"\tau = \frac{L}{R}",
                        q(tau, "s"),
                        {"L": q(ind, "H"), "R": q(r, "ohm")},
                        reference=HAYT_RC,
                    ).step
                )
                out.append(_Scale(f"{c.ref}: τ = {show_time(tau)}", SETTLE * tau, tau / PTS_TAU))

    def touching(nodes: set[str], me: str) -> list[tuple[Component, float]]:
        seen: dict[str, tuple[Component, float]] = {}
        for n in nodes - {"0"} or nodes:
            for comp, r in by_node.get(n, []):
                if comp.ref != me:
                    seen[comp.ref] = (comp, r)
        return list(seen.values())

    for c, cv, nodes in caps:
        rs = touching(nodes, c.ref)
        if not rs:
            continue
        req = 1 / sum(1 / r for _, r in rs)
        tau = req * cv
        names = ", ".join(comp.ref for comp, _ in rs)
        log.append(
            record(
                f"tau_{c.ref}",
                f"Constante de tempo de {c.ref} com {names}",
                r"\tau = C \cdot R_{eq},\quad R_{eq} = R_1 \parallel R_2 \parallel \ldots",
                q(tau, "s"),
                {"C": q(cv, "F"), "R_eq": q(req, "ohm")},
                [
                    "estimativa de 1ª ordem: só os resistores ligados aos nós do capacitor",
                    f"{SETTLE}τ para acomodar; passo de τ/{PTS_TAU}",
                ],
                HAYT_RC,
            ).step
        )
        out.append(_Scale(f"{c.ref}: τ = {show_time(tau)}", SETTLE * tau, tau / PTS_TAU))
    for c, lv, nodes in inds:
        rs = touching(nodes, c.ref)
        if rs:
            req = sum(r for _, r in rs)
            tau = lv / req
            names = ", ".join(comp.ref for comp, _ in rs)
            log.append(
                record(
                    f"tau_{c.ref}",
                    f"Constante de tempo de {c.ref} com {names}",
                    r"\tau = \frac{L}{R_{eq}},\quad R_{eq} = R_1 + R_2 + \ldots",
                    q(tau, "s"),
                    {"L": q(lv, "H"), "R_eq": q(req, "ohm")},
                    ["estimativa de 1ª ordem: resistores em série com o indutor"],
                    HAYT_RC,
                ).step
            )
            out.append(_Scale(f"{c.ref}: τ = {show_time(tau)}", SETTLE * tau, tau / PTS_TAU))
        for cc, cv, cnodes in caps:
            if not (nodes & cnodes) - {"0"}:
                continue
            period = 2 * math.pi * math.sqrt(lv * cv)
            log.append(
                record(
                    f"T_{c.ref}_{cc.ref}",
                    f"Período de ressonância de {c.ref} com {cc.ref}",
                    r"T_0 = 2\pi\sqrt{LC}",
                    q(period, "s"),
                    {"L": q(lv, "H"), "C": q(cv, "F")},
                    [f"{PTS_SINE} passos por período de ressonância"],
                    HAYT_RLC,
                ).step
            )
            out.append(
                _Scale(
                    f"{c.ref}–{cc.ref}: T₀ = {show_time(period)}",
                    CYCLES * period,
                    period / PTS_SINE,
                )
            )
    return out


def suggest_tran(
    sch: Schematic,
    pin_nodes: Mapping[str, Mapping[str, str]],
    drive_cap: float | None = None,
) -> TranSuggestion:
    """Suggested TSTOP, TSTEP, TSTART, TMAX and UIC for the circuit drawn.

    ``pin_nodes`` is the connectivity (ref → pin → node); ``drive_cap`` the largest step the
    drives and sensors accept (see ``drive_symbols.max_step``).
    """
    log: list[CalcStep] = []
    scales = _periods(sch, log) + _time_constants(sch, pin_nodes, log)
    notes: list[str] = []
    warnings: list[str] = []
    stops = [s for s in scales if s.tstop and s.tstop > 0]
    maxes = [s for s in scales if s.tmax and s.tmax > 0]
    if drive_cap is not None:
        maxes.append(_Scale("acionamentos e sensores do circuito", None, drive_cap))
    if stops:
        slow = max(stops, key=lambda s: s.tstop or 0.0)
        tstop = nice_up(slow.tstop or DEFAULT_TSTOP)
        notes.append(f"Tempo final pela escala mais lenta ({slow.label}).")
    else:
        tstop = DEFAULT_TSTOP
        notes.append(
            "O circuito não tem fontes variáveis nem constantes de tempo RC/RL reconhecidas: "
            "tempo final padrão de 10 ms; o passo fica com o padrão do ngspice."
        )
    tmax: float | None = None
    if maxes:
        fast = min(maxes, key=lambda s: s.tmax or math.inf)
        raw = fast.tmax or tstop
        tmax = nice_down(min(raw, tstop / 50))
        notes.append(f"Passo máximo pela escala mais rápida ({fast.label}).")
    implicit = tstop / OUTPUT_POINTS
    tstep = nice_down(min(implicit, tmax)) if tmax else nice_down(implicit)
    log.append(
        record(
            "tran_tstop",
            "Tempo final sugerido (valor 1-2-5 acima da maior escala)",
            rf"t_{{stop}} = \max({CYCLES}\,T, {SETTLE}\,\tau, \ldots)",
            q(tstop, "s"),
            assumptions=[s.label for s in stops] or ["sem escala reconhecida"],
            reference=NGSPICE_MANUAL,
        ).step
    )
    if tmax is not None:
        log.append(
            record(
                "tran_tmax",
                "Passo máximo sugerido (valor 1-2-5 abaixo da menor escala)",
                rf"\Delta t_{{máx}} = \min\left(\frac{{T}}{{{PTS_SINE}}}, "
                rf"\frac{{\tau}}{{{PTS_TAU}}}, "
                r"\frac{t_{stop}}{50}\right)",
                q(tmax, "s"),
                assumptions=[s.label for s in maxes],
                reference=NGSPICE_MANUAL,
            ).step
        )
    if tmax and tstop / tmax > MAX_STEPS:
        warnings.append(
            f"Simulação longa: cerca de {tstop / tmax:,.0f} passos. ".replace(",", ".")
            + "Se só interessa o regime permanente, grave a partir de um início maior "
            "(Início da gravação) ou reduza o tempo final."
        )
    uic = any(
        c.kind in ("capacitor", "inductor") and (c.params.get("ic") or "").strip()
        for c in sch.components
    )
    if uic:
        notes.append("Há tensão/corrente inicial em capacitor ou indutor: UIC = sim.")
    params = {
        "tstop": format_value(tstop, 3),
        "tstep": format_value(tstep, 3),
        "tstart": "0",
        "tmax": format_value(tmax, 3) if tmax else "",
        "uic": "sim" if uic else "não",
    }
    return TranSuggestion(params, tstop, tstep, tmax, log, notes, warnings)
