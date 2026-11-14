"""Simulation jobs in separate processes, with progress, timeout and cancellation.

ngspice keeps global state and can crash or hang on bad netlists, so every job runs in its own
``spawn``-ed process. A hung or cancelled job is terminated without affecting the API.
"""

from __future__ import annotations

import contextlib
import multiprocessing as mp
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from multiprocessing.connection import Connection
from typing import Any, Literal

from circuitos.core import errors
from circuitos.simulation.results import SimulationRequest, SimulationResult

JobState = Literal["queued", "running", "done", "failed", "cancelled"]


@dataclass
class JobError:
    kind: str
    message: str
    suggestions: list[str] = field(default_factory=list)
    log: str = ""


@dataclass
class Job:
    id: str
    request: SimulationRequest
    state: JobState = "queued"
    progress: float = 0.0
    message: str = "na fila"
    result: SimulationResult | None = None
    error: JobError | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    _done: threading.Event = field(default_factory=threading.Event, repr=False)
    _process: Any = field(default=None, repr=False)

    @property
    def finished(self) -> bool:
        return self.state in ("done", "failed", "cancelled")


def _worker_main(request: SimulationRequest, conn: Connection) -> None:  # pragma: no cover
    """Entry point of the worker process (coverage is not collected in child processes)."""
    from circuitos.simulation.backend import make_backend

    last = 0.0

    def send(*message: object) -> None:
        # The parent closes the pipe when it cancels the job.
        with contextlib.suppress(BrokenPipeError, OSError):
            conn.send(message)

    def progress(fraction: float, message: str) -> None:
        nonlocal last
        now = time.monotonic()
        if now - last > 0.05 or fraction >= 1.0:
            last = now
            send("progress", fraction, message)

    try:
        backend = make_backend(request.backend, timeout_s=request.timeout_s)
        result = backend.run(request.netlist, progress)
        send("result", result)
    except errors.SimulationError as exc:
        send("error", type(exc).__name__, str(exc), exc.suggestions, exc.log)
    except Exception as exc:
        send("error", type(exc).__name__, f"Erro interno do simulador: {exc}", [], "")
    finally:
        conn.close()


class JobQueue:
    def __init__(self, max_workers: int = 2, keep_finished: int = 50):
        self.max_workers = max_workers
        self.keep_finished = keep_finished
        self._ctx = mp.get_context("spawn")
        self._jobs: dict[str, Job] = {}
        self._pending: deque[str] = deque()
        self._running = 0
        self._lock = threading.Lock()

    # public API ---------------------------------------------------------------------------
    def submit(self, request: SimulationRequest) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], request=request)
        with self._lock:
            self._jobs[job.id] = job
            self._pending.append(job.id)
            self._prune()
        self._dispatch()
        return job

    def get(self, job_id: str) -> Job:
        with self._lock:
            try:
                return self._jobs[job_id]
            except KeyError as exc:
                raise KeyError(f"Simulação {job_id} não encontrada") from exc

    def wait(self, job_id: str, timeout: float | None = None) -> Job:
        job = self.get(job_id)
        job._done.wait(timeout)
        return job

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        with self._lock:
            if job.finished:
                return False
            if job.state == "queued":
                self._pending.remove(job_id)
                self._finish(job, "cancelled", message="cancelada")
                return True
            process = job._process
        if process is not None and process.is_alive():
            process.terminate()
        with self._lock:
            if not job.finished:
                self._finish(job, "cancelled", message="cancelada")
        return True

    def shutdown(self) -> None:
        for job_id in list(self._jobs):
            self.cancel(job_id)

    # internals ----------------------------------------------------------------------------
    def _prune(self) -> None:
        finished = sorted(
            (j for j in self._jobs.values() if j.finished), key=lambda j: j.created_at
        )
        for job in finished[: max(len(finished) - self.keep_finished, 0)]:
            del self._jobs[job.id]

    def _finish(self, job: Job, state: JobState, *, message: str) -> None:
        """Must be called with the lock held."""
        if job.state == "running":
            self._running -= 1
        job.state = state
        job.message = message
        job.finished_at = time.time()
        if state == "done":
            job.progress = 1.0
        job._done.set()

    def _dispatch(self) -> None:
        to_start: list[Job] = []
        with self._lock:
            while self._pending and self._running < self.max_workers:
                job = self._jobs[self._pending.popleft()]
                job.state = "running"
                job.message = "iniciando"
                job.started_at = time.time()
                self._running += 1
                to_start.append(job)
        for job in to_start:
            threading.Thread(target=self._run, args=(job,), daemon=True).start()

    def _run(self, job: Job) -> None:
        parent, child = self._ctx.Pipe(duplex=False)
        process = self._ctx.Process(target=_worker_main, args=(job.request, child), daemon=True)
        job._process = process
        process.start()
        child.close()
        deadline = time.monotonic() + job.request.timeout_s + 10.0  # margin for start-up
        outcome: tuple[Any, ...] | None = None
        try:
            while outcome is None and not job.finished:
                if time.monotonic() > deadline:
                    process.terminate()
                    with self._lock:
                        job.error = JobError(
                            "SimulationError",
                            f"Tempo limite de {job.request.timeout_s:g} s excedido",
                            ["Reduza o tempo simulado ou aumente o passo máximo."],
                        )
                        self._finish(job, "failed", message="tempo limite excedido")
                    break
                if parent.poll(0.1):
                    try:
                        message = parent.recv()
                    except EOFError:
                        break
                    if message[0] == "progress":
                        job.progress, job.message = float(message[1]), str(message[2])
                    else:
                        outcome = message
                elif not process.is_alive() and not parent.poll(0):
                    break
        finally:
            parent.close()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
        with self._lock:
            if not job.finished:
                if outcome is not None and outcome[0] == "result":
                    job.result = outcome[1]
                    self._finish(job, "done", message="concluída")
                elif outcome is not None:
                    _, kind, msg, suggestions, log = outcome
                    job.error = JobError(kind, msg, list(suggestions), log)
                    self._finish(job, "failed", message=msg)
                else:
                    job.error = JobError(
                        "SimulationError",
                        f"O processo do simulador terminou inesperadamente "
                        f"(código {process.exitcode})",
                    )
                    self._finish(job, "failed", message=job.error.message)
        self._dispatch()
