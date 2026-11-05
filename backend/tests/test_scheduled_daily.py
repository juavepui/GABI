from datetime import date

import pytest

from gabi.application.administration.jobs import Jobs
from gabi.application.administration.scheduled_daily import Unattended, UnattendedPolicy, schedule_daily
from gabi.infrastructure.storage.jobs import SqliteJobs

TODAY = date(2026, 11, 5)


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def monotonic(self) -> float:
        return self.now


class FakeWorker:
    """Finishes each refresh with the next scripted outcome the first time the scheduler looks at it."""

    def __init__(self, store: SqliteJobs, outcomes: list[str | None]):
        self.store = store
        self.outcomes = outcomes
        self.started: list[str] = []

    def step(self) -> None:
        job = self.store.claim("token")
        if job is None:
            return
        self.started.append(job["kind"])
        outcome = self.outcomes.pop(0) if job["kind"] == "refresh" else None
        if outcome is None:
            self.store.finish(job["id"], "token", "succeeded", ref=job["id"], digest="0" * 64)
        else:
            self.store.finish(job["id"], "token", "failed", error=outcome)


def unattended(clock: Clock, network: list[bool], worker: FakeWorker | None, messages: list[str],
               policy: UnattendedPolicy = UnattendedPolicy()) -> Unattended:
    def network_ready() -> bool:
        return network.pop(0) if len(network) > 1 else network[0]

    def sleep(seconds: float) -> None:
        clock.sleep(seconds)
        if worker is not None:
            worker.step()

    return Unattended(network_ready=network_ready, sleep=sleep, monotonic=clock.monotonic,
                      report=messages.append, policy=policy)


def refreshes(store: SqliteJobs) -> list[dict]:
    return sorted((job for job in store.list() if job["kind"] == "refresh"), key=lambda job: job["created_at"])


def test_without_unattended_mode_it_only_queues(tmp_path):
    store = SqliteJobs(tmp_path)
    schedule_daily(Jobs(store), TODAY)
    schedule_daily(Jobs(store), TODAY)
    assert sorted(job["kind"] for job in store.list()) == ["maintenance", "refresh"]
    assert all(job["status"] == "queued" for job in store.list())


def test_waits_for_the_network_before_queueing(tmp_path):
    store, clock, messages = SqliteJobs(tmp_path), Clock(), []
    queued_while_offline = []

    def network_ready() -> bool:
        queued_while_offline.append(len(store.list()))
        return len(clock.sleeps) >= 3

    mode = Unattended(network_ready=network_ready, sleep=clock.sleep, monotonic=clock.monotonic,
                      report=messages.append, policy=UnattendedPolicy(retries=0))
    schedule_daily(Jobs(store), TODAY, mode)
    assert queued_while_offline == [0, 0, 0, 0]
    assert clock.sleeps == [15, 15, 15]
    assert len(store.list()) == 2
    assert messages[-1] == "Conexión a internet disponible."


def test_network_that_never_returns_still_queues_after_the_limit(tmp_path):
    store, clock, messages = SqliteJobs(tmp_path), Clock(), []
    policy = UnattendedPolicy(network_wait_seconds=60, network_poll_seconds=15, retries=0)
    schedule_daily(Jobs(store), TODAY, unattended(clock, [False], None, messages, policy))
    assert clock.now == 60
    assert len(store.list()) == 2
    assert "se encola igualmente" in messages[-1]


def test_a_refresh_failed_by_the_sources_is_repeated_until_it_succeeds(tmp_path):
    store, clock, messages = SqliteJobs(tmp_path), Clock(), []
    worker = FakeWorker(store, ["sources_failed", None])
    schedule_daily(Jobs(store), TODAY, unattended(clock, [True], worker, messages))
    jobs = refreshes(store)
    assert [job["status"] for job in jobs] == ["failed", "succeeded"]
    assert jobs[1]["origin"] == "scheduler"
    assert 600 in clock.sleeps
    assert any("reintento 1 de 2" in message for message in messages)


def test_retries_stop_at_the_limit_and_say_so(tmp_path):
    store, clock, messages = SqliteJobs(tmp_path), Clock(), []
    worker = FakeWorker(store, ["sources_failed"] * 3)
    schedule_daily(Jobs(store), TODAY, unattended(clock, [True], worker, messages))
    assert [job["status"] for job in refreshes(store)] == ["failed"] * 3
    assert "sigue fallando" in messages[-1]


@pytest.mark.parametrize("outcome", [None, "unexpected"])
def test_success_or_another_kind_of_failure_is_not_repeated(tmp_path, outcome):
    store, clock = SqliteJobs(tmp_path), Clock()
    worker = FakeWorker(store, [outcome])
    schedule_daily(Jobs(store), TODAY, unattended(clock, [True], worker, []))
    assert len(refreshes(store)) == 1


def test_without_a_worker_it_gives_up_waiting_and_does_not_retry(tmp_path):
    store, clock, messages = SqliteJobs(tmp_path), Clock(), []
    policy = UnattendedPolicy(job_wait_seconds=120, job_poll_seconds=30)
    schedule_daily(Jobs(store), TODAY, unattended(clock, [True], None, messages, policy))
    assert clock.now == 120
    assert [job["status"] for job in refreshes(store)] == ["queued"]
    assert "no ha terminado a tiempo" in messages[-1]


def test_running_again_the_same_day_reuses_the_same_retry(tmp_path):
    store = SqliteJobs(tmp_path)
    worker = FakeWorker(store, ["sources_failed", None])
    schedule_daily(Jobs(store), TODAY, unattended(Clock(), [True], worker, []))
    schedule_daily(Jobs(store), TODAY, unattended(Clock(), [True], FakeWorker(store, []), []))
    assert [job["status"] for job in refreshes(store)] == ["failed", "succeeded"]
