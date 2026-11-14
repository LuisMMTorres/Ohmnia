"""DM-LIN: three-terminal linear regulators (78xx/79xx fixed, LM317/LM337 adjustable).

Design (Boylestad & Nashelsky, 11th ed., ch. 15 "Power supplies (voltage regulators)", IC
voltage regulators; onsemi LM317/D, Figure 1 "Standard application"):

* fixed: the part whose datasheet VO is nearest the desired output;
* adjustable: R1 carries at least the datasheet minimum load current at Vref,
  R2 = R1·(Vo − Vref)/(Vref + IAdj·R1) and Vo = Vref·(1 + R2/R1) + IAdj·R2 (LM317/D, p. 1);
* headroom: the lowest instantaneous input (lowest line, ripple valley) minus Vo must exceed
  the dropout of the datasheet (fixed) or the lower end of the specified VI − VO range
  (adjustable);
* dissipation PD = (VI − VO)·IO + VI·IQ at the highest input (the quiescent or adjustment
  current flows from the input to ground), with a heat sink from the catalogue if needed.

The simulator gets a behavioural regulator with the datasheet reference (out − adj or
out − gnd) that drops out at the same headroom, so the check confirms the divider, the
headroom with ripple and the input current; the internal loop of the IC is not modelled.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Literal

import pint
from pydantic import BaseModel, Field

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import BibRef, CalcLog, record
from circuitos.core.units import Q_, QuantityModel, format_eng
from circuitos.design.analog import commercial
from circuitos.design.base import (
    Circuit,
    DesignResult,
    DesignWarning,
    Role,
    SimCheck,
    Stress,
    make_trace,
)
from circuitos.design.devmodels import BOYLESTAD, quantity
from circuitos.design.engine import Analysis, Device
from circuitos.reports.common import BomRow, LabItem, passive, resistor_row
from circuitos.reports.schematic import Svg

Kind = Literal["fixo", "ajustavel"]
Polarity = Literal["positiva", "negativa", "simetrica"]

REF = BOYLESTAD.model_copy(update={"chapter": "15 (Power supplies: IC voltage regulators)"})
LM317_REF = BibRef(book="onsemi LM317/D", edition="Rev. 18", chapter="Figure 1, p. 1")


class LinSpec(BaseModel):
    kind: Kind = "fixo"
    polarity: Polarity = "positiva"
    Vo: QuantityModel = QuantityModel(value=5, unit="V")  # magnitude of each output
    Io: QuantityModel = QuantityModel(value=0.5, unit="A")  # maximum load current per output
    Vin: QuantityModel = QuantityModel(value=12, unit="V")  # mean unregulated input (magnitude)
    vin_tol_pct: float = Field(default=10.0, ge=0, le=40)
    ripple_pp: QuantityModel = QuantityModel(value=1.0, unit="V")  # at the regulator input
    f_ripple: QuantityModel = QuantityModel(value=120, unit="Hz")
    vo_window_pct: float = Field(default=3.0, gt=0, le=20)  # fixed parts accepted around Vo
    res_series: Literal["E24", "E96"] = "E96"
    TA: QuantityModel = QuantityModel(value=40, unit="degC")
    Rth_cs: QuantityModel = QuantityModel(value=0.5, unit="K/W")


LABELS = {
    "Vin_min": "Entrada mínima (média)",
    "Vin_max": "Entrada máxima (média)",
    "Vin_valley": "Vale da entrada (mínima − ondulação/2)",
    "Vin_peak": "Pico da entrada (máxima + ondulação/2)",
    "headroom": "Folga no vale (VI − VO)",
    "headroom_req": "Folga exigida pelo datasheet",
    "Vo": "Tensão de saída",
    "Vo_min": "Saída mínima (tolerância de Vref/VO)",
    "Vo_max": "Saída máxima (tolerância de Vref/VO)",
    "R1": "R1 (saída–ajuste)",
    "R2": "R2 (ajuste–terra)",
    "I_R1": "Corrente em R1",
    "PD": "Potência no regulador (pior caso)",
    "Iin": "Corrente média de entrada",
    "eff": "Rendimento (entrada máxima)",
}
SPEC_LABELS = {
    "kind": "Regulador",
    "polarity": "Polaridade",
    "Vo": "Tensão de saída (módulo)",
    "Io": "Corrente máxima por saída",
    "Vin": "Entrada não regulada (média, módulo)",
    "vin_tol_pct": "Variação da rede (± %)",
    "ripple_pp": "Ondulação de pico a pico na entrada",
    "f_ripple": "Frequência da ondulação",
    "vo_window_pct": "Janela de VO aceita (± %)",
    "res_series": "Série de resistores",
}
ENUM_LABELS = {
    "fixo": "fixo (78xx/79xx)",
    "ajustavel": "ajustável (LM317/LM337)",
    "positiva": "positiva",
    "negativa": "negativa",
    "simetrica": "simétrica (±)",
    "E96": "E96",
}


def caps(kind: Kind, negative: bool) -> tuple[str, str, str]:
    """(Cin, Co, source) of the datasheet standard application."""
    if kind == "ajustavel":
        return "0,1 µF", "1 µF", "LM317/D e LM337/D, Figure 1 (aplicação padrão)"
    if negative:
        return "0,33 µF", "1 µF", "MC7900/D, aplicação padrão, p. 1"
    return "0,33 µF", "0,1 µF", "MC7800/D, aplicação padrão, p. 1 (Co opcional, ≥ 0,1 µF)"


def _spec(spec: BaseModel) -> LinSpec:
    if not isinstance(spec, LinSpec):
        raise TypeError("DM-LIN espera LinSpec")
    return spec


def _num(rec: ComponentRecord, key: str, unit: str, prefer: tuple[str, ...]) -> float | None:
    v = quantity(rec, key, prefer)
    return None if v is None else float(v.m_as(unit))


class LinModule:
    id = "DM-LIN"
    family = "fontes"
    title = "Regulador linear integrado"
    spec_schema = LinSpec
    labels = LABELS
    spec_labels = SPEC_LABELS
    enum_labels = ENUM_LABELS
    lab = [
        LabItem("Tensão de saída com carga máxima", "multímetro CC", "Vo"),
        LabItem("Vale da tensão de entrada", "osciloscópio, acoplamento CC", "Vin_valley"),
        LabItem("Corrente de entrada", "multímetro em série", "Iin"),
        LabItem("Temperatura da cápsula", "termopar no dissipador", "PD"),
    ]
    questions = [
        "Por que a folga entrada-saída deve ser verificada no vale da ondulação, e não na "
        "média da entrada?",
        "De onde vem a parcela VI·IQ da potência do regulador? Em que condição ela pesa?",
        "No LM317, por que R1 é escolhido pela corrente mínima de carga e não pela "
        "tensão de saída?",
    ]
    practice = {
        "objective": "Montar o regulador, verificar a tensão de saída, a folga no vale da "
        "ondulação e a temperatura do regulador com a carga máxima.",
        "material": "Fonte retificada e filtrada (ou fonte CC com ondulação), carga resistiva "
        "de potência, osciloscópio, multímetros, termopar, componentes da lista de materiais.",
        "procedure": [
            "Fixe o regulador no dissipador com pasta térmica antes de energizar.",
            "Ligue sem carga e confira a saída.",
            "Ligue a carga máxima; meça a saída, a entrada (média e vale) e a corrente.",
            "Reduza a entrada até a saída começar a ondular: anote a folga em que isso ocorre.",
            "Após 15 min com carga máxima, meça a temperatura do dissipador.",
        ],
    }

    def _outputs(self, s: LinSpec) -> list[tuple[str, str]]:
        pos = ("U1", "regulator.positive")
        neg = ("U2" if s.polarity == "simetrica" else "U1", "regulator.negative")
        return {"positiva": [pos], "negativa": [neg], "simetrica": [pos, neg]}[s.polarity]

    def roles(self, spec: BaseModel) -> list[Role]:
        s = _spec(spec)
        return [
            Role(
                designator=d,
                category=c,
                description=f"Regulador {'fixo' if s.kind == 'fixo' else 'ajustável'} "
                f"{'positivo' if c.endswith('positive') else 'negativo'}",
            )
            for d, c in self._outputs(s)
        ]

    def required_ratings(self, role: Role) -> list[str]:
        return ["IO_max"]

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).Rth_cs.to_pint()

    def accepts(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> bool:
        s = _spec(spec)
        if s.kind == "ajustavel":
            return "Vref" in rec.parameters and "VO" not in rec.parameters
        vo = _num(rec, "VO", "V", ("typ",))
        target = s.Vo.to_pint().m_as("V")
        return vo is not None and abs(vo - target) <= s.vo_window_pct / 100 * target

    def preference(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> float:
        s = _spec(spec)
        if s.kind == "ajustavel":
            return 0.0
        return abs((_num(rec, "VO", "V", ("typ",)) or 0.0) - s.Vo.to_pint().m_as("V"))

    # ------------------------------------------------------------------ analysis
    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        log = CalcLog()
        warnings: list[DesignWarning] = []
        vin = s.Vin.to_pint().m_as("V")
        tol = s.vin_tol_pct / 100
        rip = s.ripple_pp.to_pint().m_as("V")
        io = s.Io.to_pint().m_as("A")
        vo_t = s.Vo.to_pint().m_as("V")
        if io <= 0 or vo_t <= 0:
            raise ValueError("Vo e Io devem ser positivos")
        vin_min, vin_max = vin * (1 - tol), vin * (1 + tol)
        valley = log.add(
            record(
                "Vin_valley",
                "Menor tensão instantânea na entrada do regulador",
                r"V_{I,vale} = V_{in}(1 - \delta) - \frac{\Delta V_{pp}}{2}",
                output=Q_(vin_min - rip / 2, "V"),
                inputs={
                    "V_{in}": s.Vin.to_pint(),
                    r"\delta": Q_(s.vin_tol_pct, "percent"),
                    r"\Delta V_{pp}": s.ripple_pp.to_pint(),
                },
                assumptions=["ondulação simétrica em torno da média"],
                reference=REF,
            )
        ).m_as("V")
        peak = log.add(
            record(
                "Vin_peak",
                "Maior tensão instantânea na entrada",
                r"V_{I,pico} = V_{in}(1 + \delta) + \frac{\Delta V_{pp}}{2}",
                output=Q_(vin_max + rip / 2, "V"),
                inputs={
                    "V_{in}": s.Vin.to_pint(),
                    r"\delta": Q_(s.vin_tol_pct, "percent"),
                    r"\Delta V_{pp}": s.ripple_pp.to_pint(),
                },
                reference=REF,
            )
        ).m_as("V")
        summary: dict[str, pint.Quantity] = {
            "Vin_min": Q_(vin_min, "V"),
            "Vin_max": Q_(vin_max, "V"),
            "Vin_valley": Q_(valley, "V"),
            "Vin_peak": Q_(peak, "V"),
        }
        stresses: list[Stress] = []
        losses: dict[str, pint.Quantity] = {}
        first = True
        for designator, _cat in self._outputs(s):
            rec = devices[designator].record
            sfx = "" if first else f"_{designator}"
            first = False
            if s.kind == "fixo":
                if rec is not None:
                    vo = _num(rec, "VO", "V", ("typ",)) or vo_t
                    vo_lo = _num(rec, "VO", "V", ("min",)) or vo
                    vo_hi = _num(rec, "VO", "V", ("max",)) or vo
                    iq = _num(rec, "IQ", "A", ("max", "typ")) or 0.0
                    need = _num(rec, "Vdo", "V", ("typ", "max")) or 0.0
                    vi_reg = _num(rec, "VI_reg_min", "V", ("min",))
                    log.add(
                        record(
                            f"Vo{sfx}",
                            f"Tensão de saída de {designator} ({rec.part_number}, datasheet)",
                            r"V_O = V_{O,typ}",
                            output=Q_(vo, "V"),
                            inputs={"V_{O,min}": Q_(vo_lo, "V"), "V_{O,max}": Q_(vo_hi, "V")},
                            assumptions=["TJ = 25 °C, condições de ensaio do datasheet"],
                            reference=REF,
                        )
                    )
                    if vi_reg is not None and vin_min < vi_reg:
                        warnings.append(
                            DesignWarning(
                                code="fora_da_faixa",
                                message=f"{designator}: a entrada mínima ({vin_min:.3g} V) "
                                f"fica abaixo da faixa em que o datasheet garante VO "
                                f"({vi_reg:g} V).",
                            )
                        )
                else:
                    vo, vo_lo, vo_hi, iq, need = vo_t, vo_t, vo_t, 0.0, 0.0
                req_txt = "queda (dropout) típica do datasheet a 1 A"
                summary[f"Vo{sfx}"] = Q_(vo, "V")
            else:
                if rec is not None:
                    vref = _num(rec, "Vref", "V", ("typ",)) or 1.25
                    vref_lo = _num(rec, "Vref", "V", ("min",)) or vref
                    vref_hi = _num(rec, "Vref", "V", ("max",)) or vref
                    iadj = _num(rec, "IAdj", "A", ("typ", "max")) or 0.0
                    iadj_max = _num(rec, "IAdj", "A", ("max", "typ")) or 0.0
                    ilmin = _num(rec, "IL_min", "A", ("max", "typ")) or 0.0
                    need = _num(rec, "VIO_min", "V", ("min",)) or 0.0
                else:
                    vref = vref_lo = vref_hi = 1.25
                    iadj = iadj_max = 0.0
                    ilmin = 5e-3
                    need = 0.0
                    warnings.append(
                        DesignWarning(
                            code="ideal",
                            message="Passo ideal: Vref = 1,25 V e 5 mA em R1 até escolher o CI.",
                        )
                    )
                r1_calc = log.add(
                    record(
                        f"R1_calc{sfx}",
                        f"R1 de {designator}: corrente em R1 ≥ corrente mínima de carga",
                        r"R_1 \le \frac{V_{ref,min}}{I_{L,min}}",
                        output=Q_(vref_lo / ilmin, "ohm"),
                        inputs={
                            "V_{ref,min}": Q_(vref_lo, "V"),
                            "I_{L,min}": Q_(ilmin, "A").to("mA"),
                        },
                        assumptions=[
                            "a corrente de R1 mantém o CI regulando mesmo sem carga externa"
                        ],
                        reference=LM317_REF,
                    )
                )
                r1 = commercial(
                    log, f"R1{sfx}", f"R1 de {designator}", r1_calc, s.res_series, "down"
                ).m_as("ohm")
                r2_calc = log.add(
                    record(
                        f"R2_calc{sfx}",
                        f"R2 de {designator} para a saída desejada",
                        r"R_2 = \frac{R_1 (V_o - V_{ref})}{V_{ref} + I_{Adj} R_1}",
                        output=Q_(r1 * (vo_t - vref) / (vref + iadj * r1), "ohm"),
                        inputs={
                            "R_1": Q_(r1, "ohm"),
                            "V_o": s.Vo.to_pint(),
                            "V_{ref}": Q_(vref, "V"),
                            "I_{Adj}": Q_(iadj, "A").to("uA"),
                        },
                        reference=LM317_REF,
                    )
                )
                if r2_calc.magnitude <= 0:
                    raise ValueError("A saída desejada é menor que Vref")
                r2 = commercial(
                    log, f"R2{sfx}", f"R2 de {designator}", r2_calc, s.res_series, "nearest"
                ).m_as("ohm")
                vo = log.add(
                    record(
                        f"Vo{sfx}",
                        f"Tensão de saída de {designator} com os resistores comerciais",
                        r"V_o = V_{ref}\left(1 + \frac{R_2}{R_1}\right) + I_{Adj} R_2",
                        output=Q_(vref * (1 + r2 / r1) + iadj * r2, "V"),
                        inputs={
                            "V_{ref}": Q_(vref, "V"),
                            "R_1": Q_(r1, "ohm"),
                            "R_2": Q_(r2, "ohm"),
                            "I_{Adj}": Q_(iadj, "A").to("uA"),
                        },
                        reference=LM317_REF,
                    )
                ).m_as("V")
                vo_lo = vref_lo * (1 + r2 / r1)
                vo_hi = vref_hi * (1 + r2 / r1) + iadj_max * r2
                summary |= {
                    f"R1{sfx}": Q_(r1, "ohm"),
                    f"R2{sfx}": Q_(r2, "ohm"),
                    f"I_R1{sfx}": Q_(vref / r1, "A").to("mA"),
                    f"Vo{sfx}": Q_(vo, "V"),
                }
                iq = iadj  # the R1/R2 current reaches the output node: counted in the load
                req_txt = "início da faixa |VI − VO| em que Vref é especificada"
            summary[f"Vo_min{sfx}"] = Q_(vo_lo, "V")
            summary[f"Vo_max{sfx}"] = Q_(vo_hi, "V")
            i_div = summary[f"I_R1{sfx}"].m_as("A") if f"I_R1{sfx}" in summary else 0.0
            head = valley - vo
            log.add(
                record(
                    f"headroom{sfx}",
                    f"Folga de {designator} no vale da entrada",
                    r"V_{I,vale} - V_O \ge V_{folga}",
                    output=Q_(head, "V"),
                    inputs={
                        "V_{I,vale}": Q_(valley, "V"),
                        "V_O": Q_(vo, "V"),
                        "V_{folga}": Q_(need, "V"),
                    },
                    assumptions=[req_txt],
                    reference=REF,
                )
            )
            summary[f"headroom{sfx}"] = Q_(head, "V")
            summary[f"headroom_req{sfx}"] = Q_(need, "V")
            if head < need:
                warnings.append(
                    DesignWarning(
                        code="folga",
                        message=f"{designator}: a folga no vale ({head:.3g} V) é menor que a "
                        f"exigida ({need:.3g} V): a saída vai ondular. Aumente a entrada ou o "
                        "capacitor de filtro.",
                    )
                )
            i_out = io + i_div
            pd = log.add(
                record(
                    f"PD{sfx}",
                    f"Potência dissipada em {designator} (entrada máxima, carga máxima)",
                    r"P_D = (V_{I,max} - V_O)\,I_O + V_{I,max}\,I_Q",
                    output=Q_((vin_max - vo) * i_out + vin_max * iq, "W"),
                    inputs={
                        "V_{I,max}": Q_(vin_max, "V"),
                        "V_O": Q_(vo, "V"),
                        "I_O": Q_(i_out, "A"),
                        "I_Q": Q_(iq, "A").to("mA"),
                    },
                    assumptions=[
                        "média da entrada (a ondulação não altera a média de (VI − VO)·IO)",
                        "I_O inclui a corrente do divisor R1–R2"
                        if s.kind == "ajustavel"
                        else "I_Q: corrente quiescente máxima do datasheet",
                    ],
                    reference=REF,
                )
            )
            iin = i_out + iq
            summary |= {
                f"PD{sfx}": pd,
                f"Iin{sfx}": Q_(iin, "A"),
                f"eff{sfx}": Q_(vo * io / (vin_max * iin) * 100, "percent"),
            }
            stresses += [
                Stress(
                    designator=designator,
                    key="IO_max",
                    label="Corrente de saída",
                    value=QuantityModel(value=i_out, unit="A"),
                    calc_step_id=f"PD{sfx}",
                ),
                Stress(
                    designator=designator,
                    key="VI_max" if s.kind == "fixo" else "VIO_max",
                    label="Tensão de entrada" if s.kind == "fixo" else "Diferença entrada-saída",
                    value=QuantityModel(value=peak if s.kind == "fixo" else peak - vo, unit="V"),
                    calc_step_id="Vin_peak",
                ),
            ]
            losses[designator] = pd.to("W")
        period = 1 / s.f_ripple.to_pint().m_as("Hz")
        th = [2 * math.pi * k / 720 for k in range(720)]
        vin_wave = [vin_min + rip / 2 * math.sin(t) for t in th]
        vo1 = summary["Vo"].m_as("V")
        need1 = summary["headroom_req"].m_as("V")
        traces = {
            "Entrada do regulador (entrada mínima)": make_trace("V", vin_wave),
            "Saída": make_trace("V", [min(vo1, v - need1) for v in vin_wave]),
        }
        return Analysis(
            log=log,
            stresses=stresses,
            summary=summary,
            losses=losses,
            warnings=warnings,
            convergence_keys=("Vo", "PD"),
            traces=traces,
            trace_period=Q_(period, "s"),
        )

    # ------------------------------------------------------------------ circuit
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        """Behavioural regulators at the lowest line (ripple valley), loaded with Io.

        Fixed: ``out = min(VO, VI − folga)``. Adjustable: a source Vref between output and
        adjust (limited the same way) and the adjust current into R2. The positive output
        is used for the checks; a negative output is the mirror image.
        """
        s = _spec(spec)
        f = s.f_ripple.to_pint().m_as("Hz")
        vin_min = summary["Vin_min"].to_pint().m_as("V")
        rip = s.ripple_pp.to_pint().m_as("V")
        io = s.Io.to_pint().m_as("A")
        need = summary["headroom_req"].to_pint().m_as("V")
        lines = [f"VIN in 0 SIN({vin_min:.9g} {rip / 2:.9g} {f:.9g})", "VSI in i 0"]
        rec = devices[self._outputs(s)[0][0]].record
        if s.kind == "fixo":
            vo = summary["Vo"].to_pint().m_as("V")
            iq = (_num(rec, "IQ", "A", ("max", "typ")) or 0.0) if rec else 0.0
            lines += [
                f"BREG out 0 V = min({vo:.9g}, v(i) - {need:.9g})",
                f"IQ i 0 DC {iq:.9g}",
                "BIO i 0 I = i(vso)",
                "VSO out o 0",
            ]
        else:
            r1 = summary["R1"].to_pint().m_as("ohm")
            r2 = summary["R2"].to_pint().m_as("ohm")
            vref = (_num(rec, "Vref", "V", ("typ",)) or 1.25) if rec else 1.25
            iadj = (_num(rec, "IAdj", "A", ("typ", "max")) or 0.0) if rec else 0.0
            lines += [
                f"BREG out 0 V = min(v(adj) + {vref:.9g}, v(i) - {need:.9g})",
                f"IADJ i adj DC {iadj:.9g}",
                "BIO i 0 I = i(vso)",
                "VSO out o 0",
                f"R1 o adj {r1:.9g}",
                f"R2 adj 0 {r2:.9g}",
            ]
        lines.append(f"IL o 0 DC {io:.9g}")
        checks = [
            SimCheck(
                quantity="Tensão de saída (média)",
                summary_key="Vo",
                metric="avg",
                probe="v(o)",
                tolerance_pct=0.5,
                justification="mesmo modelo comportamental",
            ),
            SimCheck(
                quantity="Corrente média de entrada",
                summary_key="Iin",
                metric="avg",
                probe="i(vsi)",
                tolerance_pct=0.5,
                justification="mesmo modelo comportamental",
            ),
        ]
        return Circuit(
            title=f"{self.id}: regulador {ENUM_LABELS[s.kind]}, entrada mínima com ondulação",
            netlist="\n".join(lines),
            tran_stop=QuantityModel(value=3 / f, unit="s"),
            tran_step=QuantityModel(value=1 / f / 2000, unit="s"),
            period=QuantityModel(value=1 / f, unit="s"),
            probes={"Entrada do regulador (entrada mínima)": "v(in)", "Saída": "v(o)"},
            checks=checks,
        )

    # ------------------------------------------------------------------ outputs
    def schematic(self, spec: BaseModel, result: DesignResult, title: str) -> str:
        s = _spec(spec)
        parts = {c.designator: c.part_number for c in result.selection}
        sm = result.summary
        rows = self._outputs(s)
        svg = Svg(560, 140 + 150 * len(rows))
        svg.title(title)
        for i, (designator, cat) in enumerate(rows):
            neg = cat.endswith("negative")
            sfx = "" if i == 0 else f"_{designator}"
            y = 70 + 150 * i
            sign = "−" if neg else "+"
            svg.terminal(30, y, f"{sign}VI", "start")
            svg.wire((34, y), (190, y))
            cin, co, _src = caps(s.kind, neg)
            svg.cap_v(110, y, y + 90, "Cin", cin)
            svg.box(190, y - 22, 90, 44, designator, parts.get(designator, ""))
            svg.wire((280, y), (470, y))
            gx = 235
            if s.kind == "ajustavel":
                r1 = format_eng(sm[f"R1{sfx}"].to_pint())
                r2 = format_eng(sm[f"R2{sfx}"].to_pint())
                svg.resistor_v(330, y, y + 50, "R1", r1)
                svg.wire((gx, y + 22), (gx, y + 50), (330, y + 50))
                svg.resistor_v(330, y + 50, y + 90, "R2", r2)
                svg.text(gx + 4, y + 36, "ADJ")
            else:
                svg.line(gx, y + 22, gx, y + 90)
                svg.text(gx + 4, y + 36, "GND")
            svg.cap_v(400, y, y + 90, "Co", co)
            svg.terminal(474, y, f"{sign}{format_eng(sm[f'Vo{sfx}'].to_pint())}", "start")
            svg.wire((110, y + 90), (420, y + 90))
            svg.ground(110, y + 90)
        return svg.render(title)

    def bom_extra(self, spec: BaseModel, result: DesignResult) -> list[BomRow]:
        s = _spec(spec)
        rows: list[BomRow] = []
        for i, (designator, cat) in enumerate(self._outputs(s)):
            sfx = "" if i == 0 else f"_{designator}"
            n = i + 1
            if s.kind == "ajustavel":
                rows += [
                    r
                    for r in (
                        resistor_row(result, f"R{2 * n - 1}", f"R1{sfx}"),
                        resistor_row(result, f"R{2 * n}", f"R2{sfx}"),
                    )
                    if r
                ]
            cin, co, src = caps(s.kind, cat.endswith("negative"))
            rows += [
                passive(f"C{2 * n - 1}", "Capacitor de entrada junto ao regulador", cin, src),
                passive(f"C{2 * n}", "Capacitor de saída", co, src),
            ]
        return rows
