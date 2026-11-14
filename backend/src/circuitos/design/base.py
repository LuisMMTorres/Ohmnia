"""Common types of design modules (docs/arquitetura.md, section 4; docs/modelo-de-dados.md, 3.1).

A design module (``DM-RET1``, ``DM-RETC1``...) turns a specification into:

1. ideal stresses on each component role (step 1);
2. a selection of real components from the catalogue, with derating margins (``selection/``);
3. a recomputation with the parameters of the selected parts, iterated until it converges
   (step 2), plus junction temperatures (``thermal/``);
4. a circuit for the simulator, used to check the analytic result.

Every number of the result comes from a :class:`CalcStep` of the calculation log.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Literal, Protocol
from uuid import UUID

import numpy as np
import pint
from numpy.typing import NDArray
from pydantic import BaseModel, Field

from circuitos.core.calc import CalcStep
from circuitos.core.units import QuantityModel

MarginStatus = Literal["ok", "atencao", "violado"]


class Stress(BaseModel):
    """A stress on one component role: the value the rating must withstand."""

    designator: str  # "D1-D4"
    key: str  # rating it is checked against: "VRRM", "IF(AV)", "IFSM", "Tj"...
    label: str  # "Tensão reversa de pico"
    value: QuantityModel
    calc_step_id: str


class Role(BaseModel):
    """A component position of the circuit that is filled from the catalogue."""

    designator: str
    category: str  # catalogue category prefix: "diode.rectifier", "thyristor.scr"...
    description: str
    count: int = 1


class StressReport(BaseModel):
    roles: list[Role]
    stresses: list[Stress]
    steps: list[CalcStep]


class MarginCheck(BaseModel):
    designator: str
    parameter: str
    stress: QuantityModel
    rating: QuantityModel
    required_factor: float
    margin_pct: float  # (rating / stress − 1)·100
    status: MarginStatus
    note: str | None = None


class ThermalResult(BaseModel):
    designator: str
    power: QuantityModel
    Tj: QuantityModel
    Tj_max: QuantityModel
    path: str  # "sem dissipador (Rθja)", "com dissipador"
    required_Rsa: QuantityModel | None = None  # heatsink needed to keep the Tj margin
    status: MarginStatus
    heatsink: str | None = None  # catalogue part chosen (one per device)
    heatsink_id: UUID | None = None
    heatsink_manufacturer: str | None = None
    heatsink_Rsa: QuantityModel | None = None  # effective, at the actual temperature rise


class Choice(BaseModel):
    """Component chosen for a role (automatic or locked by the user)."""

    designator: str
    component_id: UUID
    part_number: str
    manufacturer: str
    locked: bool
    released: bool  # False only for a component the user locked before review


class SimComparison(BaseModel):
    quantity: str
    analytic: QuantityModel
    simulated: QuantityModel
    error_pct: float
    tolerance_pct: float
    ok: bool


class DesignWarning(BaseModel):
    code: str
    message: str


class Trace(BaseModel):
    """One analytic waveform over one source period (uniform samples from θ = 0)."""

    unit: str
    values: list[float]


TRACE_POINTS = 720


def make_trace(unit: str, values: Sequence[float] | NDArray[np.float64]) -> Trace:
    arr = np.asarray(values, dtype=np.float64)
    step = max(arr.size // TRACE_POINTS, 1)
    return Trace(unit=unit, values=[float(v) for v in arr[::step]])


class DesignResult(BaseModel):
    module_id: str
    steps: list[CalcStep]
    stresses: list[Stress]
    roles: list[Role]
    selection: list[Choice]
    candidates: dict[str, list[str]] = Field(default_factory=dict)  # designator → part numbers
    margins: list[MarginCheck]
    thermal: list[ThermalResult]
    summary: dict[str, QuantityModel]  # headline results for the UI
    iterations: int
    converged: bool
    warnings: list[DesignWarning]
    sim_check: list[SimComparison] | None = None
    traces: dict[str, Trace] = Field(default_factory=dict)  # label = Circuit.probes label
    # Time span of the traces (one source/signal period); None: one period of spec.f.
    trace_period: QuantityModel | None = None
    # Frequency response: frequencies (Hz, log spaced) and |H| per label (Circuit.bode_probes).
    bode_f: Trace | None = None
    bode: dict[str, Trace] = Field(default_factory=dict)


Metric = Literal["avg", "rms", "pp", "max", "min", "pf", "thd", "ac_mag", "ac_fl", "ac_fh"]


class SimCheck(BaseModel):
    """One analytic result compared with the same quantity measured in the simulation.

    ``probe`` is a sum of vectors (``"v(p)-v(n)"``, ``"i(vsd1)"``); ``pf`` and ``thd`` use the
    current in ``probe`` and, for ``pf``, the voltage in ``voltage``. Both remove the mean of
    the current first (the primary of a transformer never carries DC).

    AC metrics use the ``.ac`` sweep (input source with ``AC 1``): ``ac_mag`` is |probe| at
    ``freq``; ``ac_fl`` and ``ac_fh`` are the frequencies where |probe| falls 3 dB below its
    maximum, below and above it.
    """

    quantity: str  # label shown to the user
    summary_key: str  # key of DesignResult.summary with the analytic value
    metric: Metric
    probe: str
    voltage: str | None = None
    freq: float | None = None  # Hz, for ac_mag
    tolerance_pct: float
    justification: str = ""  # why this tolerance (model approximation)


class Circuit(BaseModel):
    """Netlist for the simulator plus what to measure and how to compare."""

    title: str
    netlist: str  # without analysis cards
    tran_stop: QuantityModel | None = None  # None: no transient run
    tran_step: QuantityModel | None = None
    period: QuantityModel | None = None  # steady-state window length
    probes: dict[str, str] = Field(default_factory=dict)  # label → vector sum to plot
    checks: list[SimCheck] = Field(default_factory=list)
    ac_start: QuantityModel | None = None  # None: no .ac run
    ac_stop: QuantityModel | None = None
    ac_points_per_decade: int = 40
    bode_probes: dict[str, str] = Field(default_factory=dict)  # label → node/expression


class DesignModule(Protocol):
    id: str
    family: str
    title: str
    spec_schema: type[BaseModel]

    def design(self, spec: BaseModel, ctx: DesignContext) -> DesignResult: ...

    def build_circuit(self, spec: BaseModel, result: DesignResult) -> Circuit: ...


class DesignContext(Protocol):
    """What a module needs from the outside world (catalogue, policy, user locks)."""

    def candidates(self, category: str) -> list[object]: ...


QuantityMap = Mapping[str, pint.Quantity]
Factory = Callable[[], DesignModule]
