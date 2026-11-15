import pytest

from circuitos.simulation.jobs import JobQueue
from circuitos.simulation.results import SimulationRequest

pytestmark = pytest.mark.ngspice

DIV = "div\nV1 a 0 10\nR1 a b 1k\nR2 b 0 3k\n.op\n"
LONG = "t\nV1 a 0 SIN(0 1 1k)\nR1 a b 1k\nC1 b 0 1u\n.tran 1m 20 0 1n\n"


@pytest.fixture
def queue():
    q = JobQueue(max_workers=2)
    yield q
    q.shutdown()


def test_job_runs_in_subprocess(queue):
    job = queue.wait(queue.submit(SimulationRequest(DIV)).id, timeout=60)
    assert job.state == "done", job.error
    assert job.result is not None
    assert job.result.plot("op")["v(b)"].data[0] == pytest.approx(7.5)
    assert job.progress == 1.0


def test_job_failure_is_reported(queue):
    job = queue.wait(queue.submit(SimulationRequest("t\nR1 a 0\n.op\n")).id, timeout=60)
    assert job.state == "failed"
    assert job.error is not None and job.error.message


def test_job_cancel_running(queue):
    job = queue.submit(SimulationRequest(LONG))
    import time

    for _ in range(100):
        if job.state == "running" and job._process is not None:
            break
        time.sleep(0.05)
    assert queue.cancel(job.id)
    assert queue.wait(job.id, timeout=10).state == "cancelled"
    assert not queue.cancel(job.id)


def test_job_cancel_queued():
    q = JobQueue(max_workers=1)
    try:
        first = q.submit(SimulationRequest(LONG))
        second = q.submit(SimulationRequest(DIV))
        assert second.state == "queued"
        assert q.cancel(second.id) and second.state == "cancelled"
        q.cancel(first.id)
    finally:
        q.shutdown()


def test_job_timeout(queue):
    job = queue.submit(SimulationRequest(LONG, timeout_s=1.0, backend="batch"))
    job = queue.wait(job.id, timeout=30)
    assert job.state == "failed"
    assert "Tempo limite" in job.error.message


def test_unknown_job(queue):
    with pytest.raises(KeyError):
        queue.get("nada")


def test_prune_keeps_recent():
    q = JobQueue(max_workers=1, keep_finished=1)
    try:
        a = q.wait(q.submit(SimulationRequest(DIV)).id, timeout=60)
        b = q.wait(q.submit(SimulationRequest(DIV)).id, timeout=60)
        q.submit(SimulationRequest(DIV))
        with pytest.raises(KeyError):
            q.get(a.id)
        assert q.get(b.id).state == "done"
    finally:
        q.shutdown()
