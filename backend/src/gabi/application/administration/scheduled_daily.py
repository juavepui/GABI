"""Daily scheduled jobs: queue the price refresh and maintenance, optionally unattended.

Unattended mode is for the Windows task. After the computer wakes up, the network can take a
minute to come back, and a refresh started without it fails for every company. So it first waits
for the network, then follows the refresh and, if it failed because the sources did not answer,
repeats it a few times. Other failures are not retried: repeating them would hide a real problem.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from gabi.application.administration.jobs import JobCommand, Jobs
from gabi.application.errors import QueryError

FINISHED = {"succeeded", "failed", "cancelled"}
RETRYABLE_ERRORS = {"sources_failed"}


@dataclass(frozen=True)
class UnattendedPolicy:
    network_wait_seconds: float = 15 * 60
    network_poll_seconds: float = 15
    job_wait_seconds: float = 4 * 3600
    job_poll_seconds: float = 30
    retry_delay_seconds: float = 10 * 60
    retries: int = 2

    def __post_init__(self) -> None:
        if self.retries < 0 or min(self.network_wait_seconds, self.network_poll_seconds, self.job_wait_seconds,
                                   self.job_poll_seconds, self.retry_delay_seconds) < 0:
            raise ValueError("Invalid unattended policy")


@dataclass(frozen=True)
class Unattended:
    """Ports for unattended mode: network check, clock and sleep come from the CLI bootstrap."""

    network_ready: Callable[[], bool]
    sleep: Callable[[float], None]
    monotonic: Callable[[], float]
    report: Callable[[str], None] = lambda _message: None
    policy: UnattendedPolicy = UnattendedPolicy()


def wait_for_network(unattended: Unattended) -> bool:
    policy = unattended.policy
    deadline = unattended.monotonic() + policy.network_wait_seconds
    if unattended.network_ready():
        return True
    unattended.report("Sin conexión a internet todavía; esperando a que vuelva la red.")
    while unattended.monotonic() < deadline:
        unattended.sleep(policy.network_poll_seconds)
        if unattended.network_ready():
            unattended.report("Conexión a internet disponible.")
            return True
    unattended.report("La red no ha vuelto a tiempo; se encola igualmente y se reintentará si falla.")
    return False


def wait_for_job(jobs: Jobs, job_id: str, unattended: Unattended) -> dict | None:
    """The finished job, or None if it did not finish in time (for example, no worker running)."""
    policy = unattended.policy
    deadline = unattended.monotonic() + policy.job_wait_seconds
    while True:
        job = jobs.get(job_id)
        if job["status"] in FINISHED:
            return job
        if unattended.monotonic() >= deadline:
            unattended.report("El refresco no ha terminado a tiempo; no se reintentará en esta ejecución.")
            return None
        unattended.sleep(policy.job_poll_seconds)


def schedule_daily(jobs: Jobs, today: date, unattended: Unattended | None = None) -> None:
    if unattended is not None:
        wait_for_network(unattended)
    refresh = None
    for command, key in ((JobCommand("refresh"), f"schedule:refresh:{today}"),
                         (JobCommand("maintenance"), f"schedule:maintenance:{today}")):
        try:
            job = jobs.submit(command, key, origin="scheduler")
        except QueryError as exc:
            if exc.code != "job_conflict":
                raise
            continue
        if command.kind == "refresh":
            refresh = job
    if unattended is None or refresh is None or unattended.policy.retries == 0:
        return
    policy = unattended.policy
    for attempt in range(1, policy.retries + 1):
        finished = wait_for_job(jobs, refresh["id"], unattended)
        if finished is None or finished["status"] != "failed" or finished["error_code"] not in RETRYABLE_ERRORS:
            return
        unattended.report(f"El refresco falló porque las fuentes no respondieron; "
                          f"reintento {attempt} de {policy.retries} dentro de {policy.retry_delay_seconds / 60:g} min.")
        unattended.sleep(policy.retry_delay_seconds)
        wait_for_network(unattended)
        try:
            refresh = jobs.retry(finished["id"], f"programado:{today}:{attempt}", origin="scheduler")
        except QueryError as exc:
            if exc.code != "job_conflict":
                raise
            unattended.report("Ya hay otro refresco pendiente o en curso; no hace falta reintentar.")
            return
    finished = wait_for_job(jobs, refresh["id"], unattended)
    if finished is not None and finished["status"] == "failed":
        unattended.report("El refresco sigue fallando tras los reintentos; revísalo en Administración.")
