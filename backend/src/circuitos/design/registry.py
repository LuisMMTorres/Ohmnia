"""Design modules available to the application (plug-ins under ``design/plugins``)."""

from __future__ import annotations

from circuitos.design.engine import TopologyModule
from circuitos.design.plugins.bias import BiasModule
from circuitos.design.plugins.cc import CcModule
from circuitos.design.plugins.cci import CciModule
from circuitos.design.plugins.chave import ChaveModule
from circuitos.design.plugins.diff import DiffModule
from circuitos.design.plugins.fil import FilModule
from circuitos.design.plugins.forma import FormaModule
from circuitos.design.plugins.inst import InstModule
from circuitos.design.plugins.lin import LinModule
from circuitos.design.plugins.opa import OpaModule
from circuitos.design.plugins.opnl import OpnlModule
from circuitos.design.plugins.osc import OscModule
from circuitos.design.plugins.pa import PaModule
from circuitos.design.plugins.pad import PadModule
from circuitos.design.plugins.ret1 import Ret1Module
from circuitos.design.plugins.ret3 import Ret3Module
from circuitos.design.plugins.retc1 import Retc1Module
from circuitos.design.plugins.ssa import SsaModule
from circuitos.design.plugins.zen import ZenModule

MODULES: dict[str, TopologyModule] = {
    m.id: m
    for m in (
        Ret1Module(),
        Retc1Module(),
        Ret3Module(),
        ZenModule(),
        LinModule(),
        BiasModule(),
        SsaModule(),
        DiffModule(),
        PaModule(),
        PadModule(),
        ChaveModule(),
        FormaModule(),
        OpaModule(),
        FilModule(),
        OpnlModule(),
        OscModule(),
        InstModule(),
        CcModule(),
        CciModule(),
    )
}


def get(module_id: str) -> TopologyModule:
    try:
        return MODULES[module_id]
    except KeyError as exc:
        raise KeyError(f"Módulo de projeto desconhecido: {module_id}") from exc
