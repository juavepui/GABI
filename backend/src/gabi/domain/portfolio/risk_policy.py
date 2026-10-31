"""Issuer risk and an investable portfolio policy for small capital and contributions (#248).

A concentration warning does not limit exposure: this policy does, with caps by
issuer and sector, no leverage, an optional cash reserve and eligibility by
price and liquidity. Two share classes of one issuer are one risk. The policy
is versioned apart from the models; it never activates a real portfolio nor
sends orders. Comparing it with equal weight does not tune the number of
positions to rescue historical results.
"""

import math
from collections import defaultdict
from dataclasses import asdict, dataclass

POLICY_VERSION = "portfolio-policy-v1"
UNKNOWN = "Sin sector"
BLOCKS = ("value", "quality", "momentum", "risk")


@dataclass(frozen=True)
class Policy:
    max_issuer_weight: float = 0.10
    max_sector_weight: float = 0.30
    cash_weight: float = 0.0
    min_daily_dollar_volume: float = 5_000_000.0
    participation: float = 0.10  # Share of the daily volume one could trade without moving the price.
    max_cost_share: float = 0.01  # An order whose costs exceed this share of its amount is merged away.
    version: str = POLICY_VERSION


def validate_policy(raw: dict) -> Policy:
    """The stored policy, or ValueError with the reason in Spanish."""
    try:
        values = {key: float(raw[key]) for key in ("max_issuer_weight", "max_sector_weight")}
        values |= {key: float(raw.get(key, default)) for key, default in (
            ("cash_weight", 0.0), ("min_daily_dollar_volume", 5e6), ("participation", 0.10),
            ("max_cost_share", 0.01))}
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Los límites de la política deben ser números.") from exc
    if not (0 < values["max_issuer_weight"] <= 1 and 0 < values["max_sector_weight"] <= 1):
        raise ValueError("Los pesos máximos deben estar entre 0 % y 100 %.")
    if not 0 <= values["cash_weight"] < 1:
        raise ValueError("La caja debe estar entre 0 % y 100 %.")
    if not (0 <= values["min_daily_dollar_volume"] <= 1e12 and 0 < values["participation"] <= 1
            and 0 < values["max_cost_share"] <= 0.2):
        raise ValueError("Liquidez, participación o coste máximo fuera de rango.")
    return Policy(values["max_issuer_weight"], values["max_sector_weight"], values["cash_weight"],
                  values["min_daily_dollar_volume"], values["participation"], values["max_cost_share"])


def stored(policy: Policy) -> dict:
    values = asdict(policy)
    values.pop("version")
    return values


def _share(groups: dict[str, float], total: float) -> list[dict]:
    return sorted(({"name": name, "weight": value / total} for name, value in groups.items()),
                  key=lambda row: (-row["weight"], row["name"]))


def exposures(positions: list[dict], policy: Policy, *, total_eur: float | None = None) -> dict:
    """Weights by issuer, sector, industry, listing and economic currency, factor tilt and liquidity.

    Each position: symbol, issuer, value_eur, sector, industry, listing_currency,
    economic_currency, scores (block → 0–100 or None) and daily_volume_eur (or None).
    ``total_eur`` includes what is not in ``positions``, such as a cash reserve."""
    total = total_eur if total_eur is not None else sum(row["value_eur"] for row in positions)
    if total <= 0:
        return {"total_eur": 0.0, "issuers": [], "sectors": [], "industries": [], "listing_currency": [],
                "economic_currency": [], "factors": {}, "liquidity": [], "breaches": []}
    issuers: dict[str, dict] = {}
    groups: dict[str, dict[str, float]] = {key: defaultdict(float) for key in
                                           ("sectors", "industries", "listing_currency", "economic_currency")}
    for row in positions:
        issuer = issuers.setdefault(row["issuer"], {"issuer": row["issuer"], "symbols": [], "value_eur": 0.0})
        issuer["symbols"].append(row["symbol"])
        issuer["value_eur"] += row["value_eur"]
        groups["sectors"][row.get("sector") or UNKNOWN] += row["value_eur"]
        groups["industries"][row.get("industry") or UNKNOWN] += row["value_eur"]
        groups["listing_currency"][row["listing_currency"]] += row["value_eur"]
        groups["economic_currency"][row["economic_currency"]] += row["value_eur"]
    issuer_rows = sorted(({**row, "symbols": sorted(row["symbols"]), "weight": row["value_eur"] / total,
                           "exceeds": row["value_eur"] / total > policy.max_issuer_weight + 1e-9}
                          for row in issuers.values()), key=lambda row: -row["weight"])
    sectors = [{**row, "exceeds": row["weight"] > policy.max_sector_weight + 1e-9}
               for row in _share(groups["sectors"], total)]
    factors = {}
    for block in BLOCKS:
        known = [(row["value_eur"], row["scores"].get(block)) for row in positions
                 if row.get("scores", {}).get(block) is not None]
        weight = sum(value for value, _ in known)
        factors[block] = {"score": sum(value * score for value, score in known) / weight if weight else None,
                          "coverage": weight / total}
    liquidity = []
    for row in positions:
        volume = row.get("daily_volume_eur")
        days = row["value_eur"] / (volume * policy.participation) if volume else None
        liquidity.append({"symbol": row["symbol"], "value_eur": row["value_eur"], "daily_volume_eur": volume,
                          "days_to_trade": days, "illiquid": days is None or days > 1})
    breaches = ([f"Emisor {row['issuer']} ({', '.join(row['symbols'])}) pesa {row['weight']:.1%}"
                 for row in issuer_rows if row["exceeds"]]
                + [f"Sector {row['name']} pesa {row['weight']:.1%}" for row in sectors if row["exceeds"]])
    return {"total_eur": total, "issuers": issuer_rows, "sectors": sectors,
            "industries": _share(groups["industries"], total),
            "listing_currency": _share(groups["listing_currency"], total),
            "economic_currency": _share(groups["economic_currency"], total),
            "factors": factors, "liquidity": sorted(liquidity, key=lambda row: -(row["days_to_trade"] or math.inf)),
            "breaches": breaches}


def eligible(candidates: list[dict], policy: Policy) -> tuple[list[dict], list[dict]]:
    """Candidates with a price and enough daily dollar volume; the rest with their reason."""
    keep, excluded = [], []
    for row in candidates:
        if not row.get("price"):
            excluded.append({"symbol": row["symbol"], "reason": "no_price"})
        elif (row.get("daily_dollar_volume") or 0) < policy.min_daily_dollar_volume:
            excluded.append({"symbol": row["symbol"], "reason": "illiquid"})
        else:
            keep.append(row)
    return keep, excluded


def apply_limits(symbols: list[str], issuers: dict[str, str], sectors: dict[str, str | None],
                 policy: Policy) -> dict:
    """Equal weights within the invested share, capped by issuer and sector; what cannot be placed is cash.

    The excess of a capped group goes pro rata to the positions whose issuer and
    sector still have room. Weights plus cash add up to exactly 1: no leverage."""
    invested = 1 - policy.cash_weight
    weights = {symbol: invested / len(symbols) for symbol in symbols} if symbols else {}
    capped: set[str] = set()
    issuer_of = {symbol: issuers.get(symbol, symbol) for symbol in symbols}
    sector_of = {symbol: sectors.get(symbol) or UNKNOWN for symbol in symbols}
    for _ in range(100):
        moved = False
        for group_of, cap in ((issuer_of, policy.max_issuer_weight), (sector_of, policy.max_sector_weight)):
            groups: dict[str, list[str]] = defaultdict(list)
            for symbol in weights:
                groups[group_of[symbol]].append(symbol)
            for members in groups.values():
                total = sum(weights[symbol] for symbol in members)
                if total > cap + 1e-12:
                    for symbol in members:
                        weights[symbol] *= cap / total
                    capped.update(members)
                    moved = True
        free = invested - sum(weights.values())
        room = [symbol for symbol in weights if symbol not in capped]
        if free > 1e-12 and room:
            base = sum(weights[symbol] for symbol in room)
            for symbol in room:
                weights[symbol] += free * weights[symbol] / base
            moved = True
        if not moved:
            break
    cash = 1 - sum(weights.values())
    return {"weights": weights, "cash": cash, "capped": sorted(capped)}


def contribution_orders(current: dict[str, float], targets: dict[str, float], contribution_eur: float,
                        prices_eur: dict[str, float], currencies: dict[str, str], *, commission_fixed_eur: float,
                        commission_pct: float, fx_cost_pct: float, min_order_eur: float, fractional: bool,
                        max_cost_share: float) -> dict:
    """Buy orders that move the portfolio toward ``targets`` with new money only: no sales.

    The largest gaps are funded first. An order below the broker minimum, or whose
    costs exceed ``max_cost_share`` of its amount, is dropped and its money goes to
    the remaining gaps: fewer, larger orders cost less. What whole shares or
    dropped orders leave is residual cash."""
    future = sum(current.values()) + contribution_eur
    gaps = {symbol: weight * future - current.get(symbol, 0.0) for symbol, weight in targets.items()}
    funded = sorted((symbol for symbol, gap in gaps.items() if gap > 0.005 and prices_eur.get(symbol)),
                    key=lambda symbol: -gaps[symbol])

    def costs(symbol: str, amount: float) -> tuple[float, float]:
        commission = commission_fixed_eur + amount * commission_pct
        fx = (amount - commission) * fx_cost_pct if currencies.get(symbol, "EUR") != "EUR" else 0.0
        return commission, fx

    amounts: dict[str, float] = {}
    while funded:
        need = sum(gaps[symbol] for symbol in funded)
        amounts = {symbol: contribution_eur * gaps[symbol] / need if need > contribution_eur else gaps[symbol]
                   for symbol in funded}
        worst = min(funded, key=lambda symbol: amounts[symbol])
        commission, fx = costs(worst, amounts[worst])
        if amounts[worst] < min_order_eur or (commission + fx) > max_cost_share * amounts[worst]:
            funded.remove(worst)
            continue
        break
    orders: list[dict] = []
    remaining, total_costs = contribution_eur, 0.0
    for symbol in funded:
        amount = min(amounts[symbol], remaining)
        commission, fx = costs(symbol, amount)
        price = prices_eur[symbol]
        investable = max(amount - commission - fx, 0.0)
        shares = investable / price if fractional else math.floor(investable / price + 1e-9)
        if shares <= 0:
            continue
        spent = shares * price + commission + fx
        remaining -= spent
        total_costs += commission + fx
        orders.append({"symbol": symbol, "shares": shares, "amount_eur": shares * price, "commission_eur": commission,
                       "fx_cost_eur": fx, "gap_eur": gaps[symbol]})
    return {"orders": orders, "residual_cash_eur": remaining, "costs_eur": total_costs,
            "unfunded": sorted(symbol for symbol, gap in gaps.items()
                               if gap > 0.005 and symbol not in {row["symbol"] for row in orders})}


def stress(positions: list[dict], loss_tolerance: float, *, market: float = -0.20, euro: float = 0.10) -> dict:
    """A market fall through each beta, the same fall with correlations at 1, the euro and illiquidity.

    Each position: value_eur, beta (or None → 1), economic_currency, days_to_trade."""
    total = sum(row["value_eur"] for row in positions)
    if total <= 0:
        return {"scenarios": [], "notes": []}

    def change(of) -> float:
        return sum(row["value_eur"] * of(row) for row in positions) / total

    dollar = sum(row["value_eur"] for row in positions if row["economic_currency"] == "USD") / total
    euro_effect = dollar * (1 / (1 + euro) - 1)
    rows = [
        ("market_beta", f"Mercado {market:.0%} a través de la beta de cada posición",
         change(lambda row: market * (row.get("beta") if row.get("beta") is not None else 1.0))),
        ("market_correlated", f"Mercado {market:.0%} con correlaciones en 1: la diversificación desaparece",
         market),
        ("euro", f"El euro sube un {euro:.0%} frente al dólar", euro_effect),
        ("combined", "Mercado correlacionado y euro al alza a la vez", (1 + market) * (1 + euro_effect) - 1),
    ]
    slow = [row for row in positions if row.get("days_to_trade") is None or row["days_to_trade"] > 1]
    notes = [
        f"El {loss_tolerance:.0%} es un umbral de revisión: una caída de apertura o una posición ilíquida pueden "
        "superarlo antes de poder actuar, y GABI nunca vende por sí solo.",
    ]
    if slow:
        notes.append(f"{len(slow)} posiciones tardarían más de una sesión en venderse sin mover el precio.")
    return {"scenarios": [{"id": key, "label": label, "change": value, "change_eur": value * total,
                           "exceeds_tolerance": value <= -loss_tolerance} for key, label, value in rows],
            "notes": notes}
