"""DM-INST: measurement and signal-conditioning circuits.

Ideal relations (Pertence, *Amplificadores operacionais e filtros ativos*, chapters on
instrumentation; Sedra & Smith, *Microelectronic Circuits*, 7th ed., ch. 2 "Operational
amplifiers" for the difference and instrumentation amplifiers):

* electronic voltmeter: divider R_b/(R_a + R_b) = V_fs/V_max and a follower (or a non-inverting
  gain when V_max < V_fs), input resistance R_a + R_b;
* ammeter: shunt R_sh = V_sh/I_max (low side) and a non-inverting gain V_fs/V_sh;
* power: voltage and current channels, P = (V_o,v/G_v)·(V_o,i/G_i);
* 4–20 mA transmitter (three wires, load in the feedback loop of a V-I converter): i = v+/R_s,
  v+ = a·v_in + b·V_ref from a passive summing network; compliance R_L ≤ V_sat/I_max − R_s;
* 4–20 mA receiver: 250 Ω and a difference amplifier with offset, v_o = G(i·R_rx − V_ref);
* Wheatstone quarter bridge: v_b = V_exc·x/(2(2 + x)) for R = R0(1 + x), against the linear
  V_exc·x/4; three-op-amp instrumentation amplifier, G = 1 + 2R/R_G;
* linear sensor conditioning: v_o = G(v_s − V_s,min), G = V_fs/(V_s,max − V_s,min).

The analysis solves the real circuit by nodal analysis with the macromodel of the chosen
op-amps including VOS and the bias currents (typical values), at both ends of the input range;
the simulator receives the same elements with the input as a ramp, so the extremes agree to
rounding.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Literal

import pint
from pydantic import BaseModel, Field

from circuitos.components.models import ComponentRecord
from circuitos.core.calc import BibRef, CalcLog, record
from circuitos.core.units import Q_, QuantityModel, format_eng
from circuitos.design.analog import commercial
from circuitos.design.base import Circuit, DesignResult, DesignWarning, Role, SimCheck
from circuitos.design.engine import Analysis, Device
from circuitos.design.mna import Circuit as Mna
from circuitos.design.opamp import REF as OPA_REF
from circuitos.design.opamp import OpAmp, opamp_model
from circuitos.reports.common import BomRow, LabItem, passive
from circuitos.reports.schematic import value_sheet

Config = Literal[
    "voltimetro",
    "amperimetro",
    "potencia",
    "transmissor_4_20",
    "receptor_4_20",
    "ponte_wheatstone",
    "condicionamento",
]
PERT = BibRef(book="Pertence, Amplificadores operacionais e filtros ativos", edition="8ª")
REF = OPA_REF
T_RAMP = 0.1  # s, input ramp of the simulation (no reactive elements: quasi-static)
N_OPAMPS = {
    "voltimetro": 1,
    "amperimetro": 1,
    "potencia": 2,
    "transmissor_4_20": 1,
    "receptor_4_20": 1,
    "ponte_wheatstone": 3,
    "condicionamento": 1,
}


class InstSpec(BaseModel):
    config: Config = "voltimetro"
    V_fs: QuantityModel = QuantityModel(value=5, unit="V")  # full-scale output (ADC)
    V_max: QuantityModel = QuantityModel(value=50, unit="V")  # voltmeter range
    R_in: QuantityModel = QuantityModel(value=1, unit="Mohm")  # voltmeter input resistance
    I_max: QuantityModel = QuantityModel(value=5, unit="A")  # ammeter range
    V_sh: QuantityModel = QuantityModel(value=50, unit="mV")  # shunt drop at I_max
    Vs_min: QuantityModel = QuantityModel(value=0, unit="V")  # sensor / transmitter input
    Vs_max: QuantityModel = QuantityModel(value=5, unit="V")
    V_ref: QuantityModel = QuantityModel(value=2.5, unit="V")  # transmitter reference
    R_sense: QuantityModel = QuantityModel(value=100, unit="ohm")  # transmitter sense
    R_loop: QuantityModel = QuantityModel(value=250, unit="ohm")  # receiver / loop load
    V_exc: QuantityModel = QuantityModel(value=5, unit="V")  # bridge excitation
    R0: QuantityModel = QuantityModel(value=350, unit="ohm")  # bridge arms
    x_max: float = Field(default=0.01, gt=0, le=0.5)  # sensor ΔR/R0 at full scale
    R_base: QuantityModel = QuantityModel(value=10, unit="kohm")
    VCC: QuantityModel = QuantityModel(value=15, unit="V")
    res_series: Literal["E24", "E96"] = "E96"
    TA: QuantityModel = QuantityModel(value=25, unit="degC")


LABELS = {
    "Vo_fs": "Saída no fundo de escala",
    "Vo_zero": "Saída no início da escala",
    "err_fs": "Erro no fundo de escala",
    "G": "Ganho do condicionador",
    "Rin": "Resistência de entrada",
    "R_sh": "Resistor shunt",
    "P_sh": "Potência no shunt (fundo de escala)",
    "Vo_v_fs": "Canal de tensão no fundo de escala",
    "Vo_i_fs": "Canal de corrente no fundo de escala",
    "P_fs": "Potência no fundo de escala (calculada dos canais)",
    "I_lo": "Corrente na entrada mínima",
    "I_hi": "Corrente na entrada máxima",
    "RL_max": "Carga máxima da malha (compliance)",
    "V_comp": "Tensão de compliance do ampop",
    "Vb_fs": "Saída da ponte no fundo de escala",
    "Vb_lin": "Saída da ponte (aproximação linear)",
    "nl_err": "Não linearidade da ponte",
    "V_ref_set": "Tensão de referência",
}
SPEC_LABELS = {
    "config": "Circuito",
    "V_fs": "Saída no fundo de escala (ADC)",
    "V_max": "Fundo de escala do voltímetro",
    "R_in": "Resistência de entrada do voltímetro",
    "I_max": "Fundo de escala do amperímetro",
    "V_sh": "Queda no shunt no fundo de escala",
    "Vs_min": "Entrada mínima (sensor/transmissor)",
    "Vs_max": "Entrada máxima (sensor/transmissor)",
    "V_ref": "Referência do transmissor",
    "R_sense": "Resistor sensor de corrente (transmissor)",
    "R_loop": "Carga da malha / resistor do receptor",
    "V_exc": "Excitação da ponte",
    "R0": "Resistência nominal da ponte",
    "x_max": "Variação relativa do sensor no fundo de escala (ΔR/R0)",
    "R_base": "Resistor de base",
    "VCC": "Alimentação (±)",
    "res_series": "Série de resistores",
}
ENUM_LABELS = {
    "voltimetro": "voltímetro eletrônico",
    "amperimetro": "amperímetro com shunt",
    "potencia": "medidor de potência CC (canais V e I)",
    "transmissor_4_20": "transmissor 4–20 mA (3 fios)",
    "receptor_4_20": "receptor 4–20 mA",
    "ponte_wheatstone": "ponte de Wheatstone + amplificador de instrumentação",
    "condicionamento": "condicionamento de sensor linear",
    "E24": "E24",
    "E96": "E96",
}


def _spec(spec: BaseModel) -> InstSpec:
    if not isinstance(spec, InstSpec):
        raise TypeError("DM-INST espera InstSpec")
    return spec


Build = Callable[[float], Mna]


def evaluate(c: Mna, probe: str) -> float:
    """Value of ``v(a)``, ``v(a)-v(b)`` or ``i(vname)`` at the DC operating point."""
    volts, currents = c.op()
    total = 0.0
    for term in probe.replace("-", "+-").split("+"):
        if not term:
            continue
        sign = -1.0 if term.startswith("-") else 1.0
        t = term.lstrip("-")
        if t.startswith("v("):
            total += sign * volts[t[2:-1]]
        else:
            total += sign * currents[t[3:-1]]  # i(vNAME) → branch NAME
    return float(total)


class InstModule:
    id = "DM-INST"
    family = "ampops"
    title = "Instrumentação e condicionamento"
    spec_schema = InstSpec
    labels = LABELS
    spec_labels = SPEC_LABELS
    enum_labels = ENUM_LABELS
    lab = [
        LabItem("Saída no fundo de escala", "multímetro CC", "Vo_fs"),
        LabItem("Saída no início da escala", "multímetro CC", "Vo_zero"),
        LabItem("Corrente da malha", "multímetro CC (mA)", "I_hi"),
    ]
    questions = [
        "De onde vem o erro de zero do condicionador? Como compensá-lo?",
        "Por que a malha de corrente 4–20 mA é imune à resistência dos fios?",
        "Por que a ponte de Wheatstone de um quarto não é linear?",
    ]
    practice = {
        "objective": "Montar o condicionador, calibrar zero e fundo de escala e levantar a curva "
        "de transferência.",
        "material": "Fonte simétrica, multímetros, ampops, resistores 1 % e o sensor ou um "
        "simulador (fonte ajustável, década resistiva).",
        "procedure": [
            "Aplique a entrada mínima e meça a saída (erro de zero).",
            "Aplique a entrada máxima e meça a saída (erro de fundo de escala).",
            "Levante cinco pontos intermediários e calcule a não linearidade.",
        ],
    }

    def roles(self, spec: BaseModel) -> list[Role]:
        n = N_OPAMPS[_spec(spec).config]
        return [
            Role(designator=f"U{k + 1}", category="opamp", description="Amplificador operacional")
            for k in range(n)
        ]

    def required_ratings(self, role: Role) -> list[str]:
        return []

    def ambient(self, spec: BaseModel) -> pint.Quantity:
        return _spec(spec).TA.to_pint()

    def interface_resistance(self, spec: BaseModel) -> pint.Quantity:
        return Q_(0, "K/W")

    def accepts(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> bool:
        vs = _spec(spec).VCC.to_pint().m_as("V")
        sym, tot = rec.parameters.get("VS_max"), rec.parameters.get("VS_total_max")
        return (sym is not None and (sym.max or 0) >= vs) or (
            tot is not None and (tot.max or 0) >= 2 * vs
        )

    def preference(self, spec: BaseModel, role: Role, rec: ComponentRecord) -> float:
        vos = rec.parameters.get("Vos")  # precision first: the smallest typical offset
        return (vos.typ or vos.max or 0.0) if vos is not None and vos.has_value else 1e3

    # ------------------------------------------------------------------ design
    def _plan(
        self, s: InstSpec, devices: Mapping[str, Device], log: CalcLog
    ) -> tuple[Build, dict[str, str], float, float, str, dict[str, float], dict[str, float]]:
        """(build(x), probes, x_min, x_max, input unit, part values, ideal outputs)."""
        c = s.config
        vcc = s.VCC.to_pint().m_as("V")
        ops: list[OpAmp] = [
            opamp_model(devices[f"U{k + 1}"].record, vcc, -vcc, log, f"U{k + 1}")[0]
            for k in range(N_OPAMPS[c])
        ]
        vfs = s.V_fs.to_pint().m_as("V")
        rb = s.R_base.to_pint().m_as("ohm")
        v: dict[str, float] = {}

        cache: dict[str, float] = {}

        def com(step: str, desc: str, r: float) -> float:
            # the circuit builders call this once per evaluation: log each value only once
            if step not in cache:
                q = commercial(log, step, desc, Q_(r, "ohm"), s.res_series, "nearest")
                cache[step] = float(q.m_as("ohm"))
            return cache[step]

        def voltmeter(cc: Mna, inp: str, out: str, u: OpAmp, p: str, vmax: float) -> None:
            k = vfs / vmax
            if k < 1:
                rin = s.R_in.to_pint().m_as("ohm")
                rbot = com(f"R{p}b", "Resistor inferior do divisor", k * rin)
                rtop = com(f"R{p}a", "Resistor superior do divisor", rin - rbot)
                v[f"R{p}a"], v[f"R{p}b"] = rtop, rbot
                cc.R(f"{p}a", inp, f"d{p}", rtop)
                cc.R(f"{p}b", f"d{p}", "0", rbot)
                u.add(cc, f"U{p}", f"d{p}", out, out)
            else:
                r2 = com(f"R{p}2", "Realimentação (ganho não inversor)", (k - 1) * rb)
                v[f"R{p}1"], v[f"R{p}2"] = rb, r2
                cc.R(f"{p}1", f"n{p}", "0", rb)
                cc.R(f"{p}2", f"n{p}", out, r2)
                u.add(cc, f"U{p}", inp, f"n{p}", out)

        def ammeter(cc: Mna, node: str, out: str, u: OpAmp, p: str) -> float:
            imax = s.I_max.to_pint().m_as("A")
            rsh = s.V_sh.to_pint().m_as("V") / imax
            g = vfs / s.V_sh.to_pint().m_as("V")
            r2 = com(f"R{p}2", "Realimentação (ganho do canal de corrente)", (g - 1) * rb)
            v[f"R{p}1"], v[f"R{p}2"], v["R_sh"] = rb, r2, rsh
            cc.R(f"{p}sh", node, "0", rsh)
            cc.R(f"{p}1", f"n{p}", "0", rb)
            cc.R(f"{p}2", f"n{p}", out, r2)
            u.add(cc, f"U{p}", node, f"n{p}", out)
            return float(rsh)

        ideal: dict[str, float] = {}
        if c == "voltimetro":
            vmax = s.V_max.to_pint().m_as("V")

            def build1(x: float) -> Mna:
                cc = Mna()
                cc.V("sig", "in", "0", x)
                voltmeter(cc, "in", "o", ops[0], "1", vmax)
                return cc

            build1(0.0)
            ideal["Vo_fs"] = vfs
            return build1, {"Vo": "v(o)"}, 0.0, vmax, "V", v, ideal
        if c == "amperimetro":
            imax = s.I_max.to_pint().m_as("A")

            def build2(x: float) -> Mna:
                cc = Mna()
                cc.I("sig", "0", "sh", x)  # current into the shunt node
                ammeter(cc, "sh", "o", ops[0], "1")
                return cc

            build2(0.0)
            ideal["Vo_fs"] = vfs
            return build2, {"Vo": "v(o)"}, 0.0, imax, "A", v, ideal
        if c == "potencia":
            imax = s.I_max.to_pint().m_as("A")
            vmax = s.V_max.to_pint().m_as("V")

            def build3(x: float) -> Mna:
                cc = Mna()
                cc.V("bus", "bus", "0", vmax)
                cc.I("sig", "0", "sh", x)
                voltmeter(cc, "bus", "ov", ops[0], "1", vmax)
                ammeter(cc, "sh", "oi", ops[1], "2")
                return cc

            build3(0.0)
            ideal |= {"Vo_v_fs": vfs, "Vo_i_fs": vfs}
            return build3, {"Vo_v": "v(ov)", "Vo_i": "v(oi)"}, 0.0, imax, "A", v, ideal
        if c == "transmissor_4_20":
            vmin, vmax = s.Vs_min.to_pint().m_as("V"), s.Vs_max.to_pint().m_as("V")
            rs = s.R_sense.to_pint().m_as("ohm")
            vref = s.V_ref.to_pint().m_as("V")
            # v+ = a·vin + b·Vref with v+(vmin) = 4 mA·Rs and v+(vmax) = 20 mA·Rs
            a = 16e-3 * rs / (vmax - vmin)
            b = (4e-3 * rs - a * vmin) / vref
            if a <= 0 or b <= 0 or a + b >= 1:
                raise ValueError("Rede somadora inviável: ajuste R_sense ou V_ref")
            ra = rb
            gs = 1 / (a * ra)
            rbb = com("R2", "R2 (da referência)", 1 / (b * gs))
            rc = com("R3", "R3 (para o terra)", 1 / (gs - 1 / ra - 1 / rbb))
            v |= {"R1": ra, "R2": rbb, "R3": rc, "R_sense": rs}
            rl = s.R_loop.to_pint().m_as("ohm")
            log.add(
                record(
                    "net_4_20",
                    "Rede somadora do transmissor",
                    r"v_+ = a\,v_{in} + b\,V_{ref},\ a = \frac{16\,\mathrm{mA}\,R_s}{V_{max} - "
                    r"V_{min}},\ b = \frac{4\,\mathrm{mA}\,R_s - a V_{min}}{V_{ref}}",
                    output=Q_(a, ""),
                    inputs={"b": Q_(b, ""), "R_s": Q_(rs, "ohm"), "V_{ref}": Q_(vref, "V")},
                    assumptions=["i = v+/R_s (carga na realimentação, corrente de entrada nula)"],
                    reference=PERT,
                )
            )

            def build4(x: float) -> Mna:
                cc = Mna()
                cc.V("sig", "in", "0", x)
                cc.V("ref", "ref", "0", vref)
                cc.R("1", "in", "p", ra)
                cc.R("2", "ref", "p", rbb)
                cc.R("3", "p", "0", rc)
                cc.R("L", "o", "ld", rl)
                cc.V("ld", "ld", "n", 0.0)  # ammeter of the loop
                cc.R("s", "n", "0", rs)
                ops[0].add(cc, "U1", "p", "n", "o")
                return cc

            ideal |= {"I_lo": 4e-3, "I_hi": 20e-3}
            return build4, {"I": "i(vld)"}, vmin, vmax, "V", v, ideal
        if c == "receptor_4_20":
            rrx = s.R_loop.to_pint().m_as("ohm")
            g = vfs / (16e-3 * rrx)
            vref = 4e-3 * rrx
            r1 = rb
            r2 = com("R2", "R2 (ganho do diferencial)", g * r1)
            r3 = com("R3", "R3 (entrada +)", 10 * rb)
            r4 = com("R4", "R4 = R3·R2/R1", r3 * r2 / r1)
            v |= {"R1": r1, "R2": r2, "R3": r3, "R4": r4, "R_rx": rrx}

            def build5(x: float) -> Mna:
                cc = Mna()
                cc.I("sig", "0", "rx", x)
                cc.R("rx", "rx", "0", rrx)
                cc.V("ref", "ref", "0", vref)
                cc.R("1", "ref", "n", r1)
                cc.R("2", "n", "o", r2)
                cc.R("3", "rx", "p", r3)
                cc.R("4", "p", "0", r4)
                ops[0].add(cc, "U1", "p", "n", "o")
                return cc

            ideal["Vo_fs"] = vfs
            v["V_ref_set"] = vref
            return build5, {"Vo": "v(o)"}, 4e-3, 20e-3, "A", v, ideal
        if c == "ponte_wheatstone":
            vexc = s.V_exc.to_pint().m_as("V")
            r0 = s.R0.to_pint().m_as("ohm")
            vb = vexc * s.x_max / (2 * (2 + s.x_max))
            g = vfs / vb
            r = rb
            rg = com("RG", "RG (ganho do INA)", 2 * r / (g - 1))
            v |= {"R": r, "RG": rg, "R3": rb, "R4": rb}
            log.add(
                record(
                    "Vb_fs",
                    "Saída da ponte de um quarto no fundo de escala",
                    r"v_b = V_{exc}\frac{x}{2(2 + x)}\ \left(\approx V_{exc}\frac{x}{4}\right)",
                    output=Q_(vb, "V").to("mV"),
                    inputs={"V_{exc}": Q_(vexc, "V"), "x": Q_(s.x_max, "")},
                    assumptions=["sensor R0(1 + x) num braço; os outros três iguais a R0"],
                    reference=PERT,
                )
            )

            def build6(x: float) -> Mna:
                cc = Mna()
                cc.V("exc", "e", "0", vexc)
                cc.R("a", "e", "b1", r0)
                cc.R("sens", "b1", "0", r0 * (1 + x))
                cc.R("b", "e", "b2", r0)
                cc.R("c", "b2", "0", r0)
                ops[0].add(cc, "U1", "b1", "i1", "o1")
                ops[1].add(cc, "U2", "b2", "i2", "o2")
                cc.R("f1", "o1", "i1", r)
                cc.R("f2", "o2", "i2", r)
                cc.R("G", "i1", "i2", rg)
                cc.R("3", "o2", "n3", rb)
                cc.R("4", "n3", "o", rb)
                cc.R("5", "o1", "p3", rb)
                cc.R("6", "p3", "0", rb)
                ops[2].add(cc, "U3", "p3", "n3", "o")
                return cc

            ideal |= {"Vo_fs": vfs, "Vb_fs": vb, "Vb_lin": vexc * s.x_max / 4}
            return build6, {"Vo": "v(o)", "Vb": "v(b1)-v(b2)"}, 0.0, s.x_max, "", v, ideal
        # linear sensor conditioning: difference amplifier with Vref = Vs_min
        vmin, vmax = s.Vs_min.to_pint().m_as("V"), s.Vs_max.to_pint().m_as("V")
        if vmax <= vmin:
            raise ValueError("Faixa do sensor inválida")
        g = vfs / (vmax - vmin)
        r1 = rb
        r2 = com("R2", "R2 (ganho)", g * r1)
        v |= {"R1": r1, "R2": r2, "R3": r1, "R4": r2, "V_ref_set": vmin}

        def build7(x: float) -> Mna:
            cc = Mna()
            cc.V("sig", "in", "0", x)
            cc.V("ref", "ref", "0", vmin)
            cc.R("1", "ref", "n", r1)
            cc.R("2", "n", "o", r2)
            cc.R("3", "in", "p", r1)
            cc.R("4", "p", "0", r2)
            ops[0].add(cc, "U1", "p", "n", "o")
            return cc

        ideal["Vo_fs"] = vfs
        return build7, {"Vo": "v(o)"}, vmin, vmax, "V", v, ideal

    def analyse(self, spec: BaseModel, devices: Mapping[str, Device]) -> Analysis:
        s = _spec(spec)
        log = CalcLog()
        build, probes, x0, x1, xu, v, ideal = self._plan(s, devices, log)
        c = s.config
        warnings: list[DesignWarning] = []
        summary: dict[str, pint.Quantity] = {}
        lo = {k: evaluate(build(x0), p) for k, p in probes.items()}
        hi = {k: evaluate(build(x1), p) for k, p in probes.items()}
        sol = "análise nodal com o modelo do ampop (VOS e IB típicos)"
        xin = Q_(x1, xu) if xu else Q_(x1, "")
        if c == "transmissor_4_20":
            summary |= {"I_lo": Q_(lo["I"], "A").to("mA"), "I_hi": Q_(hi["I"], "A").to("mA")}
            log.add(
                record(
                    "I_hi",
                    "Corrente da malha nas entradas mínima e máxima (circuito real)",
                    r"i_L = v_{R_s}/R_s",
                    output=Q_(hi["I"], "A").to("mA"),
                    inputs={"i_{L,min}": Q_(lo["I"], "A").to("mA"), "v_{in,max}": xin},
                    assumptions=[sol],
                    reference=PERT,
                )
            )
            vcc = s.VCC.to_pint().m_as("V")
            vsat = opamp_model(devices["U1"].record, vcc, -vcc, CalcLog(), "U1")[0].v_hi
            rs = s.R_sense.to_pint().m_as("ohm")
            rlmax = vsat / 20e-3 - rs
            summary |= {"RL_max": Q_(rlmax, "ohm"), "V_comp": Q_(vsat, "V")}
            log.add(
                record(
                    "RL_max",
                    "Carga máxima da malha (compliance)",
                    r"R_{L,max} = \frac{V_{sat+}}{I_{max}} - R_s",
                    output=Q_(rlmax, "ohm"),
                    inputs={"V_{sat+}": Q_(vsat, "V"), "R_s": Q_(rs, "ohm")},
                    assumptions=["a saída do ampop alimenta a carga e o R_s em série"],
                    reference=PERT,
                )
            )
            if s.R_loop.to_pint().m_as("ohm") > rlmax:
                warnings.append(
                    DesignWarning(
                        code="compliance",
                        message="A carga da malha passa da compliance: a corrente satura.",
                    )
                )
            err = (hi["I"] / 20e-3 - 1) * 100
        else:
            key = "Vo_i" if c == "potencia" else "Vo"  # power: zero error is in the I channel
            summary |= {"Vo_fs": Q_(hi[key], "V"), "Vo_zero": Q_(lo[key], "V").to("mV")}
            log.add(
                record(
                    "Vo_fs",
                    "Saída do circuito real no início e no fundo de escala",
                    r"v_o(x_{max}),\ v_o(x_{min})",
                    output=Q_(hi[key], "V"),
                    inputs={"v_o(x_{min})": Q_(lo[key], "V").to("mV"), "x_{max}": xin},
                    assumptions=[sol],
                    reference=REF,
                )
            )
            err = (hi[key] / ideal.get("Vo_fs", ideal.get("Vo_v_fs", 1.0)) - 1) * 100
            if c == "potencia":
                gi = s.V_fs.to_pint().m_as("V") / s.I_max.to_pint().m_as("A")
                gv = s.V_fs.to_pint().m_as("V") / s.V_max.to_pint().m_as("V")
                p = (hi["Vo_v"] / gv) * (hi["Vo_i"] / gi)
                summary |= {
                    "Vo_v_fs": Q_(hi["Vo_v"], "V"),
                    "Vo_i_fs": Q_(hi["Vo_i"], "V"),
                    "P_fs": Q_(p, "W"),
                }
                log.add(
                    record(
                        "P_fs",
                        "Potência calculada a partir dos dois canais",
                        r"P = \frac{V_{o,v}}{G_v}\cdot\frac{V_{o,i}}{G_i}",
                        output=Q_(p, "W"),
                        inputs={"G_v": Q_(gv, ""), "G_i": Q_(gi, "V/A")},
                        assumptions=["produto feito no processamento (ADC + software)"],
                        reference=PERT,
                    )
                )
            if c == "ponte_wheatstone":
                vb, vl = hi["Vb"], ideal["Vb_lin"]
                summary |= {
                    "Vb_fs": Q_(vb, "V").to("mV"),
                    "Vb_lin": Q_(vl, "V").to("mV"),
                    "nl_err": Q_((vb / vl - 1) * 100, "percent"),
                }
        summary["err_fs"] = Q_(err, "percent")
        if abs(err) > 1:
            warnings.append(
                DesignWarning(
                    code="erro",
                    message=f"Erro de fundo de escala de {err:+.2f} % (arredondamento, offset "
                    "e corrente de polarização): calibre com um trimpot.",
                )
            )
        if c in ("amperimetro", "potencia"):
            rsh = v["R_sh"]
            imax = s.I_max.to_pint().m_as("A")
            summary |= {"R_sh": Q_(rsh, "ohm").to("mohm"), "P_sh": Q_(imax**2 * rsh, "W")}
        if c == "voltimetro" and "R1a" in v:
            summary["Rin"] = Q_(v["R1a"] + v["R1b"], "ohm").to("Mohm")
        for k, x in v.items():
            if k in ("R_sh",):
                continue
            summary[k] = Q_(x, "V") if k == "V_ref_set" else Q_(x, "ohm")
        return Analysis(
            log=log,
            stresses=[],
            summary=summary,
            losses={},
            warnings=warnings,
            convergence_keys=("err_fs",),
        )

    # ------------------------------------------------------------------ circuit
    def build_circuit(
        self, spec: BaseModel, devices: Mapping[str, Device], summary: Mapping[str, QuantityModel]
    ) -> Circuit:
        s = _spec(spec)
        build, probes, x0, x1, _, _, _ = self._plan(s, devices, CalcLog())
        c = s.config
        start = build(x1 if c == "ponte_wheatstone" else x0)
        vdc, _ = start.op()
        lines = []
        for line in start.netlist():
            if line.startswith("C"):  # start at the DC solution (the macromodel pole caps)
                _, a, b, _val = line.split()
                line += f" IC={vdc.get(a, 0.0) - vdc.get(b, 0.0):.12g}"
            lines.append(line)
        if c != "ponte_wheatstone":  # the input as a ramp: both ends in one run
            for k, line in enumerate(lines):
                if line.split()[0] in ("Vsig", "Isig"):
                    name, a, b = line.split()[:3]
                    # flat at both ends so that min/max are the two static values
                    pts = f"0 {x0:.12g} {0.1 * T_RAMP:.12g} {x0:.12g} {0.9 * T_RAMP:.12g} {x1:.12g}"
                    lines[k] = f"{name} {a} {b} PWL({pts} {T_RAMP:.12g} {x1:.12g})"
        checks: list[SimCheck] = []
        why = "mesmo circuito linear; entrada em rampa quase estática"
        if c == "transmissor_4_20":
            checks = [
                SimCheck(
                    quantity="Corrente na entrada máxima",
                    summary_key="I_hi",
                    metric="max",
                    probe="i(vld)",
                    tolerance_pct=0.5,
                    justification=why,
                ),
                SimCheck(
                    quantity="Corrente na entrada mínima",
                    summary_key="I_lo",
                    metric="min",
                    probe="i(vld)",
                    tolerance_pct=0.5,
                    justification=why,
                ),
            ]
        elif c == "potencia":
            checks = [
                SimCheck(
                    quantity="Canal de tensão",
                    summary_key="Vo_v_fs",
                    metric="max",
                    probe="v(ov)",
                    tolerance_pct=0.5,
                    justification=why,
                ),
                SimCheck(
                    quantity="Canal de corrente no fundo de escala",
                    summary_key="Vo_i_fs",
                    metric="max",
                    probe="v(oi)",
                    tolerance_pct=0.5,
                    justification=why,
                ),
            ]
        elif c == "ponte_wheatstone":
            checks = [
                SimCheck(
                    quantity="Saída no fundo de escala",
                    summary_key="Vo_fs",
                    metric="avg",
                    probe="v(o)",
                    tolerance_pct=0.5,
                    justification="mesmo circuito linear (ponto de operação)",
                ),
                SimCheck(
                    quantity="Saída da ponte",
                    summary_key="Vb_fs",
                    metric="avg",
                    probe="v(b1)-v(b2)",
                    tolerance_pct=0.5,
                    justification="mesmo circuito linear (ponto de operação)",
                ),
            ]
        else:
            checks = [
                SimCheck(
                    quantity="Saída no fundo de escala",
                    summary_key="Vo_fs",
                    metric="max",
                    probe="v(o)",
                    tolerance_pct=0.5,
                    justification=why,
                ),
                SimCheck(
                    quantity="Saída no início da escala",
                    summary_key="Vo_zero",
                    metric="min",
                    probe="v(o)",
                    tolerance_pct=0.5,
                    justification=why,
                ),
            ]
        return Circuit(
            title=f"{self.id}: {ENUM_LABELS[c]}",
            netlist="\n".join(lines),
            tran_stop=QuantityModel(value=T_RAMP, unit="s"),
            tran_step=QuantityModel(value=T_RAMP / 200, unit="s"),
            period=QuantityModel(value=T_RAMP, unit="s"),
            probes={k: p for k, p in probes.items()},
            checks=checks,
        )

    # ------------------------------------------------------------------ outputs
    def schematic(self, spec: BaseModel, result: DesignResult, title: str) -> str:
        s = _spec(spec)
        sm = result.summary
        vals = {k: format_eng(sm[k].to_pint()) for k in sm if k.startswith("R") and k != "RL_max"}
        parts = {c.designator: c.part_number for c in result.selection}
        return value_sheet(title, ENUM_LABELS[s.config], vals, parts)

    def bom_extra(self, spec: BaseModel, result: DesignResult) -> list[BomRow]:
        sm = result.summary
        rows = []
        for k in sm:
            if k == "R_sh":
                rows.append(
                    passive(
                        k, "Resistor shunt de precisão (4 terminais)", format_eng(sm[k].to_pint())
                    )
                )
            elif k.startswith("R") and k not in ("RL_max", "Rin"):
                rows.append(
                    passive(k, "Resistor 0,1 % (filme metálico)", format_eng(sm[k].to_pint()))
                )
        return rows
