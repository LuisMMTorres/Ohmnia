"""AS-ZEN/LIN/BIAS/SSA/DIFF/PA/PAD/CHAVE/FORMA: Phase 4 analytic designs × ngspice.

Every module computes with the same device equations the simulator uses (Ebers-Moll BJT with
IS and BF from the chosen part, Darlington as two Ebers-Moll transistors, Shockley JFET (NJF),
LEVEL 1 MOSFET, piecewise-linear Zener, constant-drop diode, behavioural regulator, class D
switches as RON/ROFF switches driven by the same comparator), so the tolerance of each check
only covers numerics, stated in the module's ``SimCheck.justification``. Small-signal gains and
corner frequencies come from the exact nodal solution of the hybrid-π network, compared with
``.ac``. Measured on 2026-11-14: worst error 0,6 % on exact checks; the voltage-multiplier
ripple (linear-discharge formula) up to 6,1 % against a 25 % tolerance. Table in
docs/validacao/fontes-amplificadores.md.
"""

import pytest

from circuitos.design import registry
from circuitos.design.engine import run
from circuitos.design.verify import compare_full
from circuitos.selection.derating import DeratingPolicy

pytestmark = pytest.mark.ngspice


def q(v: float, u: str) -> dict[str, object]:
    return {"value": v, "unit": u}


CASES: dict[str, tuple[str, dict[str, object]]] = {
    "zen_simples": ("DM-ZEN", {}),
    "zen_transistor": ("DM-ZEN", {"variant": "transistor", "IL_max": q(300, "mA")}),
    "lin_fixo_pos": ("DM-LIN", {}),
    "lin_fixo_neg": ("DM-LIN", {"polarity": "negativa", "Vo": q(12, "V"), "Vin": q(18, "V")}),
    "lin_fixo_sim": ("DM-LIN", {"polarity": "simetrica", "Vo": q(15, "V"), "Vin": q(22, "V")}),
    "lin_ajust": ("DM-LIN", {"kind": "ajustavel", "Vo": q(9, "V"), "Vin": q(15, "V")}),
    "lin_ajust_sim": (
        "DM-LIN",
        {"kind": "ajustavel", "polarity": "simetrica", "Vo": q(9, "V"), "Vin": q(15, "V")},
    ),
    "lin_ldo_fixo": ("DM-LIN", {"ldo": True, "Vin": q(8, "V"), "ripple_pp": q(0.5, "V")}),
    "lin_ldo_100ma": (
        "DM-LIN",
        {"ldo": True, "Io": q(80, "mA"), "Vin": q(9, "V"), "ripple_pp": q(0.5, "V")},
    ),
    "lin_ldo_ajust": (
        "DM-LIN",
        {
            "ldo": True,
            "kind": "ajustavel",
            "Vo": q(3.3, "V"),
            "Io": q(50, "mA"),
            "Vin": q(6, "V"),
            "ripple_pp": q(0.5, "V"),
        },
    ),
    "bias_fixa": ("DM-BIAS", {"config": "fixa"}),
    "bias_emissor": ("DM-BIAS", {"config": "emissor"}),
    "bias_divisor": ("DM-BIAS", {}),
    "bias_coletor": ("DM-BIAS", {"config": "coletor"}),
    "bias_mos": ("DM-BIAS", {"config": "mos_divisor", "IC": q(10, "mA")}),
    "bias_jfet_auto": ("DM-BIAS", {"config": "jfet_auto", "IC": q(1, "mA")}),
    "bias_jfet_divisor": ("DM-BIAS", {"config": "jfet_divisor", "IC": q(1, "mA")}),
    "ssa_ec": ("DM-SSA", {}),
    "ssa_ec_bypass": ("DM-SSA", {"Av": 0}),
    "ssa_cc": ("DM-SSA", {"config": "CC"}),
    "ssa_bc": ("DM-SSA", {"config": "BC"}),
    "ssa_fc": ("DM-SSA", {"config": "FC", "IC": q(10, "mA"), "Av": 3}),
    "ssa_fcj": ("DM-SSA", {"config": "FCJ", "IC": q(1, "mA")}),
    "diff_resistor": ("DM-DIFF", {}),
    "diff_espelho": ("DM-DIFF", {"tail": "espelho"}),
    "pa_a": ("DM-PA", {"cls": "A", "Po": q(0.5, "W")}),
    "pa_b": ("DM-PA", {"cls": "B"}),
    "pa_ab": ("DM-PA", {}),
    "pa_b_darlington": ("DM-PA", {"cls": "B", "darlington": True}),
    "pa_ab_darlington": ("DM-PA", {"darlington": True}),
    "pad_padrao": ("DM-PAD", {}),
    "pad_4ohm": (
        "DM-PAD",
        {
            "VCC": q(15, "V"),
            "RL": q(4, "ohm"),
            "Po": q(20, "W"),
            "fs": q(400, "kHz"),
            "fc": q(30, "kHz"),
        },
    ),
    "chave_tbj_ind": ("DM-CHAVE", {}),
    "chave_tbj_res": ("DM-CHAVE", {"load": "resistiva"}),
    "chave_darlington_ind": ("DM-CHAVE", {"device": "darlington"}),
    "chave_darlington_res": (
        "DM-CHAVE",
        {"device": "darlington", "load": "resistiva", "R_load": q(12, "ohm")},
    ),
    "chave_mos": ("DM-CHAVE", {"device": "mosfet", "R_load": q(12, "ohm"), "V_drive": q(10, "V")}),
    "forma_paralelo": ("DM-FORMA", {}),
    "forma_serie": ("DM-FORMA", {"kind": "ceifador_serie"}),
    "forma_duplo": ("DM-FORMA", {"kind": "ceifador_duplo"}),
    "forma_grampeador": ("DM-FORMA", {"kind": "grampeador"}),
    "forma_grampeador_neg": (
        "DM-FORMA",
        {"kind": "grampeador", "VB": q(-2, "V"), "C": q(1, "uF"), "RL": q(10, "kohm")},
    ),
    "forma_dobrador": ("DM-FORMA", {"kind": "multiplicador"}),
    "forma_cw3": (
        "DM-FORMA",
        {
            "kind": "multiplicador",
            "stages": 3,
            "Vm": q(100, "V"),
            "f": q(60, "Hz"),
            "RL": q(1, "Mohm"),
        },
    ),
}


@pytest.mark.parametrize("name", list(CASES))
def test_as_fase4(reviewed_catalogue, name):
    repo = reviewed_catalogue
    mid, raw = CASES[name]
    mod = registry.get(mid)
    spec = mod.spec_schema(**raw)
    res, devices = run(
        mod,
        spec,
        lambda c: repo.search(category=c),
        repo.get,
        DeratingPolicy.from_preset("didatico"),
    )
    assert res.selection, "nenhum componente selecionado"
    comparisons, _, _ = compare_full(mod.build_circuit(spec, devices, res.summary), res.summary)
    assert comparisons
    bad = [c for c in comparisons if not c.ok]
    assert not bad, "\n".join(
        f"{c.quantity}: analítico {c.analytic.value:.5g}, simulado {c.simulated.value:.5g} "
        f"({c.error_pct:.2f} % > {c.tolerance_pct} %)"
        for c in bad
    )
