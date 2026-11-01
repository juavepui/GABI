"""Investment cards (#246): versioned drafts, explicit states and a snapshot of inputs when published.

Reads only the local cache (ranking, checklist, evidence and identity); nothing is
downloaded. The snapshot keeps each metric with its source, period and date, the
reverse DCF and the comparables the checklist already computes, the evidence
summary and the issuer's identity, plus a SHA-256 of the whole snapshot. What is
absent is listed as absent, never filled in.
"""

import hashlib
import json
import re
from collections.abc import Callable
from datetime import date
from math import isfinite
from typing import Protocol

import pandas as pd

from gabi.application.errors import QueryError
from gabi.domain.portfolio import investment_card as rules


class CardStore(Protocol):
    def list(self, symbol: str | None, limit: int) -> list[dict]: ...
    def get(self, card_id: int) -> dict | None: ...
    def create(self, symbol: str, version: int, content: dict, now: str) -> int: ...
    def update(self, card_id: int, content: dict, state: str, now: str) -> bool: ...
    def publish(self, card_id: int, content: dict, snapshot: dict, digest: str, now: str) -> bool: ...
    def discard(self, card_id: int, reason: str, now: str) -> bool: ...


def _symbol(value: str) -> str:
    symbol = str(value or "").strip().upper().replace(".", "-")
    if not re.fullmatch(r"[A-Z0-9^][A-Z0-9^\-]{0,19}", symbol):
        raise QueryError("invalid_symbol", "Indica un símbolo válido.", 422)
    return symbol


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def digest(snapshot: dict) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                                     default=str).encode("utf-8")).hexdigest()


class InvestmentCards:
    def __init__(self, store: CardStore, *, ranking: Callable[[], pd.DataFrame], checklist: Callable[[str], dict],
                 evidence: Callable[[str], dict], identity: Callable[[str], dict], model_id: str | None,
                 today: Callable[[], date] = date.today):
        self.store, self.ranking, self.checklist, self.evidence = store, ranking, checklist, evidence
        self.identity, self.model_id, self.today = identity, model_id, today

    def present(self, row: dict) -> dict:
        content = row["content"]
        price = (row.get("snapshot") or {}).get("price", {}).get("value")
        return row | {"missing": rules.missing(content) if row["state"] in rules.EDITABLE else [],
                      "scenario_returns": rules.scenario_returns(content, price),
                      "version_rules": rules.VERSION, "not_a_probability": rules.NOT_A_PROBABILITY}

    def list(self, symbol: str | None = None, limit: int = 50) -> list[dict]:
        return [self.present(row) for row in self.store.list(_symbol(symbol) if symbol else None, limit)]

    def get(self, card_id: int) -> dict:
        row = self.store.get(card_id)
        if row is None:
            raise QueryError("card_not_found", "No existe una ficha con ese identificador.", 404)
        return self.present(row)

    def create(self, symbol: str, raw: dict) -> dict:
        """A new version of the company's card; only one version may be open for editing."""
        symbol = _symbol(symbol)
        content = self._content(raw)
        versions = self.store.list(symbol, 1000)
        if any(row["state"] in rules.EDITABLE for row in versions):
            raise QueryError("card_open", "Ya hay una versión abierta de esta ficha; edítala o descártala.", 409)
        version = max((row["version"] for row in versions), default=0) + 1
        return self.get(self.store.create(symbol, version, content, self.today().isoformat()))

    def save(self, card_id: int, raw: dict) -> dict:
        row = self.get(card_id)
        if row["state"] not in rules.EDITABLE:
            raise QueryError("card_closed", "Esta versión ya no se edita; abre una versión nueva.", 409)
        # Editing an analysed card sends it back to «incompleta» until it is marked again.
        self.store.update(card_id, self._content(raw), "incompleta", self.today().isoformat())
        return self.get(card_id)

    def move(self, card_id: int, target: str, reason: str = "") -> dict:
        row = self.get(card_id)
        try:
            state = rules.transition(row["state"], target, row["content"], today=self.today(), reason=reason)
        except rules.CardError as exc:
            raise QueryError("invalid_card", str(exc), 422) from exc
        now = self.today().isoformat()
        if state == "descartada":
            self.store.discard(card_id, reason.strip()[:rules.MAX_TEXT], now)
        elif state == "publicada":
            snapshot = self.capture(row["symbol"])
            self.store.publish(card_id, row["content"], snapshot, digest(snapshot), now)
        else:
            self.store.update(card_id, row["content"], state, now)
        return self.get(card_id)

    @staticmethod
    def _content(raw: dict) -> dict:
        try:
            return rules.normalize(raw)
        except rules.CardError as exc:
            raise QueryError("invalid_card", str(exc), 422) from exc

    def capture(self, symbol: str) -> dict:
        """The inputs at publication, from the local cache; each absence is named."""
        absent: list[str] = []
        snapshot: dict = {"captured_at": self.today().isoformat(), "model_id": self.model_id,
                          "instrument": {"symbol": symbol, "currency": "USD"}}
        try:
            identity = self.identity(symbol)
        except QueryError:
            identity = {}
        snapshot["issuer"] = {key: identity.get(key) for key in ("entity_id", "cik", "source")}
        if not identity.get("entity_id") and not identity.get("cik"):
            absent.append("identidad del emisor")
        price: dict[str, float | str | None] = {"value": None, "date": None, "score": None}
        try:
            table = self.ranking()
        except QueryError:
            table = None
        if table is not None and symbol in table.index:
            source = table.attrs.get("sources", {}).get(symbol, {})
            price = {"value": _finite(table.at[symbol, "price"]) if "price" in table else None,
                     "date": source.get("price_date"),
                     "score": _finite(table.at[symbol, "composite_score"]) if "composite_score" in table else None}
        if price["value"] is None:
            absent.append("precio")
        snapshot["price"] = price
        try:
            checklist = self.checklist(symbol)
        except QueryError:
            checklist = None
        if checklist:
            snapshot["checklist"] = {
                "as_of": checklist.get("as_of"), "fiscal_year_end": checklist.get("fiscal_year_end"),
                "sector": checklist.get("sector"), "financial_sector": checklist.get("financial_sector"),
                "thresholds_version": checklist.get("thresholds_version"),
                "metrics": [{key: item.get(key) for key in ("key", "label", "value", "unit", "source", "period",
                                                             "verdict", "reason")}
                            for item in checklist.get("criteria", [])],
                "reverse_dcf": checklist.get("dcf"), "historical_multiples": checklist.get("multiples_history")}
            absent += [f"métrica: {item['label']}" for item in snapshot["checklist"]["metrics"]
                       if item["value"] is None]
        else:
            snapshot["checklist"] = None
            absent.append("checklist")
        try:
            evidence = self.evidence(symbol)
        except QueryError:
            evidence = None
        snapshot["evidence"] = None if not evidence else {
            "data_coverage": evidence.get("weighted_data_coverage"), "score_coverage": evidence.get("score_coverage"),
            "statistical_evidence": evidence.get("evidence_stage"),
            "validated_score_fraction": evidence.get("validated_score_fraction"),
            "confidence_level": evidence.get("confidence_level"), "rules_version": evidence.get("rules_version")}
        if not evidence:
            absent.append("evidencia del modelo")
        snapshot["absent"] = absent
        return snapshot
