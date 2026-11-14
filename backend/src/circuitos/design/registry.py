"""Design modules available to the application (plug-ins under ``design/plugins``)."""

from __future__ import annotations

from circuitos.design.engine import TopologyModule
from circuitos.design.plugins.ret1 import Ret1Module
from circuitos.design.plugins.ret3 import Ret3Module
from circuitos.design.plugins.retc1 import Retc1Module

MODULES: dict[str, TopologyModule] = {m.id: m for m in (Ret1Module(), Retc1Module(), Ret3Module())}


def get(module_id: str) -> TopologyModule:
    try:
        return MODULES[module_id]
    except KeyError as exc:
        raise KeyError(f"Módulo de projeto desconhecido: {module_id}") from exc
