"""Pure SEC filing comparison over explicitly supplied cached facts."""

import pandas as pd

from gabi import filing_tracker


def compare_cached(symbol: str, facts: pd.DataFrame, cik: str | None) -> list[dict]:
    results: list[dict] = []
    for form in ("10-K", "10-Q"):
        filings = filing_tracker.filings_from_facts(facts, form, cik)
        if len(filings) < 2:
            results.append({"symbol": symbol, "form": form, "current": None, "previous": None,
                            "rows": [], "events": [], "reason": "Sin dos filings comparables."})
            continue
        current, previous = filings.iloc[-1], filings.iloc[-2]
        current_metrics = filing_tracker._period_metrics_for_accn(
            symbol, str(current["accn"]), form, facts=facts)
        previous_metrics = filing_tracker._period_metrics_for_accn(
            symbol, str(previous["accn"]), form, facts=facts)
        rows = filing_tracker.compare_filing_metrics(previous_metrics, current_metrics)
        result = {"symbol": symbol, "form": form, "current": current.to_dict(),
                  "previous": previous.to_dict(), "rows": rows,
                  "reason": None if rows else "Sin metricas comparables entre ambos filings."}
        result["events"] = filing_tracker.material_events_for_signal_monitor(result)
        results.append(result)
    return results
