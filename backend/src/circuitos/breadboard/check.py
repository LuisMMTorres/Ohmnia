"""Check an assembly against the schematic: missing, extra and swapped connections.

Both sides are reduced to the same thing: a partition of the checked legs into nets. On the
breadboard, a leg belongs to the strip of its hole, strips joined by jumpers are one net. A leg
pair that the schematic joins but the board does not is a missing connection; a board net that
joins legs of different schematic nets is an extra connection (a short). Two legs of the same
part that are each where the other should be are reported once, as swapped, before the rest of
the comparison.
"""

from __future__ import annotations

from itertools import combinations, pairwise
from typing import Literal

from pydantic import BaseModel, Field

from circuitos.breadboard import board
from circuitos.breadboard.layout import Breadboard
from circuitos.breadboard.packages import package
from circuitos.breadboard.reference import ALIM, Reference, key

IssueKind = Literal[
    "faltando",
    "sobrando",
    "trocada",
    "nao_montado",
    "furo",
    "fora_do_esquematico",
    "sem_pinagem",
    "aviso",
]
ERRORS = {"faltando", "sobrando", "trocada", "nao_montado", "furo", "fora_do_esquematico"}
_SYMMETRIC = {"axial-r", "axial-r-1w", "axial-l", "radial-cer", "radial-film", "radial-l", "carga"}


class Issue(BaseModel):
    kind: IssueKind
    message: str
    refs: list[str] = Field(default_factory=list)
    holes: list[str] = Field(default_factory=list)


class CheckReport(BaseModel):
    ok: bool
    issues: list[Issue]
    checked_parts: int
    checked_legs: int
    summary: str


class _UF:
    def __init__(self) -> None:
        self.p: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        self.p[self.find(a)] = self.find(b)


def board_nets(bb: Breadboard) -> _UF:
    uf = _UF()
    for w in bb.wires:
        uf.union(board.strip(w.a, bb.rails_split), board.strip(w.b, bb.rails_split))
    return uf


def _holes_in_use(bb: Breadboard) -> list[Issue]:
    used: dict[str, list[str]] = {}
    for p in bb.parts:
        for pin, h in p.legs.items():
            used.setdefault(h, []).append(f"{p.ref} pino {pin}")
    for w in bb.wires:
        for h in (w.a, w.b):
            used.setdefault(h, []).append("fio")
    return [
        Issue(
            kind="furo",
            message=f"Furo {h} com mais de uma perna ou fio: {', '.join(who)}.",
            holes=[h],
        )
        for h, who in sorted(used.items())
        if len(who) > 1
    ]


def check(ref: Reference, bb: Breadboard) -> CheckReport:
    issues = _holes_in_use(bb)
    uf = board_nets(bb)
    leg_hole: dict[str, str] = {}
    checked: set[str] = set()
    for p in bb.parts:
        r = ref.parts.get(p.ref)
        if r is None:
            issues.append(
                Issue(
                    kind="fora_do_esquematico",
                    refs=[p.ref],
                    message=f"{p.ref} está na protoboard mas não no esquemático.",
                    holes=list(p.legs.values()),
                )
            )
            continue
        if not r.checkable:
            if r.origin == "sem_pinagem":
                issues.append(Issue(kind="sem_pinagem", refs=[p.ref], message=" ".join(r.notes)))
            continue
        if p.package != r.package:
            issues.append(
                Issue(
                    kind="aviso",
                    refs=[p.ref],
                    message=(
                        f"{p.ref} está montado como {p.package}, mas a peça usa {r.package}: "
                        "as pernas não foram conferidas."
                    ),
                )
            )
            continue
        checked.add(p.ref)
        for pin, h in p.legs.items():
            leg_hole[key(p.ref, pin)] = h
        if package(p.package).style == "board":
            # pins of one function on a board (its GND pins) are joined on the board itself
            by_role: dict[str, list[str]] = {}
            for pin, h in p.legs.items():
                if pin in r.pinmap:
                    by_role.setdefault(r.pinmap[pin], []).append(board.strip(h, bb.rails_split))
            for strips in by_role.values():
                for a, b in pairwise(strips):
                    uf.union(a, b)
        net_members = ref.members()
        missing = [
            pin
            for pin in r.pinmap
            if pin not in p.legs and len(net_members.get(ref.nets.get(key(p.ref, pin), ""), [])) > 1
        ]
        if missing:
            issues.append(
                Issue(
                    kind="faltando",
                    refs=[p.ref],
                    message=(f"{p.ref}: perna(s) {', '.join(missing)} fora da placa."),
                )
            )
        # a hint next to the "extra connection" error: two legs of one part in one strip
        by_strip: dict[str, list[str]] = {}
        for pin, h in p.legs.items():
            by_strip.setdefault(board.strip(h, bb.rails_split), []).append(pin)
        for s, pins in by_strip.items():
            if len({ref.nets.get(key(p.ref, pin)) for pin in pins}) > 1:
                issues.append(
                    Issue(
                        kind="aviso",
                        refs=[p.ref],
                        holes=[p.legs[pin] for pin in pins],
                        message=f"{p.ref}: pernas {', '.join(pins)} na mesma tira ({s}), em curto.",
                    )
                )
    for refd, r in ref.parts.items():
        if r.checkable and bb.part(refd) is None:
            text = (
                "Falta ligar a fonte simétrica dos integrados (ALIM: +, − e 0 V)."
                if refd == ALIM
                else f"{refd} ({r.title or r.kind}) não está na protoboard."
            )
            issues.append(Issue(kind="nao_montado", refs=[refd], message=text))

    legs = [k for k in leg_hole if k in ref.nets]
    want = {k: ref.nets[k] for k in legs}
    have = {k: uf.find(board.strip(leg_hole[k], bb.rails_split)) for k in legs}

    def cost(k: str) -> int:
        a = {j for j in legs if j != k and want[j] == want[k]}
        b = {j for j in legs if j != k and have[j] == have[k]}
        return len(a ^ b)

    for refd in sorted(checked):
        r = ref.parts[refd]
        mine = [k for k in legs if k.split(":", 1)[0] == refd]
        for x, y in combinations(mine, 2):
            if want[x] == want[y]:
                continue
            before = cost(x) + cost(y)
            if before == 0:
                continue
            want[x], want[y] = want[y], want[x]
            if cost(x) + cost(y) == 0:
                if r.package not in _SYMMETRIC:
                    px, py = x.split(":", 1)[1], y.split(":", 1)[1]
                    issues.append(
                        Issue(
                            kind="trocada",
                            refs=[refd],
                            holes=[leg_hole[x], leg_hole[y]],
                            message=(
                                f"{ref.leg_label(x)} e {ref.leg_label(y)} invertidos "
                                f"(pernas em {leg_hole[x]} e {leg_hole[y]}). "
                                f"Pino {px} está onde deveria estar o pino {py}."
                            ),
                        )
                    )
            else:
                want[x], want[y] = want[y], want[x]

    by_want: dict[str, list[str]] = {}
    by_have: dict[str, list[str]] = {}
    for k in legs:
        by_want.setdefault(want[k], []).append(k)
        by_have.setdefault(have[k], []).append(k)
    for net, members in sorted(by_want.items()):
        groups: dict[str, list[str]] = {}
        for k in members:
            groups.setdefault(have[k], []).append(k)
        if len(groups) > 1:
            parts = [", ".join(ref.leg_label(k) for k in g) for g in groups.values()]
            issues.append(
                Issue(
                    kind="faltando",
                    refs=sorted({k.split(":")[0] for k in members}),
                    holes=[leg_hole[k] for k in members],
                    message=(
                        f"Falta ligação no nó {ref.net_labels.get(net, net)}: "
                        + " ⟷ ".join(f"[{t}]" for t in parts)
                        + " devem estar ligados."
                    ),
                )
            )
    for members in by_have.values():
        nets = sorted({want[k] for k in members})
        if len(nets) > 1:
            names = " e ".join(ref.net_labels.get(n, n) for n in nets)
            who = ", ".join(ref.leg_label(k) for k in members)
            issues.append(
                Issue(
                    kind="sobrando",
                    refs=sorted({k.split(":")[0] for k in members}),
                    holes=[leg_hole[k] for k in members],
                    message=(
                        f"Ligação a mais: os nós {names} estão ligados na protoboard ({who})."
                    ),
                )
            )
    issues += [Issue(kind="aviso", message=w) for w in ref.warnings]
    errors = sum(i.kind in ERRORS for i in issues)
    ok = errors == 0 and bool(checked)
    summary = (
        f"Montagem confere com o esquemático: {len(checked)} peças, {len(legs)} pernas."
        if ok
        else f"{errors} problema(s) na montagem ({len(checked)} peças conferidas)."
        if checked
        else "Nada conferido ainda: monte as peças na protoboard."
    )
    return CheckReport(
        ok=ok, issues=issues, checked_parts=len(checked), checked_legs=len(legs), summary=summary
    )
