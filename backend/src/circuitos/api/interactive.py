"""Local interactive bench sessions; ordinary simulations continue using the job queue."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from circuitos.api.breadboard import reference_for
from circuitos.api.schematic import _records
from circuitos.breadboard.check import check
from circuitos.core.errors import CircuitosError
from circuitos.schematic.model import Schematic
from circuitos.schematic.netlist import SchematicError
from circuitos.simulation.interactive import BenchSessions, prepare

router = APIRouter(prefix="/api/v1/bench")


class StartIn(BaseModel):
    schematic: Schematic
    window_s: float = Field(default=0.01, ge=1e-6, le=1, allow_inf_nan=False)


class AdvanceIn(BaseModel):
    controls: dict[str, dict[str, str]] = Field(default_factory=dict)


@router.post("", status_code=201)
def start(request: Request, body: StartIn) -> dict[str, str]:
    sch = body.schematic
    try:
        if sch.breadboard is None:
            raise SchematicError("Monte o circuito na protoboard antes de iniciar a bancada.")
        ref = reference_for(request.app.state.components, sch)
        report = check(ref, sch.breadboard)
        if not report.ok:
            raise SchematicError("Corrija a montagem antes de iniciar a bancada: " + report.summary)
        plan = prepare(sch, _records(request, sch), body.window_s)
        sessions: BenchSessions = request.app.state.benches
        return {"id": sessions.start(plan)}
    except (ValueError, CircuitosError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{session_id}/advance")
def advance(request: Request, session_id: str, body: AdvanceIn) -> dict[str, Any]:
    sessions: BenchSessions = request.app.state.benches
    try:
        return sessions.advance(session_id, body.controls)
    except KeyError as exc:
        raise HTTPException(404, "Sessão de bancada encerrada. Inicie novamente.") from exc
    except (ValueError, CircuitosError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete("/{session_id}", status_code=204)
def stop(request: Request, session_id: str) -> None:
    sessions: BenchSessions = request.app.state.benches
    sessions.stop(session_id)
