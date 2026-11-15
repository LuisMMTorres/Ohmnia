"""Import of manufacturer SPICE models (``.lib``, ``.mod``, ``.cir``, ``.sp``).

The text is split into ``.model`` and ``.subckt`` definitions (continuation lines joined,
comments dropped). Each one is then *checked*: a minimal circuit that instantiates it runs in
ngspice, so a model that ngspice cannot read (PSpice-only syntax, missing nested models) is
flagged before it reaches a design. The original text is kept unchanged for the netlist.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from circuitos.components.models import SpiceModel
from circuitos.core.errors import CircuitosError
from circuitos.schematic.values import try_parse
from circuitos.simulation.backend import SimulatorBackend, make_backend

_DEVICE_TYPES = {
    "D": "D",
    "NPN": "NPN",
    "PNP": "PNP",
    "NMOS": "NMOS",
    "PMOS": "PMOS",
    "NJF": "NJF",
    "PJF": "PJF",
    "SW": "SW",
    "CSW": "CSW",
    "VDMOS": "VDMOS",
}


def _logical_lines(text: str) -> list[str]:
    """Join ``+`` continuations, drop ``*`` comment lines and ``;``/``$`` inline comments."""
    out: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.rstrip()
        stripped = line.lstrip()
        if not stripped or stripped.startswith("*"):
            continue
        line = re.split(r"\s;|\s\$", line, maxsplit=1)[0].rstrip()
        if stripped.startswith("+"):
            if out:
                out[-1] += " " + stripped[1:].strip()
            continue
        out.append(line.strip())
    return out


_PARAM = re.compile(r"([A-Za-z_][\w]*)\s*=\s*(\{[^}]*\}|[^\s,()]+)")


def _params(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for name, value in _PARAM.findall(text):
        number = try_parse(value)
        if number is not None:
            out[name.upper()] = number
    return out


def parse_models(text: str, source_note: str | None = None) -> list[SpiceModel]:
    """Every ``.model`` and ``.subckt`` in a model file, in order."""
    lines = _logical_lines(text)
    models: list[SpiceModel] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        low = line.lower()
        if low.startswith(".model"):
            m = re.match(r"\.model\s+(\S+)\s+([A-Za-z]+)\s*\(?(.*?)\)?\s*$", line, re.I)
            if m:
                name, kind, body = m.groups()
                models.append(
                    SpiceModel(
                        name=name,
                        kind="model",
                        device=_DEVICE_TYPES.get(kind.upper(), kind.upper()),
                        params=_params(body),
                        text=line,
                        origin="fabricante",
                        source_note=source_note,
                    )
                )
            i += 1
            continue
        if low.startswith(".subckt"):
            head = line.split()
            name = head[1] if len(head) > 1 else "?"
            pins = []
            for token in head[2:]:
                if "=" in token or token.lower() in ("params:", "param:"):
                    break
                pins.append(token)
            body = [line]
            i += 1
            depth = 1
            while i < len(lines) and depth:
                inner = lines[i].lower()
                if inner.startswith(".subckt"):
                    depth += 1
                elif inner.startswith(".ends"):
                    depth -= 1
                body.append(lines[i])
                i += 1
            if depth:
                raise CircuitosError(f"Subcircuito {name} sem .ends")
            models.append(
                SpiceModel(
                    name=name,
                    kind="subckt",
                    device="subckt",
                    pins=pins,
                    text="\n".join(body),
                    origin="fabricante",
                    source_note=source_note,
                )
            )
            continue
        i += 1
    return models


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    log: str


def check_netlist(model: SpiceModel, library: str = "") -> str:
    """Smallest circuit that makes ngspice load and evaluate the model."""
    lines = [f"check {model.name}"]
    if library:
        lines.append(library)
    else:
        lines.append(model.text)
    device = model.device.upper()
    if model.kind == "subckt":
        for n, _pin in enumerate(model.pins):
            lines.append(f"R{n} n{n} 0 1meg")
        lines.append("V1 n0 0 DC 1")
        lines.append(f"X1 {' '.join(f'n{n}' for n in range(len(model.pins)))} {model.name}")
    elif device == "D":
        lines += ["V1 a 0 DC 0.6", f"D1 a 0 {model.name}"]
    elif device in ("NPN", "PNP"):
        sign = "" if device == "NPN" else "-"
        lines += [f"VC c 0 DC {sign}5", f"VB b 0 DC {sign}0.7", f"Q1 c b 0 {model.name}"]
    elif device in ("NMOS", "PMOS", "VDMOS"):
        sign = "-" if device == "PMOS" else ""
        lines += [f"VD d 0 DC {sign}5", f"VG g 0 DC {sign}5", f"M1 d g 0 0 {model.name}"]
    elif device in ("NJF", "PJF"):
        sign = "" if device == "NJF" else "-"
        lines += [f"VD d 0 DC {sign}5", "VG g 0 DC 0", f"J1 d g 0 {model.name}"]
    else:
        raise CircuitosError(f"Tipo de modelo {model.device} sem circuito de verificação")
    lines += [".op", ".end"]
    return "\n".join(lines)


def check_model(
    model: SpiceModel, library: str = "", backend: SimulatorBackend | None = None
) -> CheckResult:
    """Run the model in ngspice. ``library`` is the whole file, for nested model references."""
    try:
        sim = backend or make_backend("batch", timeout_s=30)
        result = sim.run(check_netlist(model, library))
    except CircuitosError as exc:
        return CheckResult(ok=False, log=str(exc))
    return CheckResult(ok=True, log=result.log[-2000:])


__all__ = ["CheckResult", "check_model", "check_netlist", "parse_models"]
