"""Report sections computed from a design result: waveform figures and operating limits.

Both the HTML and the PDF report use them, so the two documents say the same thing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from circuitos.core.units import Q_, QuantityModel, format_eng, parse_unit
from circuitos.design.base import DesignResult, MarginCheck

from . import figures

FigFormat = Literal["svg", "png"]


@dataclass
class SimWaves:
    """Simulated waveforms over one period (from the ngspice check) and the Bode magnitude."""

    t_s: list[float] = field(default_factory=list)
    traces: dict[str, tuple[str, list[float]]] = field(default_factory=dict)  # label → unit, y
    bode_f: list[float] = field(default_factory=list)
    bode: dict[str, list[float]] = field(default_factory=dict)


@dataclass
class Figure:
    title: str
    data: bytes
    fmt: FigFormat


_UNIT_TITLE = {"V": "Tensões", "A": "Correntes", "W": "Potências"}


def waveform_figures(
    result: DesignResult, sim: SimWaves | None = None, fmt: FigFormat = "svg"
) -> list[Figure]:
    """One figure per unit (tensões, correntes…), analytic and simulated traces together."""
    out: list[Figure] = []
    by_unit: dict[str, list[figures.Trace]] = {}
    if result.traces and result.trace_period is not None:
        period = result.trace_period.to_pint().m_as("s")
        for label, tr in result.traces.items():
            x = np.linspace(0.0, period, len(tr.values), endpoint=False)
            by_unit.setdefault(tr.unit, []).append(
                figures.Trace(
                    label=f"{label} (cálculo)", x=x, y=np.asarray(tr.values), unit=tr.unit
                )
            )
    if sim is not None and sim.t_s:
        t = np.asarray(sim.t_s)
        for label, (unit, values) in sim.traces.items():
            by_unit.setdefault(unit, []).append(
                figures.Trace(label=f"{label} (ngspice)", x=t, y=np.asarray(values), unit=unit)
            )
    if by_unit:
        for unit, traces in by_unit.items():
            title = _UNIT_TITLE.get(unit, f"Grandezas em {unit}")
            spec = figures.FigureSpec(
                kind="time",
                title=title,
                x_label="tempo (um período)",
                x_unit="s",
                width_in=7.0,
                height_in=3.0,
                dpi=160,
            )
            out.append(Figure(title, figures.render(traces, spec, fmt), fmt))
    if result.bode_f is not None and result.bode:
        f = np.asarray(result.bode_f.values)
        traces = [
            figures.Trace(label=f"{k} (cálculo)", x=f, y=np.asarray(v.values))
            for k, v in result.bode.items()
        ]
        if sim is not None and sim.bode_f:
            fs = np.asarray(sim.bode_f)
            traces += [
                figures.Trace(label=f"{k} (ngspice)", x=fs, y=np.asarray(v))
                for k, v in sim.bode.items()
            ]
        spec = figures.FigureSpec(
            kind="time",
            title="Resposta em frequência (módulo)",
            x_label="frequência",
            x_unit="Hz",
            log_x=True,
            log_y=True,
            width_in=7.0,
            height_in=3.0,
            dpi=160,
        )
        out.append(Figure("Resposta em frequência", figures.render(traces, spec, fmt), fmt))
    return out


# ------------------------------------------------------------------------- operating limits --

STATUS = {"ok": "ok", "atencao": "atenção", "violado": "violado"}


@dataclass
class LimitLine:
    designator: str
    text: str
    status: str


@dataclass
class Limits:
    verdict: str
    status: str  # worst status of the design
    lines: list[LimitLine]
    notes: list[str]


def _fmt(q: QuantityModel) -> str:
    if q.unit in ("degC", "°C"):
        return f"{q.value:.3g} °C".replace(".", ",")
    try:
        return format_eng(q.to_pint())
    except Exception:
        return f"{q.value:.3g} {q.unit}".replace(".", ",")


def _dec(v: float) -> str:
    return f"{v:.2f}".replace(".", ",")


def _is_current(q: QuantityModel) -> bool:
    try:
        return bool(Q_(1, parse_unit(q.unit)).dimensionality == Q_(1, "A").dimensionality)
    except Exception:
        return False


def operating_limits(result: DesignResult, policy: str) -> Limits:
    """Plain-language conclusions on how close each component is to its limits."""
    order = {"ok": 0, "atencao": 1, "violado": 2}
    lines: list[LimitLine] = []
    worst = "ok"
    by_des: dict[str, list[MarginCheck]] = {}
    for m in result.margins:
        by_des.setdefault(m.designator, []).append(m)
    for des, checks in by_des.items():
        g = min(checks, key=lambda m: m.margin_pct)
        worst = max(worst, g.status, key=lambda s: order[s])
        text = (
            f"limite mais próximo: {g.parameter}, esforço {_fmt(g.stress)} para "
            f"{_fmt(g.rating)} nominal (margem de {g.margin_pct:.0f} %, fator exigido "
            f"{_dec(g.required_factor)})"
        )
        currents = [m for m in checks if _is_current(m.stress) and m.stress.value > 0]
        if currents:
            factor = min(m.rating.value / (m.stress.value * m.required_factor) for m in currents)
            text += (
                f"; a corrente de carga pode variar até ≈ {_dec(factor)}× a de projeto antes de "
                "esgotar a margem de corrente (estimativa: esforços de corrente proporcionais "
                "à carga)"
            )
        lines.append(LimitLine(des, text, g.status))
    for t in result.thermal:
        worst = max(worst, t.status, key=lambda s: order[s])
        if t.Tj is not None and t.Tj_max is not None:
            head = t.Tj_max.value - t.Tj.value
            lines.append(
                LimitLine(
                    t.designator,
                    f"temperatura de junção {_fmt(t.Tj)} para {_fmt(t.Tj_max)} máxima "
                    f"({head:.0f} K de folga, {t.path})",
                    t.status,
                )
            )
    notes = [w.message for w in result.warnings]
    if any(not c.released for c in result.selection):
        notes.append("Há componente não revisado no projeto: confira o datasheet antes de montar.")
    if not result.converged:
        notes.append("O recálculo com os componentes reais não convergiu: veja os avisos.")
    verdict = {
        "ok": f"Todos os componentes operam dentro dos limites com as margens da política "
        f"“{policy}”.",
        "atencao": "O projeto funciona, mas há componentes com margem abaixo da exigida "
        "(marcados em atenção).",
        "violado": "O projeto NÃO atende: há esforço acima do valor nominal ou temperatura "
        "acima do limite.",
    }[worst]
    return Limits(verdict=verdict, status=worst, lines=lines, notes=notes)


__all__ = ["Figure", "LimitLine", "Limits", "SimWaves", "operating_limits", "waveform_figures"]
