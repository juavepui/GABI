"""Published Research Lab audits, presented with the fields of the Streamlit expanders."""

from collections.abc import Callable
from typing import Protocol

from gabi.application.errors import QueryError
from gabi.application.research.block_bootstrap_view import present
from gabi.application.research.historical import _json_value

AUDITS = ("overfitting-audit", "factor-benchmark", "factor-stability", "block-bootstrap", "rank-stability")
BOOTSTRAP_LABELS = {"v2_daily_net": "V2 neto diario frente al SPY",
                    "v1_quarterly_net": "V1 neto trimestral frente al SPY y al universo",
                    "cross_section_means": "IC y spread trimestrales"}


class SavedAuditStore(Protocol):
    def load(self, name: str) -> dict | None: ...
    def download(self, name: str, filename: str) -> bytes: ...


class SavedAuditQueries:
    def __init__(self, store: SavedAuditStore, research_mode: Callable[[], bool]):
        self.store, self.research_mode = store, research_mode

    def _load(self, name: str) -> dict | None:
        if not self.research_mode():
            raise QueryError("research_required", "Research Lab requiere el modo Research local.", 403)
        return self.store.load(name)

    def download(self, name: str, filename: str) -> bytes:
        if name not in AUDITS:
            raise QueryError("download_not_found", "Esta descarga no existe.", 404)
        self._load(name)
        return self.store.download(name, filename)

    def overview(self) -> dict:
        return {name: self._load(name) is not None for name in AUDITS}

    def overfitting(self) -> dict:
        audit = self._load("overfitting-audit")
        if audit is None:
            raise QueryError("saved_audit_missing", "La auditoría de sobreajuste no está publicada.", 404)
        primary, statistics = audit["primary"], audit["including_cost_sensitivity"]["trial_statistics"]
        return {
            "pbo": primary["pbo"]["pbo"], "dsr": primary["dsr"]["dsr"], "n_trials": primary["n_trials"],
            "n_obs": primary["n_obs"], "max_symbols": audit["inputs"]["max_symbols"],
            "trials": [{"trial_id": trial["trial_id"], "role": trial["role"], "months": trial["months"],
                        "cost_bps": trial["cost_bps"],
                        "sharpe": _json_value(statistics[trial["trial_id"]]["sharpe_anualizado"])}
                       for trial in audit["catalog"]],
            "pbo_sensitivity": [{"splits": int(splits), "pbo": result["pbo"]}
                                for splits, result in primary["pbo_sensitivity"].items()],
            "excluded": [{"trial": item["trial"], "reason": item["reason"]} for item in audit["excluded"]],
        }

    def factor_benchmark(self) -> dict:
        audit = self._load("factor-benchmark")
        if audit is None:
            raise QueryError("saved_audit_missing", "El benchmark ajustado no está publicado.", 404)
        return audit

    def factor_stability(self) -> dict:
        audit = self._load("factor-stability")
        if audit is None:
            raise QueryError("saved_audit_missing", "La estabilidad temporal no está publicada.", 404)
        return audit

    def block_bootstrap(self, dataset: str | None) -> dict:
        saved = self._load("block-bootstrap")
        if saved is None:
            raise QueryError("saved_audit_missing", "El diagnóstico de bloques no está publicado.", 404)
        result = saved["result"]
        datasets = list(result["datasets"])
        selected = dataset or datasets[0]
        if selected not in datasets:
            raise QueryError("invalid_request", "La serie del diagnóstico no existe.", 422)
        return {"datasets": [{"id": name, "label": BOOTSTRAP_LABELS.get(name, name)} for name in datasets],
                "unavailable": [{"id": name, "label": BOOTSTRAP_LABELS.get(name, name), "reason": reason}
                                for name, reason in result.get("unavailable_datasets", {}).items()],
                "selected": selected,
                "view": present(result["datasets"][selected], saved["distributions"][selected])}

    def rank_stability(self, date: str | None) -> dict:
        saved = self._load("rank-stability")
        if saved is None:
            raise QueryError("saved_audit_missing", "La estabilidad histórica no está publicada.", 404)
        result = saved["result"]
        dates = [row["date"] for row in result["dates"]]
        selected = date or dates[0]
        if selected not in dates:
            raise QueryError("invalid_request", "La fecha no pertenece al diagnóstico.", 422)
        companies = saved["companies"].get(selected)
        return {
            "stability_score": result["stability_score"], "n_dates": len(dates),
            "aggregate": [{"metric": metric} | {key: _json_value(value) for key, value in values.items()}
                          for metric, values in result["aggregate"].items()],
            "dates": dates, "selected": selected,
            "companies": [] if companies is None else [
                {key: _json_value(value) for key, value in row.items()} for row in companies.to_dict("records")],
            "sectors_complete": all(row["sectors_complete"] for row in result["dates"]),
            "limitations": result.get("limitations", []),
        }
