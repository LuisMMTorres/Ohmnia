"""Turn ngspice error output into clear messages with suggestions (prompt, section 5)."""

from __future__ import annotations

import re

from circuitos.core.errors import ConvergenceError, SimulationError

_RULES: list[tuple[re.Pattern[str], str, list[str], bool]] = [
    (
        re.compile(r"more than the memory available|setting the output memory is not possible", re.I),
        "Memória insuficiente para guardar os resultados da simulação.",
        [
            "Reduza o tempo simulado ou aumente o passo de saída (TSTEP) em .tran.",
            "Use TSTART em .tran para guardar só o regime permanente.",
            "Guarde só os vetores necessários com .save.",
        ],
        False,
    ),
    (
        re.compile(r"timestep too small", re.I),
        "Passo de tempo muito pequeno: o simulador não conseguiu avançar no tempo.",
        [
            "Limite o passo máximo em .tran (quarto argumento) para algo como 1/100 do período "
            "de comutação.",
            "Suavize transições ideais: tempos de subida e descida não nulos nas fontes PULSE.",
            "Use o modelo ideal das chaves para estudar a topologia antes do modelo do "
            "dispositivo.",
            "Aumente RELTOL (ex.: .options reltol=0.003) ou use .options method=gear.",
        ],
        True,
    ),
    (
        re.compile(r"singular matrix", re.I),
        "Matriz singular: há nó flutuante ou malha só de fontes de tensão/indutores.",
        [
            "Verifique se todo nó tem caminho CC para o terra (0).",
            "Inclua resistência série em indutores e fontes de tensão em paralelo com capacitores.",
            "Adicione resistência de alto valor (ex.: 1 GΩ) do nó flutuante para o terra.",
        ],
        True,
    ),
    (
        re.compile(r"gmin stepping failed|source stepping failed|no convergence in dc", re.I),
        "O ponto de operação CC não convergiu.",
        [
            "Forneça condições iniciais com .ic ou .nodeset nos nós principais.",
            "Aumente GMIN (ex.: .options gmin=1e-10) ou ITL1.",
            "Use 'uic' em .tran para começar sem calcular o ponto de operação.",
        ],
        True,
    ),
    (
        re.compile(r"unknown (model|subckt)|could not find (a valid )?modelname|no model", re.I),
        "Modelo ou subcircuito não encontrado.",
        ["Confira o nome em .model/.subckt e se o arquivo .lib foi incluído com .include."],
        False,
    ),
    (
        re.compile(r"unknown device type|unrecognized|syntax error|error on line", re.I),
        "Erro de sintaxe na netlist.",
        ["Verifique a linha indicada no registro do simulador."],
        False,
    ),
]


def error_lines(log: str) -> list[str]:
    return [
        line
        for line in log.splitlines()
        if re.search(r"\berror\b|fatal|singular|too small|failed", line, re.I)
    ]


def raise_for_log(log: str, *, no_output: bool) -> None:
    """Raise a classified error if the log shows a failure (or nothing was produced)."""
    for pattern, message, suggestions, convergence in _RULES:
        if pattern.search(log):
            cls = ConvergenceError if convergence else SimulationError
            raise cls(message, log=log, suggestions=suggestions)
    if no_output:
        lines = error_lines(log)
        detail = lines[0].strip() if lines else "nenhum vetor foi produzido"
        raise SimulationError(f"A simulação falhou: {detail}", log=log)
