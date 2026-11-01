"""Alerts of open ideas (#247): registered invalidation conditions and other available signals.

Version ``idea-alerts-v1``. An alert only asks the investor to review the idea;
nothing is ever traded. Every alert has a stable key, so running the job again
adds nothing new. The kinds:

- ``invalidacion``: a registered condition (metric, operator, threshold) holds
  for its persistence, counted in distinct fiscal periods observed by the job.
- ``revision_dato``: the same fiscal period now has another value (a restated or
  corrected figure), which is not a deterioration in itself.
- ``ausencia``: the metric has no value; missing data is not a deterioration.
- ``no_evaluable``: the condition names a metric the checklist does not compute.
- ``revision_vencida``: the card's or a condition's review date has arrived.
- ``filing``, ``resultados``, ``estimaciones``, ``insiders`` and ``tendencia``:
  a new 10-K/10-Q since publication, a negative earnings surprise, a consensus
  cut of at least 5 % in 90 days, net selling by at least two insiders in six
  months, or the idea 10 points behind the index or 20 % below its peak.
  Thresholds are declared here and only trigger a review.
"""

import math
from datetime import date

VERSION = "idea-alerts-v1"
ESTIMATE_CUT = -0.05
TREND_GAP = -0.10
TREND_DRAWDOWN = -0.20
MIN_SELLERS = 2
_OPERATORS = {"<": lambda a, b: a < b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b,
              ">=": lambda a, b: a >= b}


def _norm(text: str | None) -> str:
    return " ".join(str(text or "").lower().replace("_", " ").split())


def metric_of(condition: dict, metrics: list[dict]) -> dict | None:
    """The checklist metric a condition names, by key or label."""
    wanted = _norm(condition.get("metric"))
    return next((item for item in metrics if wanted and wanted in {_norm(item.get("key")), _norm(item.get("label"))}),
                None)


def streak(condition: dict, history: list[dict]) -> int:
    """Consecutive latest fiscal periods in which the condition holds (the latest value of each period)."""
    latest: dict[str, float] = {}
    for row in history:
        latest[row["period"]] = row["value"]
    holds = _OPERATORS[condition["operator"]]
    count = 0
    for period in sorted(latest, reverse=True):
        if holds(latest[period], condition["threshold"]):
            count += 1
        else:
            break
    return count


def _alert(key: str, kind: str, message: str, **evidence) -> dict:
    return {"key": key, "kind": kind, "message": message, "evidence": evidence}


def conditions(conditions: list[dict], metrics: list[dict], period: str | None,
               history: dict[int, list[dict]]) -> tuple[list[dict], list[dict]]:
    """New observations to record and the alerts of the registered conditions.

    ``history[index]`` holds the condition's earlier observations (period, value)."""
    observations, alerts = [], []
    for index, condition in enumerate(conditions):
        if not all(condition.get(key) not in (None, "") for key in ("metric", "operator", "threshold")):
            continue
        metric = metric_of(condition, metrics)
        if metric is None:
            alerts.append(_alert(f"no_evaluable:{index}", "no_evaluable",
                                 f"«{condition['metric']}» no es una métrica de la checklist: revísala a mano.",
                                 condition=index))
            continue
        value = metric.get("value")
        if value is None or not math.isfinite(float(value)) or period is None:
            alerts.append(_alert(f"ausencia:{index}:{period}", "ausencia",
                                 f"Sin dato de {metric['label']} para el ejercicio {period or 'desconocido'}: "
                                 "falta el dato, no es un deterioro.", condition=index, period=period,
                                 source=metric.get("source")))
            continue
        value = float(value)
        earlier = history.get(index, [])
        restated = [row for row in earlier if row["period"] == period and not math.isclose(row["value"], value)]
        if restated:
            alerts.append(_alert(f"revision_dato:{index}:{period}:{value}", "revision_dato",
                                 f"{metric['label']} del ejercicio {period} cambió de {restated[-1]['value']} a {value}: "
                                 "revisión del dato, no un deterioro por sí sola.",
                                 condition=index, period=period, before=restated[-1]["value"], after=value,
                                 source=metric.get("source")))
        if not any(row["period"] == period and math.isclose(row["value"], value) for row in earlier):
            observations.append({"condition": index, "period": period, "value": value})
        run = streak(condition, earlier + [{"period": period, "value": value}])
        if run >= int(condition.get("persistence") or 1):
            alerts.append(_alert(f"invalidacion:{index}:{period}", "invalidacion",
                                 f"Se cumple la condición de invalidación «{condition.get('description') or metric['label']}»: "
                                 f"{metric['label']} {condition['operator']} {condition['threshold']} "
                                 f"en {run} ejercicio(s) seguidos (último: {period}, valor {value}).",
                                 condition=index, period=period, value=value, streak=run, source=metric.get("source")))
    return observations, alerts


def reviews_due(content: dict, today: date) -> list[dict]:
    alerts = []
    if content.get("review_due") and date.fromisoformat(content["review_due"]) <= today:
        alerts.append(_alert(f"revision_vencida:{content['review_due']}", "revision_vencida",
                             f"Llegó la fecha de revisión de la ficha ({content['review_due']}).",
                             date=content["review_due"]))
    for index, condition in enumerate(content.get("invalidation") or []):
        due = condition.get("review_by")
        if due and date.fromisoformat(due) <= today:
            alerts.append(_alert(f"revision_vencida:{index}:{due}", "revision_vencida",
                                 f"Llegó la fecha de revisar la condición «{condition.get('description') or index + 1}».",
                                 condition=index, date=due))
    return alerts


def signals(published_on: str, *, filings: list[dict], surprises: list[dict], revision: dict | None,
            insiders: dict | None, evaluation: dict | None, month: str) -> list[dict]:
    """Alerts from the other local sources; each one is only a reason to review."""
    alerts = []
    for filing in filings:
        current = filing.get("current") or {}
        if current.get("filed_date") and current["filed_date"] > published_on:
            alerts.append(_alert(f"filing:{filing['form']}:{current['filed_date']}", "filing",
                                 f"Nuevo {filing['form']} presentado el {current['filed_date']} "
                                 f"(periodo {current.get('period_end')}): revisa si cambia la tesis.",
                                 form=filing["form"], filed=current["filed_date"], url=current.get("url")))
    for surprise in surprises:
        day, pct = surprise.get("earnings_date"), surprise.get("surprise_pct")
        if day and str(day)[:10] > published_on and pct is not None and float(pct) < 0:
            alerts.append(_alert(f"resultados:{str(day)[:10]}", "resultados",
                                 f"Resultados del {str(day)[:10]} por debajo del consenso ({float(pct):.1f} %).",
                                 date=str(day)[:10], surprise_pct=float(pct)))
    if revision and revision.get("change_pct") is not None and revision["change_pct"] <= ESTIMATE_CUT \
            and str(revision.get("current_captured_at", ""))[:10] > published_on:
        captured = str(revision["current_captured_at"])[:10]
        alerts.append(_alert(f"estimaciones:{captured}", "estimaciones",
                             f"El consenso de BPA bajó un {-revision['change_pct'] * 100:.1f} % en "
                             f"{revision.get('actual_lookback_days')} días.", captured=captured,
                             change_pct=revision["change_pct"]))
    if insiders and (insiders.get("net_value") or 0) < 0 and (insiders.get("distinct_sellers") or 0) >= MIN_SELLERS:
        alerts.append(_alert(f"insiders:{month}", "insiders",
                             f"{insiders['distinct_sellers']} insiders vendieron en neto en los últimos "
                             f"{insiders.get('months', 6)} meses.", net_value=insiders["net_value"],
                             sellers=insiders["distinct_sellers"]))
    if evaluation and evaluation.get("status") == "ok":
        excess, drawdown = evaluation["excess"], evaluation["max_drawdown"]
        if excess <= TREND_GAP or drawdown <= TREND_DRAWDOWN:
            level = min(math.floor(excess / abs(TREND_GAP)), math.floor(drawdown / abs(TREND_DRAWDOWN)) * 2)
            alerts.append(_alert(f"tendencia:{level}", "tendencia",
                                 f"La idea va {excess * 100:+.1f} puntos frente al S&P 500 y llegó a caer "
                                 f"{drawdown * 100:.1f} % desde su máximo.", excess=excess, max_drawdown=drawdown))
    return alerts


def pending(alerts: list[dict], events: list[dict]) -> list[dict]:
    """Alerts detected after the investor's last review, close or withdrawal: still to be attended."""
    attended = max((event["recorded_at"] for event in events if event["kind"] in {"revisada", "cerrada", "retirada"}),
                   default="")
    return [alert for alert in alerts if alert["detected_at"] > attended]
