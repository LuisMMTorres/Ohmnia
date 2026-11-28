"""Build schematics in tests: each part in its own grid cell, its pins tied to nets by labels."""

from __future__ import annotations

from circuitos.schematic.library import is_supply_pin, pin_defs, pin_positions
from circuitos.schematic.model import Analysis, Component, NetLabel, Schematic


class Builder:
    def __init__(self, title: str = "teste") -> None:
        self.sch = Schematic(title=title)
        self._n = 0

    def add(self, kind: str, ref: str, nodes: list[str], part_id: str | None = None, **params: str):
        self._n += 1
        comp = Component(
            id=f"c{self._n}",
            kind=kind,
            ref=ref,
            x=(self._n % 8) * 20,
            y=(self._n // 8) * 20,
            params={k: str(v) for k, v in params.items()},
            part_id=part_id,
        )
        pins = pin_defs(comp)
        # trailing supply pins (op-amp V+/V−) may be left out: they stay loose (implicit supply)
        rest = pins[len(nodes) :]
        assert len(nodes) <= len(pins) and all(is_supply_pin(kind, p.name) for p in rest), (
            f"{kind} tem {len(pins)} pinos"
        )
        pos = pin_positions(comp)
        self.sch.components.append(comp)
        for p, node in zip(pins, nodes, strict=False):
            x, y = pos[p.name]
            self.sch.labels.append(NetLabel(id=f"l{len(self.sch.labels)}", name=node, x=x, y=y))
        return comp

    def analysis(self, kind: str, **params: str) -> Builder:
        self.sch.analyses.append(Analysis(kind=kind, params={k: str(v) for k, v in params.items()}))  # type: ignore[arg-type]
        return self
