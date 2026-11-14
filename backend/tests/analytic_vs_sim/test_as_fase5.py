"""AS-OPA-01, AS-FIL-01, AS-OPNL-01, AS-OSC-01, AS-INST-01: Phase 5 analytic × ngspice.

Each case designs with the reviewed catalogue, builds the same circuit the result describes and
compares every SimCheck. The tolerance of each check is in the module (``SimCheck.tolerance_pct``
with its justification); a divergence above it fails here and is a warning in the result.
"""

import pytest

from circuitos.design import registry
from circuitos.design.engine import run
from circuitos.design.verify import compare_full
from circuitos.selection.derating import DeratingPolicy

pytestmark = pytest.mark.ngspice


def q(v: float, u: str) -> dict[str, object]:
    return {"value": v, "unit": u}


OPA = {
    f"opa_{c}": ("DM-OPA", {"config": c})
    for c in (
        "inversor",
        "nao_inversor",
        "seguidor",
        "somador",
        "subtrator",
        "integrador",
        "diferenciador",
        "transimpedancia",
        "transcondutancia",
        "instrumentacao",
    )
}
F_STOP = {"passa_baixas": 3000, "passa_altas": 300, "passa_faixa": 1500, "rejeita_faixa": 1020}
FIL = (
    {
        f"fil_{k}_{a}_{r}": (
            "DM-FIL",
            {"kind": k, "approx": a, "realization": r, "f_stop": q(F_STOP[k], "Hz")},
        )
        for k in ("passa_baixas", "passa_altas")
        for a in ("butterworth", "chebyshev", "bessel", "eliptico")
        for r in ("sallen_key", "mfb", "variaveis_estado")
    }
    | {
        f"fil_{k}_{a}_{r}": (
            "DM-FIL",
            {"kind": k, "approx": a, "realization": r, "f_stop": q(F_STOP[k], "Hz")},
        )
        for k in ("passa_faixa", "rejeita_faixa")
        for a in ("butterworth", "chebyshev")
        for r in ("sallen_key", "mfb", "variaveis_estado")
    }
    | {
        "fil_lc_butter": ("DM-FIL", {"realization": "passivo_lc"}),
        "fil_lc_cheby_hp": (
            "DM-FIL",
            {
                "realization": "passivo_lc",
                "approx": "chebyshev",
                "kind": "passa_altas",
                "f_stop": q(300, "Hz"),
            },
        ),
    }
)
OPNL = {
    f"opnl_{c}": ("DM-OPNL", {"config": c})
    for c in (
        "comparador",
        "schmitt_inversor",
        "schmitt_nao_inversor",
        "retificador_meia",
        "retificador_onda",
        "logaritmico",
        "limitador",
    )
} | {
    "opnl_comparador_lm311": ("DM-OPNL", {"config": "comparador", "device": "comparador"}),
    "opnl_limitador_g2": ("DM-OPNL", {"config": "limitador", "G": 2}),
}
OSC = {
    f"osc_{c}": ("DM-OSC", {"config": c})
    for c in (
        "wien",
        "deslocamento_fase",
        "astavel_ampop",
        "ne555_astavel",
        "ne555_monoestavel",
        "multivibrador_tbj",
    )
}
INST = {
    f"inst_{c}": ("DM-INST", {"config": c})
    for c in (
        "voltimetro",
        "amperimetro",
        "potencia",
        "transmissor_4_20",
        "receptor_4_20",
        "ponte_wheatstone",
        "condicionamento",
    )
}
CASES = OPA | FIL | OPNL | OSC | INST


@pytest.mark.parametrize("name", list(CASES))
def test_as_fase5(reviewed_catalogue, name):
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
    passive = raw.get("realization") == "passivo_lc"  # LC ladder: nothing to select
    assert res.selection or passive, "nenhum componente selecionado"
    comparisons, _, _ = compare_full(mod.build_circuit(spec, devices, res.summary), res.summary)
    assert comparisons
    bad = [c for c in comparisons if not c.ok]
    assert not bad, "\n".join(
        f"{c.quantity}: analítico {c.analytic.value:.5g}, simulado {c.simulated.value:.5g} "
        f"({c.error_pct:.2f} % > {c.tolerance_pct} %)"
        for c in bad
    )
