"""A C subset for Arduino-style programs: lexer and parser into a small AST.

Covers what classroom sketches use: global and local variables (``int``, ``long``,
``unsigned long``, ``float``, ``double``, ``bool``, ``byte``, ``char``, ``const``), one-dimensional
arrays, functions with parameters, ``if``/``else``, ``while``, ``do``, ``for``, ``switch``,
``break``/``continue``/``return``, the full C expression grammar (assignment operators, ternary,
logical, bitwise, increments, casts), ``#define`` constants, and member calls such as
``Serial.println``. Pointers, structs and classes are not supported: the error says so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

TYPES = {
    "void",
    "int",
    "long",
    "short",
    "unsigned",
    "signed",
    "float",
    "double",
    "bool",
    "boolean",
    "byte",
    "char",
    "word",
    "size_t",
    "uint8_t",
    "int8_t",
    "uint16_t",
    "int16_t",
    "uint32_t",
    "int32_t",
    "String",
    # library objects of the digital sensors (cosim/libraries.py)
    "DHT",
    "OneWire",
    "DallasTemperature",
    "Adafruit_BME280",
}
OBJECT_TYPES = {"DHT", "OneWire", "DallasTemperature", "Adafruit_BME280"}
QUALIFIERS = {"const", "volatile", "static"}


class CError(ValueError):
    def __init__(self, message: str, line: int | None = None):
        super().__init__(f"linha {line}: {message}" if line else message)
        self.line = line


@dataclass
class Tok:
    kind: str  # num, id, str, char, op, eof
    value: Any
    line: int


_TOKEN = re.compile(
    r"""
    (?P<ws>[ \t\r]+)
  | (?P<nl>\n)
  | (?P<lc>//[^\n]*)
  | (?P<bc>/\*.*?\*/)
  | (?P<pp>\#[^\n]*)
  | (?P<num>0[xX][0-9a-fA-F]+[uUlL]*|0[bB][01]+[uUlL]*|(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?[fFuUlL]*)
  | (?P<id>[A-Za-z_]\w*)
  | (?P<str>"([^"\\\n]|\\.)*")
  | (?P<chr>'([^'\\\n]|\\.)')
  | (?P<op><<=|>>=|\+\+|--|&&|\|\||==|!=|<=|>=|<<|>>|\+=|-=|\*=|/=|%=|&=|\|=|\^=|->|::
           |[-+*/%<>=!&|^~?:;,.(){}\[\]])
    """,
    re.VERBOSE | re.DOTALL,
)
_ESC = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "\\": "\\", '"': '"', "'": "'"}


def _num(text: str) -> int | float:
    t = text.rstrip("uUlL")
    if t.lower().startswith("0x"):
        return int(t, 16)
    if t.lower().startswith("0b"):
        return int(t[2:], 2)
    if any(c in t for c in ".eE") or t.endswith(("f", "F")):
        return float(t.rstrip("fF"))
    return int(t)


def _unescape(s: str) -> str:
    return re.sub(r"\\(.)", lambda m: _ESC.get(m.group(1), m.group(1)), s)


def lex(source: str) -> list[Tok]:
    defines: dict[str, list[Tok]] = {}
    out: list[Tok] = []
    line = 1
    pos = 0
    while pos < len(source):
        m = _TOKEN.match(source, pos)
        if m is None:
            raise CError(f"caractere inesperado {source[pos]!r}", line)
        kind = m.lastgroup or ""
        text = m.group(kind)
        pos = m.end()
        if kind == "nl":
            line += 1
        elif kind in ("ws", "lc"):
            pass
        elif kind == "bc":
            line += text.count("\n")
        elif kind == "pp":
            d = re.match(r"#\s*define\s+([A-Za-z_]\w*)\s*(.*)", text)
            if d and "(" not in d.group(1):
                body = re.sub(r"//.*", "", d.group(2)).strip()
                defines[d.group(1)] = [t for t in lex(body)[:-1]] if body else []
            elif d is None and not re.match(
                r"#\s*(include|pragma|ifndef|ifdef|endif|if|else)", text
            ):
                raise CError(f"diretiva não suportada: {text.strip()}", line)
        elif kind == "num":
            out.append(Tok("num", _num(text), line))
        elif kind == "id":
            if text in defines:
                out.extend(Tok(t.kind, t.value, line) for t in defines[text])
            else:
                out.append(Tok("id", text, line))
        elif kind == "str":
            out.append(Tok("str", _unescape(text[1:-1]), line))
        elif kind == "chr":
            out.append(Tok("num", ord(_unescape(text[1:-1])), line))
        else:
            out.append(Tok("op", text, line))
    out.append(Tok("eof", None, line))
    return out


# ------------------------------------------------------------------------------------- AST
# Expressions are tuples (fast to evaluate): ("num", v) ("str", s) ("var", name)
# ("bin", op, a, b) ("un", op, a) ("assign", op, target, value) ("incdec", op, prefix, target)
# ("cond", c, a, b) ("call", name, args) ("member", obj, name, args) ("index", name, idx)
# ("cast", ctype, a)


@dataclass
class CType:
    base: str  # int, long, float, bool, char, byte, unsigned long, String...
    const: bool = False

    @property
    def is_float(self) -> bool:
        return self.base in ("float", "double")


@dataclass
class VarDecl:
    ctype: CType
    name: str
    size: Any = None  # array length expression, or "auto" for int a[] = {...}
    init: Any = None  # expression or list of expressions (array)
    line: int = 0


@dataclass
class Func:
    ret: CType
    name: str
    params: list[tuple[CType, str]]
    body: list[Any]
    line: int = 0


@dataclass
class Program:
    globals: list[VarDecl] = field(default_factory=list)
    funcs: dict[str, Func] = field(default_factory=dict)


# statements: ("expr", e, line) ("decl", [VarDecl]) ("if", c, then, else) ("while", c, body)
# ("do", body, c) ("for", init, c, step, body) ("break",) ("continue",) ("return", e)
# ("block", [stmts]) ("switch", e, [(values|None, [stmts])])


class Parser:
    def __init__(self, toks: list[Tok]):
        self.t = toks
        self.i = 0

    # -- helpers
    @property
    def cur(self) -> Tok:
        return self.t[self.i]

    def peek(self, k: int = 1) -> Tok:
        return self.t[min(self.i + k, len(self.t) - 1)]

    def at(self, *ops: str) -> bool:
        return self.cur.kind == "op" and self.cur.value in ops

    def at_id(self, *names: str) -> bool:
        return self.cur.kind == "id" and self.cur.value in names

    def eat(self, op: str) -> Tok:
        if not self.at(op):
            got = self.cur.value if self.cur.kind != "eof" else "fim do programa"
            raise CError(f"esperado '{op}', encontrado {got!r}", self.cur.line)
        tok = self.cur
        self.i += 1
        return tok

    def ident(self) -> str:
        if self.cur.kind != "id":
            raise CError(f"esperado um nome, encontrado {self.cur.value!r}", self.cur.line)
        name = str(self.cur.value)
        self.i += 1
        return name

    def is_type_start(self) -> bool:
        return self.cur.kind == "id" and (self.cur.value in TYPES or self.cur.value in QUALIFIERS)

    def ctype(self) -> CType:
        const = False
        words: list[str] = []
        while self.cur.kind == "id" and (self.cur.value in TYPES or self.cur.value in QUALIFIERS):
            if self.cur.value == "const":
                const = True
            elif self.cur.value not in QUALIFIERS:
                words.append(str(self.cur.value))
            self.i += 1
        if self.at("*", "&"):
            raise CError("ponteiros e referências não são suportados", self.cur.line)
        base = " ".join(words) or "int"
        if base in ("unsigned", "signed"):
            base = "unsigned int" if base == "unsigned" else "int"
        return CType(base, const)

    # -- program
    def program(self) -> Program:
        prog = Program()
        while self.cur.kind != "eof":
            if self.at_id("struct", "class", "union", "enum", "typedef", "template"):
                raise CError(f"'{self.cur.value}' não é suportado", self.cur.line)
            line = self.cur.line
            ct = self.ctype()
            name = self.ident()
            if self.at("(") and ct.base not in OBJECT_TYPES:
                prog.funcs[name] = self.func_rest(ct, name, line)
            else:
                prog.globals += self.decl_rest(ct, name, line)
        return prog

    def func_rest(self, ret: CType, name: str, line: int) -> Func:
        self.eat("(")
        params: list[tuple[CType, str]] = []
        if self.at_id("void") and self.peek().kind == "op" and self.peek().value == ")":
            self.i += 1
        while not self.at(")"):
            pt = self.ctype()
            params.append((pt, self.ident()))
            if self.at("["):
                raise CError("parâmetros vetoriais não são suportados", self.cur.line)
            if not self.at(")"):
                self.eat(",")
        self.eat(")")
        if self.at(";"):  # prototype
            self.eat(";")
            return Func(ret, name, params, [], line)
        return Func(ret, name, params, self.block(), line)

    def decl_rest(self, ct: CType, name: str, line: int) -> list[VarDecl]:
        out: list[VarDecl] = []
        while True:
            d = VarDecl(ct, name, line=line)
            if self.at("["):
                self.eat("[")
                d.size = "auto" if self.at("]") else self.expr()
                self.eat("]")
            if ct.base in OBJECT_TYPES:
                d.init = ("ctor", ct.base, self.ctor_args() if self.at("(") else [], line)
                out.append(d)
                if self.at(","):
                    self.eat(",")
                    name = self.ident()
                    continue
                self.eat(";")
                return out
            if self.at("("):
                raise CError("objetos (construtores) não são suportados", self.cur.line)
            if self.at("="):
                self.eat("=")
                if self.at("{"):
                    self.eat("{")
                    items = []
                    while not self.at("}"):
                        items.append(self.assign())
                        if not self.at("}"):
                            self.eat(",")
                    self.eat("}")
                    d.init = items
                else:
                    d.init = self.assign()
            out.append(d)
            if self.at(","):
                self.eat(",")
                name = self.ident()
                continue
            self.eat(";")
            return out

    def ctor_args(self) -> list[Any]:
        """Constructor arguments of a library object; ``&name`` passes another object."""
        self.eat("(")
        args: list[Any] = []
        while not self.at(")"):
            if self.at("&"):
                self.eat("&")
                args.append(("var", self.ident()))
            else:
                args.append(self.assign())
            if not self.at(")"):
                self.eat(",")
        self.eat(")")
        return args

    # -- statements
    def block(self) -> list[Any]:
        self.eat("{")
        body = []
        while not self.at("}"):
            if self.cur.kind == "eof":
                raise CError("falta '}'", self.cur.line)
            body.append(self.stmt())
        self.eat("}")
        return body

    def stmt(self) -> Any:
        line = self.cur.line
        if self.at("{"):
            return ("block", self.block())
        if self.at(";"):
            self.eat(";")
            return ("block", [])
        if self.is_type_start() and not (self.cur.value == "String" and self.peek().kind == "op"):
            ct = self.ctype()
            return ("decl", self.decl_rest(ct, self.ident(), line))
        if self.cur.kind == "id":
            kw = self.cur.value
            if kw == "if":
                self.i += 1
                self.eat("(")
                c = self.expr()
                self.eat(")")
                then = self.stmt()
                other = None
                if self.at_id("else"):
                    self.i += 1
                    other = self.stmt()
                return ("if", c, then, other)
            if kw == "while":
                self.i += 1
                self.eat("(")
                c = self.expr()
                self.eat(")")
                return ("while", c, self.stmt())
            if kw == "do":
                self.i += 1
                body = self.stmt()
                if not self.at_id("while"):
                    raise CError("esperado 'while' depois do 'do'", self.cur.line)
                self.i += 1
                self.eat("(")
                c = self.expr()
                self.eat(")")
                self.eat(";")
                return ("do", body, c)
            if kw == "for":
                self.i += 1
                self.eat("(")
                init: Any = None
                if not self.at(";"):
                    if self.is_type_start():
                        ct = self.ctype()
                        init = ("decl", self.decl_rest(ct, self.ident(), line))
                    else:
                        init = ("expr", self.expr(), line)
                        self.eat(";")
                else:
                    self.eat(";")
                c = None if self.at(";") else self.expr()
                self.eat(";")
                step = None if self.at(")") else self.expr()
                self.eat(")")
                return ("for", init, c, step, self.stmt())
            if kw == "switch":
                self.i += 1
                self.eat("(")
                e = self.expr()
                self.eat(")")
                self.eat("{")
                cases: list[tuple[list[Any] | None, list[Any]]] = []
                while not self.at("}"):
                    if self.at_id("case"):
                        self.i += 1
                        v = self.expr()
                        self.eat(":")
                        cases.append(([v], []))
                    elif self.at_id("default"):
                        self.i += 1
                        self.eat(":")
                        cases.append((None, []))
                    else:
                        if not cases:
                            raise CError("comando fora de 'case'", self.cur.line)
                        cases[-1][1].append(self.stmt())
                self.eat("}")
                return ("switch", e, cases)
            if kw == "break":
                self.i += 1
                self.eat(";")
                return ("break",)
            if kw == "continue":
                self.i += 1
                self.eat(";")
                return ("continue",)
            if kw == "return":
                self.i += 1
                e = None if self.at(";") else self.expr()
                self.eat(";")
                return ("return", e)
            if kw == "goto":
                raise CError("'goto' não é suportado", line)
        e = self.expr()
        self.eat(";")
        return ("expr", e, line)

    # -- expressions (precedence climbing)
    def expr(self) -> Any:
        e = self.assign()
        while self.at(","):
            self.eat(",")
            e = ("comma", e, self.assign())
        return e

    _ASSIGN = ("=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>=")

    def assign(self) -> Any:
        left = self.cond()
        if self.at(*self._ASSIGN):
            op = self.eat(self.cur.value).value
            if left[0] not in ("var", "index"):
                raise CError("atribuição a algo que não é variável", self.cur.line)
            return ("assign", op, left, self.assign())
        return left

    def cond(self) -> Any:
        c = self.binary(0)
        if self.at("?"):
            self.eat("?")
            a = self.assign()
            self.eat(":")
            return ("cond", c, a, self.assign())
        return c

    _LEVELS = (
        ("||",),
        ("&&",),
        ("|",),
        ("^",),
        ("&",),
        ("==", "!="),
        ("<", "<=", ">", ">="),
        ("<<", ">>"),
        ("+", "-"),
        ("*", "/", "%"),
    )

    def binary(self, level: int) -> Any:
        if level == len(self._LEVELS):
            return self.unary()
        left = self.binary(level + 1)
        while self.at(*self._LEVELS[level]):
            op = self.eat(self.cur.value).value
            left = ("bin", op, left, self.binary(level + 1))
        return left

    def unary(self) -> Any:
        if self.at("!", "-", "+", "~"):
            op = self.eat(self.cur.value).value
            return ("un", op, self.unary())
        if self.at("++", "--"):
            op = self.eat(self.cur.value).value
            return ("incdec", op, True, self.unary())
        if self.at("(") and self.peek().kind == "id" and self.peek().value in TYPES:
            j = self.i + 1
            while self.t[j].kind == "id" and self.t[j].value in TYPES:
                j += 1
            if self.t[j].kind == "op" and self.t[j].value == ")":
                self.eat("(")
                ct = self.ctype()
                self.eat(")")
                return ("cast", ct.base, self.unary())
        return self.postfix()

    def args(self) -> list[Any]:
        self.eat("(")
        out = []
        while not self.at(")"):
            out.append(self.assign())
            if not self.at(")"):
                self.eat(",")
        self.eat(")")
        return out

    def postfix(self) -> Any:
        e = self.primary()
        while True:
            if self.at("("):
                if e[0] != "var":
                    raise CError("chamada inválida", self.cur.line)
                e = ("call", e[1], self.args(), self.cur.line)
            elif self.at("["):
                self.eat("[")
                idx = self.expr()
                self.eat("]")
                if e[0] != "var":
                    raise CError("só vetores de uma dimensão são suportados", self.cur.line)
                e = ("index", e[1], idx)
            elif self.at("."):
                self.eat(".")
                name = self.ident()
                if e[0] != "var":
                    raise CError("membro inválido", self.cur.line)
                args = self.args() if self.at("(") else None
                e = ("member", e[1], name, args)
            elif self.at("++", "--"):
                op = self.eat(self.cur.value).value
                e = ("incdec", op, False, e)
            elif self.at("->", "::"):
                raise CError(f"'{self.cur.value}' não é suportado", self.cur.line)
            else:
                return e

    def primary(self) -> Any:
        tok = self.cur
        if tok.kind == "num":
            self.i += 1
            return ("num", tok.value)
        if tok.kind == "str":
            self.i += 1
            s = str(tok.value)
            while self.cur.kind == "str":  # "a" "b" concatenation
                s += str(self.cur.value)
                self.i += 1
            return ("str", s)
        if tok.kind == "id":
            self.i += 1
            if tok.value in ("true", "false"):
                return ("num", 1 if tok.value == "true" else 0)
            return ("var", tok.value)
        if self.at("("):
            self.eat("(")
            e = self.expr()
            self.eat(")")
            return e
        got = tok.value if tok.kind != "eof" else "fim do programa"
        raise CError(f"expressão inesperada: {got!r}", tok.line)


def parse(source: str) -> Program:
    prog = Parser(lex(source)).program()
    missing = [f for f in ("setup", "loop") if f not in prog.funcs]
    if missing:
        raise CError(f"o programa precisa da(s) função(ões) {', '.join(m + '()' for m in missing)}")
    return prog
