"""Issuer risk panel and the investable portfolio policy (#248); reads the local cache only.

The panel aggregates Mi cartera by issuer, sector, industry, currency, factors and
liquidity. The proposal compares the frozen equal-weight Top-N with the same
selection under the policy limits, and the buy orders a contribution would need
under each. Nothing is activated and no order is sent.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime
from math import isfinite
from typing import Protocol

import pandas as pd

from gabi.application.errors import QueryError
from gabi.domain.portfolio import risk_policy as rules
from gabi.domain.portfolio.selection import target_portfolio

DEFAULT_TOLERANCE = 0.20
BLOCK_COLUMNS = {block: f"{block}_score" for block in rules.BLOCKS}
COST_KEYS = ("commission_fixed_eur", "commission_pct", "fx_cost_pct", "min_order_eur")


class PolicyStore(Protocol):
    def latest(self) -> dict | None: ...
    def revisions(self) -> list[dict]: ...
    def save(self, version: str, profile: dict, now: str) -> int: ...


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _text(value) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


class PortfolioRisk:
    def __init__(self, store: PolicyStore, positions: Callable[[], list[dict]], ranking: Callable[[], pd.DataFrame],
                 issuers: Callable[[list[str]], dict[str, str]], industries: Callable[[], dict[str, str]],
                 profile: Callable[[], dict | None], euros_per_dollar: Callable[[], float | None],
                 today: Callable[[], date], now: Callable[[], datetime] = lambda: datetime.now(UTC)):
        """`issuers(symbols)` maps each symbol to its SEC entity (the symbol itself when unresolved);
        `profile()` is the saved investor profile revision; `euros_per_dollar()` the cached rate."""
        self.store, self.positions, self.ranking, self.issuers = store, positions, ranking, issuers
        self.industries, self.profile, self.euros_per_dollar = industries, profile, euros_per_dollar
        self.today, self.now = today, now

    def policy_state(self) -> dict:
        return {"current": self.store.latest(), "revisions": self.store.revisions(),
                "default": rules.stored(rules.Policy()), "version": rules.POLICY_VERSION}

    def save_policy(self, raw: dict) -> dict:
        """Every save is a new revision of the policy, separate from the model versions."""
        try:
            policy = rules.validate_policy(raw)
        except ValueError as exc:
            raise QueryError("invalid_policy", str(exc), 422) from exc
        self.store.save(policy.version, rules.stored(policy), self.now().isoformat())
        saved = self.store.latest()
        assert saved is not None
        return saved

    def _policy(self) -> tuple[rules.Policy, int | None]:
        saved = self.store.latest()
        return (rules.validate_policy(saved["profile"]), saved["revision"]) if saved else (rules.Policy(), None)

    def _investor(self) -> dict:
        return (self.profile() or {}).get("profile") or {}

    @staticmethod
    def _dollar_volume(row: dict) -> float | None:
        volume, price = _number(row.get("avg_volume")), _number(row.get("price"))
        return volume * price if volume and price else None

    def panel(self) -> dict:
        """Read-only exposure of Mi cartera: issuers, sectors, currencies, factors, liquidity and stress."""
        policy, revision = self._policy()
        table, rate = self.ranking(), self.euros_per_dollar()
        tolerance = _number(self._investor().get("loss_tolerance")) or DEFAULT_TOLERANCE
        valued = self.positions()
        held = [row for row in valued if row["status"] == "ok" and row.get("value_eur")]
        issuers = self.issuers([row["symbol"] for row in held]) if held else {}
        industries = self.industries()
        positions = []
        for row in held:
            symbol = row["symbol"]
            info = table.loc[symbol].to_dict() if symbol in table.index else {}
            dollar_volume = self._dollar_volume(info)
            positions.append({
                "symbol": symbol, "issuer": issuers.get(symbol, symbol), "value_eur": float(row["value_eur"]),
                "sector": _text(info.get("sector")), "industry": industries.get(symbol),
                "listing_currency": row["currency"],
                # An S&P 500 member earns in dollars whatever its listing: its economic exposure is USD.
                "economic_currency": "USD" if info else row["currency"],
                "scores": {block: _number(info.get(column)) for block, column in BLOCK_COLUMNS.items()},
                "daily_volume_eur": dollar_volume * rate if dollar_volume and rate else None,
                "beta": _number(info.get("beta_calc"))})
        exposure = rules.exposures(positions, policy)
        days = {row["symbol"]: row["days_to_trade"] for row in exposure["liquidity"]}
        stress = rules.stress([row | {"days_to_trade": days.get(row["symbol"])} for row in positions], tolerance)
        return {"as_of": self.today().isoformat(), "policy_version": policy.version, "policy_revision": revision,
                "policy": rules.stored(policy), "loss_tolerance": tolerance, "positions": len(positions),
                "unvalued": [row["symbol"] for row in valued if row["status"] != "ok"],
                "exposure": exposure, "stress": stress,
                "economic_currency_note": "Aproximación: un miembro del S&P 500 cuenta en USD aunque cotice en otra "
                                          "moneda; el resto, en su moneda de cotización."}

    def proposal(self, contribution_eur: float, n_positions: int = 20) -> dict:
        """Read-only: equal-weight Top-N against the same selection under the policy, with the orders for a
        contribution under each. The number of positions is the investor's choice, never optimised."""
        if not 5 <= n_positions <= 30 or not isfinite(contribution_eur) or not 0 <= contribution_eur <= 1e8:
            raise QueryError("invalid_proposal", "Aportación o número de posiciones no válido.", 422)
        policy, revision = self._policy()
        table, rate, profile = self.ranking(), self.euros_per_dollar(), self._investor()
        if rate is None:
            raise QueryError("benchmark_prices_missing",
                             "Falta el cambio USDEUR=X en caché: pulsa «Actualizar benchmark» en Perfil y benchmark.",
                             409)
        target = target_portfolio(table, n_positions)
        if target.empty:
            raise QueryError("no_candidates", "No hay candidatas con score suficiente en la caché.", 409)
        candidates = [{"symbol": symbol, "price": _number(row.get("price")),
                       "daily_dollar_volume": self._dollar_volume(row.to_dict())} for symbol, row in target.iterrows()]
        kept, excluded = rules.eligible(candidates, policy)
        issuers = self.issuers(list(target.index))
        sectors = {symbol: _text(row.get("sector")) for symbol, row in target.iterrows()}
        held = {row["symbol"]: float(row["value_eur"]) for row in self.positions()
                if row["status"] == "ok" and row.get("value_eur")}
        prices = {symbol: (_number(row.get("price")) or 0.0) * rate for symbol, row in target.iterrows()}
        costs = {key: _number(profile.get(key)) or 0.0 for key in COST_KEYS}
        fractional = bool(profile.get("fractional", True))
        limited = rules.apply_limits([row["symbol"] for row in kept], issuers, sectors, policy)

        def alternative(label: str, weights: dict[str, float], cash: float) -> dict:
            exposure = rules.exposures(
                [{"symbol": symbol, "issuer": issuers.get(symbol, symbol), "value_eur": weight,
                  "sector": sectors.get(symbol), "industry": None, "listing_currency": "USD",
                  "economic_currency": "USD", "scores": {}, "daily_volume_eur": None}
                 for symbol, weight in weights.items() if weight > 0], policy, total_eur=1.0)
            orders = rules.contribution_orders(
                held, weights, contribution_eur, prices, dict.fromkeys(weights, "USD"),
                commission_fixed_eur=costs["commission_fixed_eur"], commission_pct=costs["commission_pct"],
                fx_cost_pct=costs["fx_cost_pct"], min_order_eur=costs["min_order_eur"], fractional=fractional,
                max_cost_share=policy.max_cost_share)
            ranked = sorted(weights.items(), key=lambda item: (-item[1], item[0]))
            return {"label": label, "weights": [{"symbol": symbol, "weight": weight} for symbol, weight in ranked],
                    "cash": cash, "issuers": exposure["issuers"][:5], "sectors": exposure["sectors"],
                    "breaches": exposure["breaches"], **orders}

        return {"as_of": self.today().isoformat(), "policy_version": policy.version, "policy_revision": revision,
                "n_positions": n_positions, "contribution_eur": contribution_eur, "euros_per_dollar": rate,
                "excluded": excluded, "outside_target": sorted(set(held) - set(target.index)),
                "alternatives": [alternative("Equiponderada (regla congelada)",
                                             {symbol: 1 / len(target) for symbol in target.index}, 0.0),
                                 alternative("Con los límites de la política", limited["weights"], limited["cash"])]}
