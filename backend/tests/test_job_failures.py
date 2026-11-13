"""Failed jobs say what failed and what to do (#179): closed categories, no exception text over HTTP."""

import json

import pytest
import requests

from gabi.application.administration.jobs import JobCommand, SourceFailures
from gabi.application.errors import QueryError
from gabi.domain.administration.job_failures import FAILURES, describe_failure
from gabi.infrastructure.jobs.worker import Worker, classify_failure
from gabi.infrastructure.storage.jobs import SqliteJobs


def _http(status):
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(f"{status} for url https://api.example/?api_key=secret", response=response)


class YFRateLimitError(Exception):
    """Same name as yfinance's, which the worker recognises without importing yfinance."""


def _wrapped(inner):
    try:
        raise inner
    except Exception as cause:
        try:
            raise RuntimeError("descarga fallida") from cause
        except RuntimeError as outer:
            return outer


# One simulated failure of each category, as the executors raise them.
CASES = [
    (requests.ConnectionError("connection refused C:\\Users\\local"), "source_unavailable"),
    (requests.Timeout("read timed out"), "source_unavailable"),
    (_http(503), "source_unavailable"),
    (_http(401), "key_rejected"),
    (_http(403), "key_rejected"),
    (_http(429), "rate_limited"),
    (YFRateLimitError("Too Many Requests"), "rate_limited"),
    (ValueError("Falta la clave de Nasdaq Data Link (Configuración)"), "key_missing"),
    (QueryError("data_unavailable", "Sin datos"), "insufficient_data"),
    (QueryError("no_candidates", "Sin candidatas"), "insufficient_data"),
    (QueryError("returns_missing", "Sin retornos"), "insufficient_data"),
    (QueryError("invalid_experiment", "Configuración no válida"), "internal_error"),
    (_wrapped(requests.ConnectionError("dns")), "source_unavailable"),
    (_wrapped(_http(429)), "rate_limited"),
    (RuntimeError("boom"), "internal_error"),
    (KeyError("column"), "internal_error"),
]


@pytest.mark.parametrize("error, code", CASES)
def test_each_exception_falls_in_one_closed_category(error, code):
    assert classify_failure(error) == code


def test_every_code_has_a_message_and_an_action_without_paths_or_secrets():
    for code in FAILURES:
        described = describe_failure(code)
        assert described["message"] and described["action"] and described["retry"] in {"now", "later", "after_fix",
                                                                                        "no"}
        assert "\\" not in described["message"] + described["action"] and "secret" not in json.dumps(described)
    assert describe_failure("job_failed")["label"] == "Causa no clasificada"  # stored before #179
    assert describe_failure("something_new")["category"] == "internal_error"
    assert describe_failure(None, cancelled=True)["category"] == "cancelled"
    assert describe_failure("rate_limited")["retry"] == "later" and describe_failure("key_missing")["retry"] == \
        "after_fix"


@pytest.mark.parametrize("error, code", CASES)
def test_a_simulated_failure_of_each_category_reaches_the_job(tmp_path, error, code):
    store = SqliteJobs(tmp_path)
    job = store.enqueue(JobCommand("quality"), "quality-" + code, "ui")

    def fails(_command, progress):
        progress(0.5, "Descargando precios de Yahoo")
        raise error

    fails.reports_progress = True  # type: ignore[attr-defined]
    Worker(store, fails, tmp_path).run_once()
    failed = store.get(job["id"])
    assert failed["status"] == "failed" and failed["error_code"] == code
    assert failed["failure"] == describe_failure(code)
    assert failed["last_activity"] == "Descargando precios de Yahoo"
    # Neither the exception text nor local paths travel: only the category and the reported step.
    text = json.dumps(failed)
    assert "secret" not in text and "C:\\\\Users" not in text and "boom" not in text
    listed = next(item for item in store.list() if item["id"] == job["id"])
    assert listed["failure"]["category"] == describe_failure(code)["category"]


def test_source_failures_and_cancellation_keep_their_own_descriptions(tmp_path):
    store = SqliteJobs(tmp_path)
    job = store.enqueue(JobCommand("refresh"), "refresh-sources", "ui")

    def fails(_):
        raise SourceFailures([("yahoo", "AAA")])

    Worker(store, fails, tmp_path).run_once()
    failed = store.get(job["id"])
    assert failed["failure"]["label"] == "Fuentes no disponibles para algunos símbolos"
    assert failed["failure"]["category"] == "source_unavailable" and failed["failures_total"] == 1
    queued = store.enqueue(JobCommand("quality"), "quality-cancel", "ui")
    cancelled = store.cancel(queued["id"])
    assert cancelled["failure"]["category"] == "cancelled" and cancelled["last_activity"] is None
    done = store.enqueue(JobCommand("quality"), "quality-ok", "ui")
    Worker(store, lambda _: {"ok": True}, tmp_path).run_once()
    assert store.get(done["id"])["failure"] is None
