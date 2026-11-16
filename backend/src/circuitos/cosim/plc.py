"""PLC runtime: structured text (IEC 61131-3 subset), ladder, function blocks, scan cycle.

Every scan reads the input image (``I0``..``I5``, ``AI0``, ``AI1``), runs the program once and
writes the output image (``Q0``..``Q3``, ``AQ0``). Names are case-insensitive, as in IEC 61131-3.

Ladder is stored as rungs: each rung is an OR of branches, each branch an AND of elements read
left to right (contacts, edge contacts, comparisons, timers and counters in series), ending in
coils (normal, negated, set, reset) or a MOVE. Comparisons and MOVE sources use structured-text
expressions, so both languages share one evaluator.
"""

from __future__ import annotations

import contextlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

from circuitos.cosim.clang import CError

IO_BOOL_IN = tuple(f"I{n}" for n in range(6))
IO_BOOL_OUT = tuple(f"Q{n}" for n in range(4))
IO_REAL_IN = ("AI0", "AI1")
IO_REAL_OUT = ("AQ0",)


class PlcError(CError):
    pass


# ------------------------------------------------------------------------------------ lexer

_TOK = re.compile(
    r"""
    (?P<ws>[ \t\r]+) | (?P<nl>\n) | (?P<c1>\(\*.*?\*\)) | (?P<c2>//[^\n]*)
  | (?P<time>(?:T|TIME)\#[0-9dhmsDHMS_.]+)
  | (?P<num>\d+\.\d+(?:[eE][+-]?\d+)?|\d+(?:[eE][+-]?\d+)?)
  | (?P<id>[A-Za-z_]\w*)
  | (?P<op>:=|=>|<>|<=|>=|\*\*|\.\.|[-+*/=<>():;,.&\[\]#])
    """,
    re.VERBOSE | re.DOTALL,
)


def time_ms(text: str) -> float:
    """``T#1m30s`` → 90000 (milliseconds)."""
    body = text.split("#", 1)[1].lower().replace("_", "")
    total = 0.0
    for value, unit in re.findall(r"(\d+(?:\.\d+)?)(ms|d|h|m|s)", body):
        total += float(value) * {"ms": 1, "s": 1e3, "m": 6e4, "h": 3.6e6, "d": 8.64e7}[unit]
    if not total and not re.fullmatch(r"0+(ms|s)?", body):
        raise PlcError(f"tempo inválido: {text}")
    return total


@dataclass
class Tok:
    kind: str
    value: Any
    line: int


def lex(src: str) -> list[Tok]:
    out: list[Tok] = []
    line, pos = 1, 0
    while pos < len(src):
        m = _TOK.match(src, pos)
        if m is None:
            raise PlcError(f"caractere inesperado {src[pos]!r}", line)
        kind = m.lastgroup or ""
        text = m.group(kind)
        pos = m.end()
        if kind == "nl":
            line += 1
        elif kind in ("ws", "c2"):
            pass
        elif kind == "c1":
            line += text.count("\n")
        elif kind == "time":
            out.append(Tok("num", time_ms(text), line))
        elif kind == "num":
            out.append(
                Tok("num", float(text) if any(c in text for c in ".eE") else int(text), line)
            )
        elif kind == "id":
            out.append(Tok("id", text.upper(), line))
        else:
            out.append(Tok("op", text, line))
    out.append(Tok("eof", None, line))
    return out


# ----------------------------------------------------------------------------------- parser

FB_TYPES = {"TON", "TOF", "TP", "CTU", "CTD", "R_TRIG", "F_TRIG", "SR", "RS", "PID"}
VAR_TYPES = {
    "BOOL",
    "INT",
    "DINT",
    "SINT",
    "UINT",
    "UDINT",
    "WORD",
    "BYTE",
    "REAL",
    "LREAL",
    "TIME",
}
FUNCS = {
    "ABS",
    "SQRT",
    "MIN",
    "MAX",
    "LIMIT",
    "SEL",
    "TRUNC",
    "EXP",
    "LN",
    "LOG",
    "SIN",
    "COS",
    "TAN",
    "ROUND",
    "INT_TO_REAL",
    "REAL_TO_INT",
    "TO_REAL",
    "TO_INT",
    "DINT_TO_REAL",
    "REAL_TO_DINT",
    "BOOL_TO_INT",
    "TIME_TO_REAL",
    "REAL_TO_TIME",
    "MOVE",
}


@dataclass
class Decl:
    name: str
    vtype: str
    init: Any = None


@dataclass
class StProgram:
    decls: list[Decl] = field(default_factory=list)
    body: list[Any] = field(default_factory=list)


class _Parser:
    def __init__(self, toks: list[Tok]):
        self.t = toks
        self.i = 0

    @property
    def cur(self) -> Tok:
        return self.t[self.i]

    def at(self, *v: str) -> bool:
        return self.cur.kind in ("op", "id") and self.cur.value in v

    def eat(self, v: str) -> Tok:
        if not self.at(v):
            got = self.cur.value if self.cur.kind != "eof" else "fim do programa"
            raise PlcError(f"esperado '{v}', encontrado {got!r}", self.cur.line)
        tok = self.cur
        self.i += 1
        return tok

    def name(self) -> str:
        if self.cur.kind != "id":
            raise PlcError(f"esperado um nome, encontrado {self.cur.value!r}", self.cur.line)
        n = str(self.cur.value)
        self.i += 1
        return n

    def program(self) -> StProgram:
        prog = StProgram()
        if self.at("PROGRAM", "FUNCTION_BLOCK"):
            self.i += 1
            self.name()
        while self.at("VAR", "VAR_GLOBAL", "VAR_INPUT", "VAR_OUTPUT", "VAR_TEMP"):
            self.i += 1
            if self.at("RETAIN", "CONSTANT"):
                self.i += 1
            while not self.at("END_VAR"):
                names = [self.name()]
                while self.at(","):
                    self.eat(",")
                    names.append(self.name())
                self.eat(":")
                vtype = self.name()
                if vtype not in VAR_TYPES | FB_TYPES:
                    raise PlcError(f"tipo {vtype} não suportado", self.cur.line)
                init = None
                if self.at(":="):
                    self.eat(":=")
                    init = self.expr()
                self.eat(";")
                prog.decls += [Decl(n, vtype, init) for n in names]
            self.eat("END_VAR")
        prog.body = self.stmts(("END_PROGRAM", "END_FUNCTION_BLOCK"))
        if self.at("END_PROGRAM", "END_FUNCTION_BLOCK"):
            self.i += 1
        if self.cur.kind != "eof":
            raise PlcError(f"sobrou texto: {self.cur.value!r}", self.cur.line)
        return prog

    def stmts(self, stop: tuple[str, ...]) -> list[Any]:
        out = []
        while self.cur.kind != "eof" and not self.at(*stop):
            if self.at(";"):
                self.i += 1
                continue
            out.append(self.stmt())
        return out

    def stmt(self) -> Any:
        line = self.cur.line
        if self.at("IF"):
            self.i += 1
            arms: list[Any] = [(self.expr(), None)]
            self.eat("THEN")
            arms[0] = (arms[0][0], self.stmts(("ELSIF", "ELSE", "END_IF")))
            other: list[Any] = []
            while self.at("ELSIF"):
                self.i += 1
                c = self.expr()
                self.eat("THEN")
                arms.append((c, self.stmts(("ELSIF", "ELSE", "END_IF"))))
            if self.at("ELSE"):
                self.i += 1
                other = self.stmts(("END_IF",))
            self.eat("END_IF")
            self._semi()
            return ("if", arms, other)
        if self.at("CASE"):
            self.i += 1
            sel = self.expr()
            self.eat("OF")
            cases: list[tuple[list[Any], list[Any]]] = []
            other = []
            while not self.at("END_CASE", "ELSE"):
                labels = [self.case_label()]
                while self.at(","):
                    self.eat(",")
                    labels.append(self.case_label())
                self.eat(":")
                body = []
                while not self.at("END_CASE", "ELSE") and not self._case_start():
                    if self.at(";"):
                        self.i += 1
                        continue
                    body.append(self.stmt())
                cases.append((labels, body))
            if self.at("ELSE"):
                self.i += 1
                other = self.stmts(("END_CASE",))
            self.eat("END_CASE")
            self._semi()
            return ("case", sel, cases, other)
        if self.at("FOR"):
            self.i += 1
            var = self.name()
            self.eat(":=")
            a = self.expr()
            self.eat("TO")
            b = self.expr()
            step = ("num", 1)
            if self.at("BY"):
                self.i += 1
                step = self.expr()
            self.eat("DO")
            body = self.stmts(("END_FOR",))
            self.eat("END_FOR")
            self._semi()
            return ("for", var, a, b, step, body)
        if self.at("WHILE"):
            self.i += 1
            c = self.expr()
            self.eat("DO")
            body = self.stmts(("END_WHILE",))
            self.eat("END_WHILE")
            self._semi()
            return ("while", c, body)
        if self.at("REPEAT"):
            self.i += 1
            body = self.stmts(("UNTIL",))
            self.eat("UNTIL")
            c = self.expr()
            self.eat("END_REPEAT")
            self._semi()
            return ("repeat", body, c)
        if self.at("EXIT"):
            self.i += 1
            self._semi()
            return ("exit",)
        if self.at("RETURN"):
            self.i += 1
            self._semi()
            return ("return",)
        target = self.name()
        if self.at("("):  # FB call
            self.eat("(")
            args: dict[str, Any] = {}
            while not self.at(")"):
                pname = self.name()
                if self.at("=>"):
                    raise PlcError("saídas com '=>' não são suportadas: leia FB.Q", line)
                self.eat(":=")
                args[pname] = self.expr()
                if not self.at(")"):
                    self.eat(",")
            self.eat(")")
            self._semi()
            return ("fbcall", target, args, line)
        member = None
        if self.at("."):
            self.eat(".")
            member = self.name()
        self.eat(":=")
        value = self.expr()
        self._semi()
        return ("assign", target, member, value, line)

    def _semi(self) -> None:
        if self.at(";"):
            self.i += 1

    def _case_start(self) -> bool:
        j = self.i
        if self.t[j].kind == "op" and self.t[j].value == "-":
            j += 1
        if self.t[j].kind not in ("num", "id"):
            return False
        j += 1
        while self.t[j].kind == "op" and self.t[j].value in (",", ".."):
            j += 2
        return self.t[j].kind == "op" and self.t[j].value == ":"

    def case_label(self) -> Any:
        a = self.expr()
        if self.at(".."):
            self.i += 1
            return ("range", a, self.expr())
        return a

    # expressions
    def expr(self) -> Any:
        return self._binary(0)

    _LEVELS: tuple[tuple[str, ...], ...] = (
        ("OR",),
        ("XOR",),
        ("AND", "&"),
        ("=", "<>"),
        ("<", "<=", ">", ">="),
        ("+", "-"),
        ("*", "/", "MOD"),
        ("**",),
    )

    def _binary(self, level: int) -> Any:
        if level == len(self._LEVELS):
            return self._unary()
        left = self._binary(level + 1)
        while self.at(*self._LEVELS[level]):
            op = str(self.cur.value)
            self.i += 1
            left = ("bin", "AND" if op == "&" else op, left, self._binary(level + 1))
        return left

    def _unary(self) -> Any:
        if self.at("NOT"):
            self.i += 1
            return ("not", self._unary())
        if self.at("-"):
            self.i += 1
            return ("neg", self._unary())
        if self.at("+"):
            self.i += 1
            return self._unary()
        return self._primary()

    def _primary(self) -> Any:
        tok = self.cur
        if tok.kind == "num":
            self.i += 1
            return ("num", tok.value)
        if tok.kind == "id":
            self.i += 1
            if tok.value in ("TRUE", "FALSE"):
                return ("num", tok.value == "TRUE")
            if self.at("("):
                self.eat("(")
                args = []
                while not self.at(")"):
                    args.append(self.expr())
                    if not self.at(")"):
                        self.eat(",")
                self.eat(")")
                if tok.value not in FUNCS:
                    raise PlcError(f"função {tok.value} não existe", tok.line)
                return ("call", tok.value, args)
            if self.at("."):
                self.eat(".")
                return ("member", tok.value, self.name())
            return ("var", tok.value)
        if self.at("("):
            self.eat("(")
            e = self.expr()
            self.eat(")")
            return e
        got = tok.value if tok.kind != "eof" else "fim do programa"
        raise PlcError(f"expressão inesperada: {got!r}", tok.line)


def parse_st(src: str) -> StProgram:
    return _Parser(lex(src)).program()


def parse_expr(src: str) -> Any:
    p = _Parser(lex(src))
    e = p.expr()
    if p.cur.kind != "eof":
        raise PlcError(f"expressão inválida: {src!r}")
    return e


# --------------------------------------------------------------------------- function blocks


class FB:
    kind = ""

    def __init__(self) -> None:
        self.inputs: dict[str, Any] = {}

    def outputs(self) -> dict[str, Any]:
        return {}

    def get(self, name: str) -> Any:
        if name in self.inputs:
            return self.inputs[name]
        out = self.outputs()
        if name not in out:
            raise PlcError(f"{self.kind} não tem o membro {name}")
        return out[name]

    def call(self, args: dict[str, Any], dt_ms: float) -> None:
        self.inputs.update(args)
        self.run(dt_ms)

    def run(self, dt_ms: float) -> None:
        raise NotImplementedError


class TON(FB):
    kind = "TON"

    def __init__(self) -> None:
        super().__init__()
        self.inputs = {"IN": False, "PT": 0.0}
        self.et = 0.0

    def run(self, dt: float) -> None:
        self.et = min(self.et + dt, self.inputs["PT"]) if self.inputs["IN"] else 0.0

    def outputs(self) -> dict[str, Any]:
        return {"Q": bool(self.inputs["IN"]) and self.et >= self.inputs["PT"], "ET": self.et}


class TOF(FB):
    kind = "TOF"

    def __init__(self) -> None:
        super().__init__()
        self.inputs = {"IN": False, "PT": 0.0}
        self.et = 0.0
        self.q = False

    def run(self, dt: float) -> None:
        if self.inputs["IN"]:
            self.q, self.et = True, 0.0
        elif self.q:
            self.et = min(self.et + dt, self.inputs["PT"])
            if self.et >= self.inputs["PT"]:
                self.q = False

    def outputs(self) -> dict[str, Any]:
        return {"Q": self.q, "ET": self.et}


class TP(FB):
    kind = "TP"

    def __init__(self) -> None:
        super().__init__()
        self.inputs = {"IN": False, "PT": 0.0}
        self.et = 0.0
        self.q = False
        self.prev = False

    def run(self, dt: float) -> None:
        rising = bool(self.inputs["IN"]) and not self.prev
        self.prev = bool(self.inputs["IN"])
        if rising and not self.q:
            self.q, self.et = True, 0.0
        elif self.q:
            self.et = min(self.et + dt, self.inputs["PT"])
            if self.et >= self.inputs["PT"]:
                self.q = False
        elif not self.inputs["IN"]:
            self.et = 0.0

    def outputs(self) -> dict[str, Any]:
        return {"Q": self.q, "ET": self.et}


class CTU(FB):
    kind = "CTU"

    def __init__(self) -> None:
        super().__init__()
        self.inputs = {"CU": False, "R": False, "PV": 0}
        self.cv = 0
        self.prev = False

    def run(self, dt: float) -> None:
        if self.inputs["R"]:
            self.cv = 0
        elif self.inputs["CU"] and not self.prev:
            self.cv += 1
        self.prev = bool(self.inputs["CU"])

    def outputs(self) -> dict[str, Any]:
        return {"Q": self.cv >= self.inputs["PV"], "CV": self.cv}


class CTD(FB):
    kind = "CTD"

    def __init__(self) -> None:
        super().__init__()
        self.inputs = {"CD": False, "LD": False, "PV": 0}
        self.cv = 0
        self.prev = False

    def run(self, dt: float) -> None:
        if self.inputs["LD"]:
            self.cv = int(self.inputs["PV"])
        elif self.inputs["CD"] and not self.prev:
            self.cv -= 1
        self.prev = bool(self.inputs["CD"])

    def outputs(self) -> dict[str, Any]:
        return {"Q": self.cv <= 0, "CV": self.cv}


class R_TRIG(FB):  # noqa: N801 (IEC name)
    kind = "R_TRIG"

    def __init__(self) -> None:
        super().__init__()
        self.inputs = {"CLK": False}
        self.q = False
        self.m = False

    def run(self, dt: float) -> None:
        clk = bool(self.inputs["CLK"])
        self.q = clk and not self.m
        self.m = clk

    def outputs(self) -> dict[str, Any]:
        return {"Q": self.q}


class F_TRIG(R_TRIG):  # noqa: N801
    kind = "F_TRIG"

    def run(self, dt: float) -> None:
        clk = bool(self.inputs["CLK"])
        self.q = self.m and not clk
        self.m = clk


class SR(FB):
    kind = "SR"

    def __init__(self) -> None:
        super().__init__()
        self.inputs = {"S1": False, "R": False}
        self.q = False

    def run(self, dt: float) -> None:
        self.q = bool(self.inputs["S1"]) or (self.q and not self.inputs["R"])

    def outputs(self) -> dict[str, Any]:
        return {"Q1": self.q}


class RS(FB):
    kind = "RS"

    def __init__(self) -> None:
        super().__init__()
        self.inputs = {"S": False, "R1": False}
        self.q = False

    def run(self, dt: float) -> None:
        self.q = not self.inputs["R1"] and (bool(self.inputs["S"]) or self.q)

    def outputs(self) -> dict[str, Any]:
        return {"Q1": self.q}


class PID(FB):
    """Positional PID, derivative on the measurement, integral clamped (anti-windup).

    Inputs: SP, PV, KP, TI (s, 0 = no integral), TD (s), OUT_MIN, OUT_MAX, ENABLE.
    Output: OUT (clamped). Same algorithm as the textbook discrete PID (Åström and Hägglund,
    *Advanced PID Control*, 2006, cap. 3).
    """

    kind = "PID"

    def __init__(self) -> None:
        super().__init__()
        self.inputs = {
            "SP": 0.0,
            "PV": 0.0,
            "KP": 1.0,
            "TI": 0.0,
            "TD": 0.0,
            "OUT_MIN": 0.0,
            "OUT_MAX": 100.0,
            "ENABLE": True,
        }
        self.i = 0.0
        self.prev_pv: float | None = None
        self.out = 0.0

    def run(self, dt_ms: float) -> None:
        g = self.inputs
        lo, hi = float(g["OUT_MIN"]), float(g["OUT_MAX"])
        if not g["ENABLE"]:
            self.i, self.prev_pv, self.out = 0.0, None, lo
            return
        dt = dt_ms / 1000
        e = float(g["SP"]) - float(g["PV"])
        kp, ti, td = float(g["KP"]), float(g["TI"]), float(g["TD"])
        d = 0.0
        if self.prev_pv is not None and dt > 0:
            d = -kp * td * (float(g["PV"]) - self.prev_pv) / dt
        self.prev_pv = float(g["PV"])
        p = kp * e
        if ti > 0:
            self.i += kp * e * dt / ti
            self.i = min(max(self.i, lo - p - d), hi - p - d)  # clamp: no windup
        self.out = min(max(p + self.i + d, lo), hi)

    def outputs(self) -> dict[str, Any]:
        return {"OUT": self.out, "I": self.i}


FB_CLASSES: dict[str, type[FB]] = {
    c.kind: c for c in (TON, TOF, TP, CTU, CTD, R_TRIG, F_TRIG, SR, RS, PID)
}


# -------------------------------------------------------------------------------- runtime


class _Exit(Exception):  # noqa: N818 (control flow)
    pass


class _ReturnSt(Exception):  # noqa: N818 (control flow)
    pass


class PlcRuntime:
    MAX_LOOP = 100_000

    def __init__(self, language: str, st: str = "", ladder: str | dict[str, Any] = "") -> None:
        self.language = language
        self.vars: dict[str, Any] = {}
        self.types: dict[str, str] = {}
        self.fbs: dict[str, FB] = {}
        for n in IO_BOOL_IN + IO_BOOL_OUT:
            self.vars[n], self.types[n] = False, "BOOL"
        for n in IO_REAL_IN + IO_REAL_OUT:
            self.vars[n], self.types[n] = 0.0, "REAL"
        self.dt = 0.0
        self.edge_mem: dict[tuple[int, int, int], bool] = {}
        if language == "st":
            self.prog = parse_st(st)
            for d in self.prog.decls:
                self._declare(d)
            self.rungs: list[dict[str, Any]] = []
        elif language == "ladder":
            self.prog = StProgram()
            data = json.loads(ladder) if isinstance(ladder, str) else ladder
            self.rungs = self._compile_ladder(data or {})
        else:
            raise PlcError(f"linguagem {language!r} desconhecida (use 'ladder' ou 'st')")

    # -- declarations
    def _declare(self, d: Decl) -> None:
        if d.name in self.vars or d.name in self.fbs:
            if d.name in IO_BOOL_IN + IO_BOOL_OUT + IO_REAL_IN + IO_REAL_OUT:
                return  # re-declaring the I/O image is allowed
            raise PlcError(f"variável {d.name} declarada duas vezes")
        if d.vtype in FB_TYPES:
            self.fbs[d.name] = FB_CLASSES[d.vtype]()
            return
        init = self._ev(d.init) if d.init is not None else None
        self.types[d.name] = d.vtype
        self.vars[d.name] = self._coerce(d.vtype, init if init is not None else 0)

    def _coerce(self, vtype: str, value: Any) -> Any:
        if vtype == "BOOL":
            return bool(value)
        if vtype in ("REAL", "LREAL", "TIME"):
            return float(value)
        return int(value)

    def _auto(self, name: str) -> None:
        """Ladder coils and contacts may use names never declared: they become BOOL markers."""
        if name not in self.vars and name not in self.fbs:
            self.vars[name], self.types[name] = False, "BOOL"

    # -- scan
    def scan(self, inputs: dict[str, Any], dt_s: float) -> dict[str, Any]:
        self.dt = dt_s * 1000
        for k, v in inputs.items():
            self.vars[k] = v
        if self.language == "st":
            with contextlib.suppress(_ReturnSt):
                self._run(self.prog.body)
        else:
            self._scan_ladder()
        self.vars["AQ0"] = min(max(float(self.vars["AQ0"]), 0.0), 10.0)
        return {n: self.vars[n] for n in IO_BOOL_OUT + IO_REAL_OUT}

    def snapshot(self) -> dict[str, float]:
        out = {k: float(v) for k, v in self.vars.items()}
        for name, fb in self.fbs.items():
            for k, v in fb.outputs().items():
                out[f"{name}.{k}"] = float(v)
        return out

    # -- structured text
    def _run(self, body: list[Any]) -> None:
        for s in body:
            self._stmt(s)

    def _stmt(self, s: Any) -> None:
        k = s[0]
        if k == "assign":
            _, target, member, value, line = s
            v = self._ev(value)
            if member is not None:
                fb = self.fbs.get(target)
                if fb is None:
                    raise PlcError(f"{target} não é bloco de função", line)
                fb.inputs[member] = v
                return
            if target not in self.vars:
                raise PlcError(f"variável {target} não declarada", line)
            self.vars[target] = self._coerce(self.types[target], v)
        elif k == "fbcall":
            _, name, args, line = s
            fb = self.fbs.get(name)
            if fb is None:
                raise PlcError(f"{name} não é bloco de função declarado", line)
            fb.call({a: self._ev(e) for a, e in args.items()}, self.dt)
        elif k == "if":
            for cond, body in s[1]:
                if self._ev(cond):
                    self._run(body)
                    return
            self._run(s[2])
        elif k == "case":
            v = self._ev(s[1])
            for labels, body in s[2]:
                for lab in labels:
                    hit = (
                        self._ev(lab[1]) <= v <= self._ev(lab[2])
                        if lab[0] == "range"
                        else self._ev(lab) == v
                    )
                    if hit:
                        self._run(body)
                        return
            self._run(s[3])
        elif k == "for":
            _, var, a, b, step, body = s
            st = self._ev(step)
            self.vars.setdefault(var, 0)
            self.types.setdefault(var, "INT")
            self.vars[var] = self._ev(a)
            end = self._ev(b)
            n = 0
            try:
                while (self.vars[var] <= end) if st >= 0 else (self.vars[var] >= end):
                    self._run(body)
                    self.vars[var] += st
                    n += 1
                    if n > self.MAX_LOOP:
                        raise PlcError("laço FOR sem fim no ciclo de varredura")
            except _Exit:
                pass
        elif k == "while":
            n = 0
            try:
                while self._ev(s[1]):
                    self._run(s[2])
                    n += 1
                    if n > self.MAX_LOOP:
                        raise PlcError("laço WHILE travaria o ciclo de varredura (watchdog)")
            except _Exit:
                pass
        elif k == "repeat":
            n = 0
            try:
                while True:
                    self._run(s[1])
                    n += 1
                    if self._ev(s[2]):
                        break
                    if n > self.MAX_LOOP:
                        raise PlcError("laço REPEAT travaria o ciclo de varredura (watchdog)")
            except _Exit:
                pass
        elif k == "exit":
            raise _Exit
        elif k == "return":
            raise _ReturnSt

    def _ev(self, e: Any) -> Any:
        k = e[0]
        if k == "num":
            return e[1]
        if k == "var":
            if e[1] in self.vars:
                return self.vars[e[1]]
            if e[1] in self.fbs:
                raise PlcError(f"{e[1]} é bloco de função: use {e[1]}.Q")
            raise PlcError(f"variável {e[1]} não declarada")
        if k == "member":
            fb = self.fbs.get(e[1])
            if fb is None:
                raise PlcError(f"{e[1]} não é bloco de função")
            return fb.get(e[2])
        if k == "not":
            v = self._ev(e[1])
            return (not v) if isinstance(v, bool) else ~int(v)
        if k == "neg":
            return -self._ev(e[1])
        if k == "bin":
            op, a, b = e[1], self._ev(e[2]), self._ev(e[3])
            if op == "AND":
                return a and b if isinstance(a, bool) else int(a) & int(b)
            if op == "OR":
                return a or b if isinstance(a, bool) else int(a) | int(b)
            if op == "XOR":
                return a != b if isinstance(a, bool) else int(a) ^ int(b)
            if op == "=":
                return a == b
            if op == "<>":
                return a != b
            if op == "<":
                return a < b
            if op == "<=":
                return a <= b
            if op == ">":
                return a > b
            if op == ">=":
                return a >= b
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "*":
                return a * b
            if op == "/":
                if b == 0:
                    raise PlcError("divisão por zero")
                return int(a / b) if isinstance(a, int) and isinstance(b, int) else a / b
            if op == "MOD":
                return int(math.fmod(a, b))
            if op == "**":
                return float(a) ** float(b)
        if k == "call":
            name = e[1]
            args = [self._ev(a) for a in e[2]]
            return _call(name, args)
        raise PlcError(f"expressão não suportada: {k}")

    # -- ladder
    def _compile_ladder(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        rungs = data.get("rungs", [])
        if not isinstance(rungs, list):
            raise PlcError("ladder sem lista de degraus ('rungs')")
        for name, vtype in (data.get("vars") or {}).items():
            self._declare(Decl(str(name).upper(), str(vtype).upper()))
        out = []
        for r_i, rung in enumerate(rungs, start=1):
            branches = []
            for branch in rung.get("branches", []):
                els: list[Any] = []
                for el in branch:
                    t = str(el.get("type", "")).upper()
                    if t in ("NO", "NC", "P", "N"):
                        var = str(el.get("var", "")).upper()
                        if not var:
                            raise PlcError(f"degrau {r_i}: contato sem variável")
                        self._auto(var)
                        els.append((t, var))
                    elif t == "CMP":
                        els.append(("CMP", parse_expr(str(el.get("expr", "")))))
                    elif t in ("TON", "TOF", "TP"):
                        name = str(el.get("name", "")).upper()
                        self.fbs.setdefault(name, FB_CLASSES[t]())
                        els.append((t, name, parse_expr(str(el.get("pt", "T#1s")))))
                    elif t in ("CTU", "CTD"):
                        name = str(el.get("name", "")).upper()
                        self.fbs.setdefault(name, FB_CLASSES[t]())
                        reset = str(el.get("reset", "")).upper() or None
                        if reset:
                            self._auto(reset)
                        els.append((t, name, int(el.get("pv", 1)), reset))
                    else:
                        raise PlcError(f"degrau {r_i}: elemento {t or '?'} desconhecido")
                branches.append(els)
            coils = []
            for c in rung.get("coils", []):
                t = str(c.get("type", "coil")).lower()
                if t == "move":
                    dst = str(c.get("dst", "")).upper()
                    if dst not in self.vars:
                        self.vars[dst], self.types[dst] = 0.0, "REAL"
                    coils.append(("move", dst, parse_expr(str(c.get("src", "0")))))
                    continue
                if t not in ("coil", "ncoil", "set", "reset"):
                    raise PlcError(f"degrau {r_i}: bobina {t} desconhecida")
                var = str(c.get("var", "")).upper()
                self._auto(var)
                coils.append((t, var, None))
            out.append({"branches": branches, "coils": coils})
        return out

    def _scan_ladder(self) -> None:
        for r_i, rung in enumerate(self.rungs):
            result = False
            for b_i, branch in enumerate(rung["branches"]):
                v = True
                for e_i, el in enumerate(branch):
                    t = el[0]
                    if t == "NO":
                        v = v and bool(self.vars[el[1]])
                    elif t == "NC":
                        v = v and not self.vars[el[1]]
                    elif t in ("P", "N"):
                        key = (r_i, b_i, e_i)
                        now = bool(self.vars[el[1]])
                        before = self.edge_mem.get(key, now)
                        self.edge_mem[key] = now
                        v = v and (now and not before if t == "P" else before and not now)
                    elif t == "CMP":
                        v = v and bool(self._ev(el[1]))
                    elif t in ("TON", "TOF", "TP"):
                        fb = self.fbs[el[1]]
                        fb.call({"IN": v, "PT": self._ev(el[2])}, self.dt)
                        v = bool(fb.get("Q"))
                    elif t in ("CTU", "CTD"):
                        fb = self.fbs[el[1]]
                        reset = bool(self.vars[el[3]]) if el[3] else False
                        args = (
                            {"CU": v, "R": reset, "PV": el[2]}
                            if t == "CTU"
                            else {"CD": v, "LD": reset, "PV": el[2]}
                        )
                        fb.call(args, self.dt)
                        v = bool(fb.get("Q"))
                result = result or v
            for t, var, src in rung["coils"]:
                if t == "coil":
                    self.vars[var] = result
                elif t == "ncoil":
                    self.vars[var] = not result
                elif t == "set" and result:
                    self.vars[var] = True
                elif t == "reset" and result:
                    self.vars[var] = False
                elif t == "move" and result:
                    self.vars[var] = self._coerce(self.types.get(var, "REAL"), self._ev(src))


def _call(name: str, a: list[Any]) -> Any:
    try:
        if name == "ABS":
            return abs(a[0])
        if name == "SQRT":
            return math.sqrt(a[0])
        if name == "MIN":
            return min(a)
        if name == "MAX":
            return max(a)
        if name == "LIMIT":
            return min(max(a[1], a[0]), a[2])
        if name == "SEL":
            return a[2] if a[0] else a[1]
        if name in ("TRUNC", "REAL_TO_INT", "TO_INT", "REAL_TO_DINT"):
            return int(a[0])
        if name == "ROUND":
            return round(a[0])
        if name in ("INT_TO_REAL", "TO_REAL", "DINT_TO_REAL", "TIME_TO_REAL"):
            return float(a[0])
        if name == "REAL_TO_TIME":
            return float(a[0])
        if name == "BOOL_TO_INT":
            return 1 if a[0] else 0
        if name == "MOVE":
            return a[0]
        if name == "EXP":
            return math.exp(a[0])
        if name == "LN":
            return math.log(a[0])
        if name == "LOG":
            return math.log10(a[0])
        if name == "SIN":
            return math.sin(a[0])
        if name == "COS":
            return math.cos(a[0])
        if name == "TAN":
            return math.tan(a[0])
    except (IndexError, ValueError) as exc:
        raise PlcError(f"{name}: argumentos inválidos ({exc})") from exc
    raise PlcError(f"função {name} não existe")
