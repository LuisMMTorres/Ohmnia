"""HTML design report with calculation memory and lab guide (Jinja2)."""

from __future__ import annotations

import base64
import datetime as dt
import functools
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel

from circuitos.core.units import QuantityModel, format_eng
from circuitos.design.base import DesignResult, SimComparison

from . import rectifiers

_ENV = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html", "j2"]),
)

_KATEX = Path(__file__).parent / "vendor" / "katex"


@functools.cache
def katex_assets() -> dict[str, str]:
    """KaTeX 0.16.11 (MIT) inlined so the report renders the equations offline.

    Only the woff2 fonts are embedded, as data URIs.
    """

    def font(match: re.Match[str]) -> str:
        name = match.group(1)
        data = base64.b64encode((_KATEX / "fonts" / f"{name}.woff2").read_bytes()).decode()
        return f'src:url(data:font/woff2;base64,{data}) format("woff2")'

    css = (_KATEX / "katex.min.css").read_text(encoding="utf-8")
    css = re.sub(r'src:url\(fonts/([\w-]+)\.woff2\) format\("woff2"\)[^;}]*', font, css)
    return {
        "css": css,
        "js": (_KATEX / "katex.min.js").read_text(encoding="utf-8"),
        "auto_render": (_KATEX / "auto-render.min.js").read_text(encoding="utf-8"),
    }


LABELS: dict[str, str] = {
    "Vo": "Tensão média na carga",
    "Vo_rms": "Tensão eficaz na carga",
    "dVo": "Ondulação de pico a pico",
    "Io": "Corrente média na carga",
    "Io_rms": "Corrente eficaz na carga",
    "dIo": "Ondulação da corrente de carga",
    "Vm": "Tensão de pico do secundário",
    "Vsec": "Tensão eficaz do secundário",
    "Vll_m": "Tensão de linha de pico do secundário",
    "Vll_sec": "Tensão de linha eficaz do secundário",
    "N": "Relação de espiras",
    "VA_sec": "Potência aparente do secundário",
    "VA_pri": "Potência aparente do primário",
    "PF": "Fator de potência",
    "DPF": "Fator de deslocamento",
    "THD_i": "THD da corrente de entrada",
    "ID_avg": "Corrente média por diodo",
    "ID_rms": "Corrente eficaz por diodo",
    "ID_pk": "Corrente de pico por diodo",
    "PIV": "Tensão reversa de pico por diodo",
    "C": "Capacitor de filtro",
    "C2": "Segundo capacitor (π)",
    "L": "Indutor de filtro",
    "IC_rms": "Corrente eficaz no capacitor",
    "VC_max": "Tensão máxima no capacitor",
    "dV_C1": "Ondulação em C1",
    "IT_avg": "Corrente média por tiristor",
    "IT_rms": "Corrente eficaz por tiristor",
    "IT_pk": "Corrente de pico por tiristor",
    "VDRM": "Tensão direta de bloqueio",
    "VRRM": "Tensão reversa de bloqueio",
    "alpha": "Ângulo de disparo nominal",
    "alpha_min": "α mínimo (rede baixa)",
    "alpha_max": "α máximo (rede alta)",
    "beta": "Ângulo de extinção",
    "mu": "Ângulo de comutação μ",
    "dV_mu": "Queda por comutação",
    "I_dev_avg": "Corrente média por dispositivo",
    "I_dev_rms": "Corrente eficaz por dispositivo",
    "V_block": "Tensão de bloqueio por dispositivo",
    "I_line": "Corrente de linha eficaz",
    "I_pri_ref": "Corrente do primário (referida ao secundário Y)",
    "Isec": "Corrente eficaz do secundário",
    "P_out": "Potência na carga",
    "eff": "Rendimento (diodos)",
    "R_load": "Resistência equivalente da carga",
    "Vo_ideal": "Tensão média com dispositivos ideais",
}
HIDDEN = {"continuous", "Isec_ac"}

SPEC_LABELS: dict[str, str] = {
    "topology": "Topologia",
    "filter": "Filtro",
    "Vin": "Tensão do primário",
    "f": "Frequência",
    "Vo": "Tensão média desejada",
    "Io": "Corrente na carga",
    "ripple_pct": "Ondulação desejada (%)",
    "L_factor": "Fator do indutor (× Lcrit)",
    "cap_series": "Série de capacitores",
    "TA": "Temperatura ambiente",
    "Rth_cs": "Rθ cápsula-dissipador (premissa)",
    "freewheel": "Diodo de roda livre",
    "R": "Resistência da carga",
    "L": "Indutância da carga",
    "E": "Força contraeletromotriz",
    "alpha_nom": "Ângulo de disparo nominal",
    "vin_tol_pct": "Variação da rede (± %)",
    "pulses": "Número de pulsos",
    "controlled": "Controlado",
    "Ls": "Indutância da fonte por fase",
}

ENUM_LABELS: dict[str, str] = {
    "meia_onda": "meia onda",
    "center_tap": "onda completa com derivação central",
    "ponte": "onda completa em ponte",
    "semicontrolada": "ponte semicontrolada",
    "nenhum": "sem filtro",
    "C": "capacitivo (C)",
    "LC": "indutivo-capacitivo (LC)",
    "pi": "π (C-L-C)",
    "E3": "E3",
    "E6": "E6",
    "E12": "E12",
}

QUESTIONS: dict[str, list[str]] = {
    "DM-RET1": [
        "Por que a corrente no diodo com filtro capacitivo é um pulso estreito e alto? Relacione "
        "com o fator de potência medido.",
        "O que acontece com a ondulação e com a corrente de pico se C dobrar?",
        "Compare a tensão média medida com a calculada: qual parcela da diferença vem da "
        "resistência do enrolamento do transformador?",
    ],
    "DM-RETC1": [
        "Explique por que a tensão média cai com α e por que, com carga RL, ela pode ficar "
        "negativa em parte do ciclo.",
        "Em que condição a corrente se torna contínua? Confira com ωL/R da montagem.",
        "Qual o efeito do diodo de roda livre (ou da ponte semicontrolada) no fator de potência?",
    ],
    "DM-RET3": [
        "Por que a ponte de 6 pulsos tem harmônicas 6k ± 1 na corrente de linha e o arranjo de "
        "12 pulsos elimina a 5ª e a 7ª?",
        "Meça o ângulo de comutação μ nos entalhes da tensão de saída e compare com o calculado.",
        "Como a indutância da fonte reduz a tensão média? Estime ωLs a partir da queda medida.",
    ],
}


def _fmt(q: QuantityModel | None) -> str:
    if q is None:
        return "—"
    if q.unit in ("", "dimensionless"):
        return f"{q.value:.3g}".replace(".", ",")
    if q.unit in ("percent", "%"):
        return f"{q.value:.3g} %".replace(".", ",")
    if q.unit in ("deg", "degree"):
        return f"{q.value:.3g}°".replace(".", ",")
    if q.unit in ("degC", "°C"):
        return f"{q.value:.3g} °C".replace(".", ",")
    try:
        return format_eng(q.to_pint())
    except Exception:  # unusual units: plain text
        return f"{q.value:.3g} {q.unit}".replace(".", ",")


def _spec_rows(spec: BaseModel) -> list[tuple[str, str]]:
    rows = []
    for key, value in spec.model_dump().items():
        label = SPEC_LABELS.get(key, key)
        if isinstance(value, dict) and "value" in value:
            text = _fmt(QuantityModel(**value))
        elif isinstance(value, bool):
            text = "sim" if value else "não"
        elif isinstance(value, float):
            text = f"{value:g}".replace(".", ",")
        else:
            text = ENUM_LABELS.get(str(value), str(value).replace("_", " "))
        rows.append((label, text))
    return rows


def render(
    module_id: str,
    title: str,
    spec: BaseModel,
    result: DesignResult,
    policy: str,
    sim: list[SimComparison] | None = None,
) -> str:
    sim_by_key: dict[str, QuantityModel] = {}
    if sim:
        for c in sim:
            for key, q in result.summary.items():
                if q == c.analytic:
                    sim_by_key.setdefault(key, c.simulated)
    lab = [
        {
            "quantity": item.quantity,
            "instrument": item.instrument,
            "calc": _fmt(result.summary.get(item.summary_key)),
            "sim": _fmt(sim_by_key.get(item.summary_key)),
        }
        for item in rectifiers.LAB.get(module_id, [])
        if item.summary_key in result.summary
    ]
    summary_rows = [
        (LABELS.get(k, k), _fmt(q)) for k, q in result.summary.items() if k not in HIDDEN
    ]
    alpha = result.summary.get("alpha")
    return _ENV.get_template("report.html.j2").render(
        title=title,
        title_lower=title[0].lower() + title[1:],
        module_id=module_id,
        generated=dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
        policy=policy,
        spec_rows=_spec_rows(spec),
        schematic=rectifiers.schematic_svg(spec, result, title),
        summary_rows=summary_rows,
        summary_keys=set(result.summary),
        warnings=result.warnings,
        selection=result.selection,
        margins=result.margins,
        thermal=result.thermal,
        bom=rectifiers.bom(spec, result),
        sim=sim,
        steps=result.steps,
        lab=lab,
        safety=rectifiers.SAFETY,
        questions=QUESTIONS.get(module_id, []),
        alpha=_fmt(alpha),
        status={"ok": "ok", "atencao": "atenção", "violado": "violado"},
        fmt=_fmt,
        katex=katex_assets(),
    )
