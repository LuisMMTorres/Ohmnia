"""Publication figures of simulation results (SVG, PNG, PDF) rendered with Matplotlib.

Axes use engineering prefixes and a decimal comma (pt-BR), traces keep the colours of the
editor's oscilloscope, and Bode figures stack magnitude and phase on a shared frequency axis.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from typing import Literal

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import ticker
from matplotlib.axes import Axes
from numpy.typing import NDArray

FigureFormat = Literal["svg", "png", "pdf"]
FigureKind = Literal["time", "xy", "bode", "spectrum"]

COLORS = ["#1f6feb", "#d1242f", "#1a7f37", "#9a6700", "#8250df", "#bf3989", "#0a7ea4", "#57606a"]
_PREFIX = {-15: "f", -12: "p", -9: "n", -6: "µ", -3: "m", 0: "", 3: "k", 6: "M", 9: "G", 12: "T"}
_UNIT = {"ohm": "Ω", "deg": "°", "degC": "°C"}


def eng_tick(value: float, unit: str = "") -> str:
    """Tick label in engineering notation with decimal comma: ``2,5 ms``."""
    unit = _UNIT.get(unit, unit)
    if value == 0 or not math.isfinite(value):
        return f"0 {unit}".strip() if value == 0 else ""
    exp = int(math.floor(math.log10(abs(value)) / 3) * 3)
    exp = max(min(exp, 12), -15)
    mant = value / 10**exp
    text = f"{mant:.4g}".replace(".", ",")
    return f"{text} {_PREFIX[exp]}{unit}".strip()


@dataclass
class Trace:
    label: str
    x: NDArray[np.float64]
    y: NDArray[np.float64]
    unit: str = ""


@dataclass
class FigureSpec:
    kind: FigureKind = "time"
    title: str = ""
    x_label: str = ""
    x_unit: str = ""
    y_label: str = ""
    log_x: bool = False
    log_y: bool = False
    width_in: float = 7.0
    height_in: float = 4.0
    dpi: int = 200


def _axis(ax: Axes, axis: Literal["x", "y"], unit: str, log: bool) -> None:
    target = ax.xaxis if axis == "x" else ax.yaxis
    if log:
        (ax.set_xscale if axis == "x" else ax.set_yscale)("log")
    target.set_major_formatter(ticker.FuncFormatter(lambda v, _pos: eng_tick(v, unit)))


def render(
    traces: list[Trace],
    spec: FigureSpec,
    fmt: FigureFormat = "svg",
    phase: list[Trace] | None = None,
) -> bytes:
    """Figure bytes; ``phase`` (Bode) goes to a second axis below the magnitude."""
    if not traces:
        raise ValueError("Nenhum traço para a figura")
    plt.rcParams.update({"font.size": 9, "axes.grid": True, "grid.alpha": 0.3})
    if spec.kind == "bode":
        fig, (ax, axp) = plt.subplots(
            2, 1, sharex=True, figsize=(spec.width_in, spec.height_in * 1.4)
        )
    else:
        fig, ax = plt.subplots(figsize=(spec.width_in, spec.height_in))
        axp = None
    units = list(dict.fromkeys(t.unit for t in traces))
    second = ax.twinx() if spec.kind == "time" and len(units) == 2 else None
    for k, tr in enumerate(traces):
        target = second if second is not None and tr.unit == units[1] else ax
        if spec.kind == "spectrum":
            target.vlines(tr.x, 0, tr.y, color=COLORS[k % len(COLORS)], label=tr.label, lw=1)
        else:
            target.plot(tr.x, tr.y, "-", color=COLORS[k % len(COLORS)], label=tr.label, lw=1.2)
    log_x = spec.log_x or spec.kind == "bode"
    _axis(ax, "x", spec.x_unit, log_x)
    _axis(ax, "y", units[0], spec.log_y)
    ax.set_ylabel(spec.y_label or ", ".join(_UNIT.get(u, u) for u in units[:1]))
    if second is not None:
        _axis(second, "y", units[1], spec.log_y)
        second.set_ylabel(_UNIT.get(units[1], units[1]))
        second.grid(False)
    if axp is not None:
        for k, tr in enumerate(phase or []):
            axp.plot(tr.x, tr.y, color=COLORS[k % len(COLORS)], label=tr.label, lw=1.2)
        _axis(axp, "x", spec.x_unit, True)
        _axis(axp, "y", "°", False)
        axp.set_ylabel("fase")
        axp.set_xlabel(spec.x_label)
        ax.set_ylabel(spec.y_label or "módulo")
    else:
        ax.set_xlabel(spec.x_label)
    if spec.title:
        ax.set_title(spec.title)
    handles, labels = ax.get_legend_handles_labels()
    if second is not None:
        h2, l2 = second.get_legend_handles_labels()
        handles, labels = handles + h2, labels + l2
    if len(handles) > 1 or spec.kind != "time":
        ax.legend(handles, labels, loc="best", fontsize=8)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format=fmt, dpi=spec.dpi)
    plt.close(fig)
    return buf.getvalue()
