"""SEC issuer evidence for attributing 2010-2015 price series (issue #28).

Three kinds of free, archived SEC evidence are used, each cached with its URL
and SHA-256 through ``sec_history.download``:

- submissions JSON: listing life of a CIK (first periodic report, holding
  company successions, delisting/deregistration followed by silence);
- XBRL frames for ``dei:EntityPublicFloat`` and share counts: an independent
  price *level* at the float date, which ties a price series to one issuer;
- XBRL frames for dividends per share: the cash events a split/dividend
  adjusted series must contain.

Nothing here decides a tier. ``historical_price_audit`` combines the checks and
fails closed when evidence is missing or contradictory.
"""

import argparse
import html
import json
import re
from datetime import date, timedelta
from functools import cache
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import identity, sec_history

DIRECTORY = sec_history.DIRECTORY
FRAMES_DIR = DIRECTORY / "frames"
SUBMISSIONS_DIR = DIRECTORY / "identity_submissions"
FRAME_URL = "https://data.sec.gov/api/xbrl/frames/{taxonomy}/{tag}/{unit}/{period}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/{name}"
FRAME_SPECS = {
    "public_float": ("dei", "EntityPublicFloat", "USD", True),
    "cover_shares": ("dei", "EntityCommonStockSharesOutstanding", "shares", True),
    "weighted_shares": ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic", "shares", False),
    "dividends_declared": ("us-gaap", "CommonStockDividendsPerShareDeclared", "USD-per-shares", False),
    "dividends_paid": ("us-gaap", "CommonStockDividendsPerShareCashPaid", "USD-per-shares", False),
    # Annual cash-flow payments: detects payers that never tag per-share values.
    "dividend_payments": ("us-gaap", "PaymentsOfDividendsCommonStock", "USD", False),
}
PERIODS = [f"CY{year}Q{quarter}" for year in range(2008, 2017) for quarter in range(1, 5)]
ANNUAL_PERIODS = [f"CY{year}" for year in range(2008, 2017)]


def _periods(kind: str) -> list[str]:
    return ANNUAL_PERIODS if kind == "dividend_payments" else PERIODS
PERIODIC_FORMS = {"10-K", "10-Q", "10-K405", "10-KT", "20-F", "40-F", "10-KSB", "10-QSB"}
SUCCESSION_FORMS = {"8-K12B", "8-K12G3", "8-K12B/A", "8-K12G3/A"}
DELISTING_FORMS = {"25", "25-NSE", "15-12B", "15-12G", "15-15D"}
# Offerings and exchange registrations that can open an equity's trading life.
REGISTRATION_FORMS = {"10-12B", "10-12B/A", "10-12G", "10-12G/A", "S-1", "S-1/A", "F-1", "F-1/A",
                      "424B1", "424B4", "8-A12B", "8-A12G", "S-4", "S-4/A", "F-4", "F-4/A"}
# A delisting/deregistration only ends the equity's trading life when the
# issuer then stops filing periodic reports; debt or preferred delistings and
# exchange transfers are followed by further 10-Q/10-K reports.
SILENCE_DAYS = 150
# Public float is held by non-affiliates, so float / (shares x close) is below
# one; controlled issuers go lower, and cover share counts are dated months
# after the float. Outside this band the price cannot be the issuer's
# as-traded price at the float date (another security, wrong split basis).
LEVEL_RATIO_LOW = 0.25
LEVEL_RATIO_HIGH = 1.5
CLEAN_SPLITS = (2, 3, 4, 5, 7, 10, 1.5, 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 10)
# Larger one-day cash factors are spin-offs/special distributions whose value
# is not a verifiable cash dividend; they block an unreconciled window.
MAX_DIVIDEND_YIELD = 0.10


def _frame_path(kind: str, period: str) -> tuple[str, Path]:
    taxonomy, tag, unit, instant = FRAME_SPECS[kind]
    suffix = "I" if instant else ""
    url = FRAME_URL.format(taxonomy=taxonomy, tag=tag, unit=unit, period=period + suffix)
    return url, FRAMES_DIR / f"{taxonomy}_{tag}_{unit}_{period}{suffix}.json"


def fetch_frames() -> dict:
    """Cache every quarterly frame used by the checks (idempotent)."""
    fetched = cached = missing = 0
    for kind in FRAME_SPECS:
        for period in _periods(kind):
            url, path = _frame_path(kind, period)
            if path.exists():
                cached += 1
                continue
            try:
                sec_history.download(url, path)
                fetched += 1
            except requests.HTTPError as exc:
                # SEC returns 404 for frames without facts; record, never invent.
                if exc.response is not None and exc.response.status_code == 404:
                    missing += 1
                    continue
                raise
    return {"fetched": fetched, "cached": cached, "not_published": missing}


def fetch_submissions(ciks: set[str]) -> dict:
    """Cache SEC submissions, including older pages that overlap 2008-2016."""
    fetched = cached = failed = 0
    for cik in sorted(identity.normalize_cik(value) for value in ciks):
        path = SUBMISSIONS_DIR / f"CIK{cik}.json"
        try:
            if path.exists():
                cached += 1
            else:
                sec_history.download(SUBMISSIONS_URL.format(name=f"CIK{cik}.json"), path)
                fetched += 1
            payload = json.loads(path.read_text(encoding="utf-8"))
            if identity.normalize_cik(payload["cik"]) != cik:
                raise ValueError("SEC submissions issuer CIK mismatch")
            for page in payload.get("filings", {}).get("files", []):
                if page.get("filingFrom", "9999") > "2017-01-01" or page.get("filingTo", "0000") < "2008-01-01":
                    continue
                extra = SUBMISSIONS_DIR / page["name"]
                if not extra.exists():
                    sec_history.download(SUBMISSIONS_URL.format(name=page["name"]), extra)
                    fetched += 1
        except (requests.RequestException, OSError, ValueError, KeyError) as exc:
            failed += 1
            print(f"SEC submissions failed {cik}: {exc}", flush=True)
    return {"ciks": len(ciks), "fetched_files": fetched, "cached": cached, "failed": failed}


@cache
def load_frames() -> dict[str, dict[str, list[dict]]]:
    """Index cached frames by CIK. Missing files simply contribute nothing."""
    result: dict[str, dict[str, list[dict]]] = {}
    for kind in FRAME_SPECS:
        for period in _periods(kind):
            url, path = _frame_path(kind, period)
            if not path.exists():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            for row in payload.get("data", []):
                cik = identity.normalize_cik(str(row["cik"]))
                result.setdefault(cik, {}).setdefault(kind, []).append(
                    {**{key: row.get(key) for key in ("accn", "start", "end", "val")},
                     "frame": payload.get("ccp"), "source_url": url})
    return result


def issuer_facts(cik: str) -> dict[str, list[dict]]:
    facts = load_frames().get(identity.normalize_cik(cik), {})
    return {kind: sorted(facts.get(kind, []), key=lambda row: row["end"]) for kind in FRAME_SPECS}


@cache
def listing_life(cik: str) -> dict | None:
    """Summarise when a CIK's common equity can have traded, from SEC filings."""
    cik = identity.normalize_cik(cik)
    path = SUBMISSIONS_DIR / f"CIK{cik}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    pages = [payload["filings"]["recent"]]
    for page in payload["filings"].get("files", []):
        extra = SUBMISSIONS_DIR / page["name"]
        if extra.exists():
            pages.append(json.loads(extra.read_text(encoding="utf-8")))
        elif page.get("filingFrom", "9999") <= "2017-01-01" and page.get("filingTo", "0000") >= "2008-01-01":
            return None  # an overlapping page is missing: never judge on partial history
    filings = sorted({(form, filed, accn) for page in pages
                      for form, filed, accn in zip(page["form"], page["filingDate"],
                                                   page["accessionNumber"], strict=True)},
                     key=lambda row: row[1])
    current_reports = sorted({(filed, accn, items, primary) for page in pages
                              for form, filed, accn, items, primary in zip(
                                  page["form"], page["filingDate"], page["accessionNumber"],
                                  page["items"], page["primaryDocument"], strict=True)
                              if form in {"8-K", "8-K/A"} and "2009-01-01" <= filed < "2017-01-01"})
    succession_reports = {accn: primary for page in pages
                          for form, accn, primary in zip(page["form"], page["accessionNumber"],
                                                         page["primaryDocument"], strict=True)
                          if form in SUCCESSION_FORMS}
    annual_reports = sorted({(filed, accn, primary) for page in pages
                             for form, filed, accn, primary in zip(
                                 page["form"], page["filingDate"], page["accessionNumber"],
                                 page["primaryDocument"], strict=True)
                             if form == "10-K" and "2009-01-01" <= filed < "2017-01-01"})
    periodic = [filed for form, filed, _ in filings if form in PERIODIC_FORMS]
    floats = [row["end"] for row in issuer_facts(cik)["public_float"] if row["val"] and row["val"] > 0]
    delisting = None
    for form, filed, accn in filings:
        if form not in DELISTING_FORMS or filed < "2008-01-01":
            continue
        horizon = (date.fromisoformat(filed) + timedelta(days=SILENCE_DAYS)).isoformat()
        silent = not any(filed < later <= horizon for later in periodic)
        # Debt registrants keep filing after a buyout; their equity no longer
        # has a public float. Frames end in 2016, so later events stay open.
        floatless = filed < "2016-01-01" and not any(day > filed for day in floats)
        if silent or floatless:
            delisting = {"form": form, "filed": filed, "accession": accn,
                         "basis": "filing_silence" if silent else "no_later_public_float"}
            break
    return {"cik": cik, "name": payload.get("name"),
            "former_names": [row.get("name") for row in payload.get("formerNames", [])],
            "current_tickers": payload.get("tickers", []),
            "first_periodic": periodic[0] if periodic else None,
            "last_periodic": periodic[-1] if periodic else None,
            "registrations": [{"form": form, "filed": filed, "accession": accn}
                              for form, filed, accn in filings if form in REGISTRATION_FORMS],
            "successions": [{"form": form, "filed": filed, "accession": accn,
                             "primary": succession_reports.get(accn)}
                            for form, filed, accn in filings if form in SUCCESSION_FORMS],
            "delisting": delisting,
            "current_reports": [{"filed": filed, "accession": accn, "items": items, "primary": primary}
                                for filed, accn, items, primary in current_reports],
            "annual_reports": [{"filed": filed, "accession": accn, "primary": primary}
                               for filed, accn, primary in annual_reports],
            "source_url": f"https://data.sec.gov/submissions/CIK{cik}.json"}


def listing_checks(life: dict | None, start: str, end: str) -> tuple[str | None, list[dict]]:
    """Reject windows outside the SEC-evidenced life of the issuer's equity.

    ``start``/``end`` are the first and last sessions of the price window.
    Returns a failure reason (or None) and the evidence references used.
    """
    if life is None:
        return "listing_life_unavailable", []
    refs = [{"kind": "first_trade", "source_url": life["source_url"], "date": life["first_periodic"],
             "basis": "first SEC periodic report of the CIK; the equity was registered by then"}]
    if not life["first_periodic"] or life["first_periodic"] > start:
        return "listing_starts_after_window", refs
    for event in life["successions"]:
        if start < event["filed"] <= end:
            refs.append({"kind": "corporate_actions", "source_url": life["source_url"], **event})
            return "succession_inside_window", refs
    delisting = life["delisting"]
    refs.append({"kind": "last_trade", "source_url": life["source_url"],
                 "date": delisting["filed"] if delisting else life["last_periodic"],
                 "basis": f"Form {delisting['form']} then {delisting['basis']}" if delisting else
                 "no equity delisting through the latest SEC periodic report",
                 **({"form": delisting["form"], "accession": delisting["accession"]} if delisting else {})})
    if delisting and delisting["filed"] <= end:
        return "delisted_before_window_end", refs
    return None, refs


def listing_start(life: dict | None, first_observation: str) -> dict | None:
    """SEC registration that opens a short trading history at ``first_observation``.

    An IPO prospectus, Form 10 or exchange registration filed in the 180 days
    before the first observed session supports that the series starts at the
    real listing rather than truncating older data.
    """
    if life is None:
        return None
    first = date.fromisoformat(first_observation)
    matches = [row for row in life["registrations"]
               if 0 <= (first - date.fromisoformat(row["filed"])).days <= 180]
    if not matches:
        return None
    return {"kind": "first_trade", "source_url": life["source_url"], "date": first_observation,
            "basis": "series starts after SEC registration", **matches[-1]}


def _price_on(close: pd.Series, day: str) -> tuple[str, float] | None:
    """Last observed as-traded close on or up to five days before ``day``."""
    target = pd.Timestamp(day)
    window = close.loc[target - pd.Timedelta(days=5):target].dropna()
    if window.empty or window.iloc[-1] <= 0:
        return None
    return window.index[-1].date().isoformat(), float(window.iloc[-1])


def _shares_near(facts: dict[str, list[dict]], day: str) -> tuple[float, dict] | None:
    """Cover share count closest to the float date (cover counts are never
    restated), else basic weighted shares for the quarter ending there; frames
    serve the latest filing, so weighted counts may be restated for splits."""
    target = date.fromisoformat(day)
    candidates = [row for row in facts["cover_shares"] if row["val"] and row["val"] > 0 and
                  -30 <= (date.fromisoformat(row["end"]) - target).days <= 270]
    if candidates:
        row = min(candidates, key=lambda item: abs((date.fromisoformat(item["end"]) - target).days))
        return float(row["val"]), {**row, "kind": "cover_shares"}
    for row in facts["weighted_shares"]:
        if not row.get("start"):
            continue
        end, begin = date.fromisoformat(row["end"]), date.fromisoformat(row["start"])
        if abs((end - target).days) <= 10 and 80 <= (end - begin).days <= 100 and row["val"] > 0:
            return float(row["val"]), {**row, "kind": "weighted_shares"}
    return None


def classify_level(ratio: float, *, restated_shares: bool = False) -> str:
    """``passed`` inside the band; ``inconclusive`` for gaps of more than two
    orders of magnitude (XBRL unit errors) or, only for share counts that SEC
    frames may restate, a clean split factor; otherwise ``failed``: the close
    belongs to another basis or security."""
    if LEVEL_RATIO_LOW <= ratio <= LEVEL_RATIO_HIGH:
        return "passed"
    if not 0.01 <= ratio <= 100:
        return "inconclusive"  # a unit error in the SEC fact, not a price
    if restated_shares:
        for factor in (*CLEAN_SPLITS, 20, 1 / 20):
            for scaled in (ratio / factor, ratio * factor):
                if LEVEL_RATIO_LOW <= scaled <= LEVEL_RATIO_HIGH:
                    return "inconclusive"
    return "failed"


def level_status(checks: list[dict]) -> str:
    """A window needs one independent pass and no unexplained failure."""
    outcomes = {check["outcome"] for check in checks}
    if "failed" in outcomes:
        return "failed"
    return "passed" if "passed" in outcomes else "missing"


def level_horizon(life: dict | None, end: str) -> str:
    """Latest float date usable for a window ending at ``end``: up to 400 days
    later, but never past a succession or delisting of the CIK."""
    horizon = date.fromisoformat(end) + timedelta(days=400)
    for event in (life or {}).get("successions", []) + ([life["delisting"]] if life and life["delisting"] else []):
        filed = date.fromisoformat(event["filed"])
        if filed > date.fromisoformat(end):
            horizon = min(horizon, filed - timedelta(days=1))
    return horizon.isoformat()


def price_level_checks(facts: dict[str, list[dict]], close: pd.Series, start: str, end: str,
                       *, until: str | None = None, splits: pd.Series | None = None) -> list[dict]:
    """Compare as-traded closes with SEC float / shares at each float date.

    Float dates from ~6 months before the window up to ``until`` (default its
    end) are used. A later date extends the check to issuers whose first XBRL
    float comes after the window; the caller must guarantee that the same
    listing continues until then (no succession or delisting). ``splits``
    (ratio by ex-date) converts a cover share count dated after a split back
    to the float date; unknown splits make the check fail, never pass.
    """
    lower = (date.fromisoformat(start) - timedelta(days=200)).isoformat()
    upper = until or end
    checks = []
    for row in facts["public_float"]:
        if not (lower <= row["end"] <= upper) or not row["val"] or row["val"] <= 0:
            continue
        price = _price_on(close, row["end"])
        shares = _shares_near(facts, row["end"])
        if price is None or shares is None:
            continue
        count = shares[0]
        if splits is not None and not splits.empty and shares[1]["kind"] == "cover_shares":
            between = splits[(splits.index > pd.Timestamp(row["end"])) &
                             (splits.index <= pd.Timestamp(shares[1]["end"]))]
            count /= float(between.prod()) if not between.empty else 1.0
        ratio = row["val"] / (count * price[1])
        restated = shares[1]["kind"] == "weighted_shares"
        checks.append({"kind": "price_level", "float_date": row["end"], "public_float": row["val"],
                       "float_accession": row["accn"], "source_url": row["source_url"],
                       "shares": count, "shares_kind": shares[1]["kind"],
                       "shares_source_url": shares[1]["source_url"], "price_date": price[0],
                       "close": price[1], "ratio": ratio,
                       "outcome": classify_level(ratio, restated_shares=restated)})
    return checks


def implied_events(frame: pd.DataFrame) -> pd.DataFrame:
    """Split and cash-distribution events implied by close vs adjusted close.

    For a split/dividend adjusted series, ``adj_t/adj_{t-1}`` differs from
    ``close_t/close_{t-1}`` only on ex-dates. A cash dividend D implies a
    factor 1/(1-D/close_{t-1}); a split implies a clean close ratio with a
    continuous adjusted series.
    """
    data = frame[["close", "adj_close"]].astype(float)
    close_ratio = data["close"] / data["close"].shift()
    adj_ratio = data["adj_close"] / data["adj_close"].shift()
    factor = adj_ratio / close_ratio
    rows = []
    for day, value in factor.dropna().items():
        if not np.isfinite(value) or abs(value - 1) < 2e-4:
            continue
        clean = [ratio for ratio in CLEAN_SPLITS if abs(value / ratio - 1) < 0.03]
        if clean:
            rows.append({"date": day, "kind": "split", "ratio": clean[0], "factor": value})
            continue
        previous = data["close"].shift().loc[day]
        amount = previous * (1 - 1 / value)
        kind = "dividend" if 0 < amount < MAX_DIVIDEND_YIELD * previous else "unexplained"
        rows.append({"date": day, "kind": kind, "amount": amount, "factor": value})
    return pd.DataFrame(rows, columns=["date", "kind", "ratio", "amount", "factor"])


def verify_splits(events: pd.DataFrame, facts: dict[str, list[dict]]) -> tuple[bool, list[dict]]:
    """A split must match the change in SEC cover share counts around it."""
    refs: list[dict] = []
    splits = events[events.kind == "split"] if not events.empty else events
    for row in splits.itertuples(index=False):
        day = row.date.date()
        before = [item for item in facts["cover_shares"] if item["val"] and
                  0 < (day - date.fromisoformat(item["end"])).days <= 400]
        after = [item for item in facts["cover_shares"] if item["val"] and
                 0 <= (date.fromisoformat(item["end"]) - day).days <= 400]
        if not before or not after:
            return False, refs
        change = max(after, key=lambda item: -abs((date.fromisoformat(item["end"]) - day).days))["val"] / \
            max(before, key=lambda item: -abs((date.fromisoformat(item["end"]) - day).days))["val"]
        refs.append({"kind": "adjustment", "event": "split", "date": day.isoformat(), "ratio": row.ratio,
                     "sec_cover_share_change": change,
                     "source_url": facts["cover_shares"][0]["source_url"]})
        if not 0.8 * row.ratio <= change <= 1.25 * row.ratio:
            return False, refs
    return True, refs


def reconcile_dividends(events: pd.DataFrame, facts: dict[str, list[dict]],
                        start: str, end: str) -> tuple[str, dict]:
    """Match implied cash events with SEC per-share dividends for the window.

    SEC periods are fiscal and declarations precede ex-dates, so totals are
    compared over the SEC quarters that end inside the window, allowing one
    quarter of timing slack. Issuers that only tag annual per-share values are
    compared with the fiscal year ending in the last half of the window.
    ``fingerprint`` marks windows whose individual cash events match SEC
    amounts: issuer-specific evidence that the series belongs to that CIK.
    """
    implied = events[events.kind == "dividend"] if not events.empty else events
    unexplained = events[events.kind == "unexplained"] if not events.empty else events
    if not unexplained.empty:
        return "unexplained_adjustment", {"dates": [d.date().isoformat() for d in unexplained.date]}
    quarterly: dict[str, float] = {}
    annual: dict[str, float] = {}
    for kind in ("dividends_declared", "dividends_paid"):
        for row in facts[kind]:
            if not row.get("start") or row["val"] is None:
                continue
            days = (date.fromisoformat(row["end"]) - date.fromisoformat(row["start"])).days
            if 80 <= days <= 100 and start < row["end"] <= end:
                quarterly.setdefault(row["end"], float(row["val"]))
            elif 350 <= days <= 380 and start < row["end"] <= end:
                annual.setdefault(row["end"], float(row["val"]))
    amounts = [float(value) for value in implied.amount] if not implied.empty else []
    total_implied = float(sum(amounts))
    detail: dict = {"implied_events": len(amounts), "implied_total": total_implied,
                    "sec_quarters": len(quarterly), "sec_total": float(sum(quarterly.values())),
                    "fingerprint": False}
    if not quarterly and annual:
        latest = max(annual)
        detail.update(sec_annual_end=latest, sec_annual=annual[latest])
        midpoint = date.fromisoformat(start) + (date.fromisoformat(end) - date.fromisoformat(start)) / 2
        if date.fromisoformat(latest) >= midpoint:
            if annual[latest] == 0:
                return ("no_dividends_consistent" if not amounts else "dividend_mismatch"), detail
            ok = amounts and abs(total_implied - annual[latest]) <= max(0.35 * annual[latest], 0.02)
            return ("dividends_reconciled" if ok else "dividend_mismatch"), detail
    if not quarterly:
        return ("no_dividends_consistent" if not amounts and _reports_no_dividend(facts, start, end)
                else "sec_dividends_unavailable"), detail
    sec_total = detail["sec_total"]
    if sec_total == 0:
        return ("no_dividends_consistent" if not amounts else "dividend_mismatch"), detail
    slack = max(quarterly.values())
    detail["slack"] = slack
    matched = sum(any(abs(amount - value) <= max(0.01, 0.03 * value) for value in quarterly.values() if value > 0)
                  for amount in amounts)
    detail.update(matched_events=matched,
                  fingerprint=matched >= 2 and matched >= 0.75 * len(amounts))
    if abs(total_implied - sec_total) <= slack + 0.02 and amounts:
        return "dividends_reconciled", detail
    return "dividend_mismatch", detail


def _reports_no_dividend(facts: dict[str, list[dict]], start: str, end: str) -> bool:
    """No cash dividend in the window according to SEC.

    Either SEC reports explicit zeros, or the issuer filed XBRL covering the
    window (public float or cover shares) while reporting neither a per-share
    dividend nor annual dividend payments for any overlapping period.
    """
    lower = (date.fromisoformat(start) - timedelta(days=370)).isoformat()
    per_share = [row["val"] for kind in ("dividends_declared", "dividends_paid") for row in facts[kind]
                 if start < row["end"] <= end]
    payments = [row["val"] for row in facts.get("dividend_payments", []) if lower < row["end"] <= end]
    if any(value for value in per_share + payments):
        return False
    if per_share or payments:
        return True
    filed_xbrl = any(start <= row["end"] <= end for kind in ("public_float", "cover_shares") for row in facts[kind])
    return filed_xbrl


ANNUAL_DIR = DIRECTORY / "annual_reports"
# Item 5 of a 10-K states where and under which symbol the equity trades.
SYMBOL_RE = re.compile(r"under\s+the\s+(?:ticker\s+|trading\s+|stock\s+)?symbols?\s*[:\-]?\s*"
                       r"[\"“”'‘’]?\s*([A-Z]{1,5}(?:[.\-][A-Z]{1,2})?)\b")


def annual_report_symbols(document: str) -> set[str]:
    """Trading symbols a 10-K states for its listed equity ("under the symbol X")."""
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", document)))
    return {match.group(1) for match in SYMBOL_RE.finditer(text)}


def fetch_annual_report(cik: str, report: dict) -> tuple[str, Path]:
    url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
           f"{report['accession'].replace('-', '')}/{report['primary']}")
    return url, sec_history.download(url, ANNUAL_DIR / f"{report['accession']}_{Path(report['primary']).name}")


TERMINAL_DIR = DIRECTORY / "terminal_8k"
TERMINAL_ITEMS = {"1.03", "2.01", "3.01", "5.01"}
RECEIVE_RE = re.compile(r"right to receive", re.I)
CASH_RE = re.compile(r"\$\s?(\d{1,4}(?:,\d{3})*(?:\.\d{1,4})?)(?:\s+per\s+share)?,?\s+in\s+cash", re.I)
STOCK_RE = re.compile(r"\b(\d+\.\d+)\s+(?:of\s+a\s+|of\s+one\s+)?(?:validly\s+issued,?\s+)?(?:fully\s+paid\s+"
                      r"and\s+non-?assessable\s+)?shares?\s+of\s+(.{0,120}?)\bcommon\s+(?:stock|shares)", re.I)
# Non-cash components next to a cash amount: shares (common or ordinary),
# contingent value rights, elections.
MIXED_RE = re.compile(r"\bshares?\s+of\b|\bof\s+an?\s+[^.;]{0,50}?\b(?:share|stock)\b|ordinary\s+shares?"
                      r"|contingent\s+value|\bCVRs?\b|\belect", re.I)
ELECTION_RE = re.compile(r"\belect(?:ion|ed|s)?\b[^.;]{0,120}\b(?:cash|stock)\b", re.I)


ONE_FOR_ONE_RE = re.compile(
    r"(?:converted\s+(?:automatically\s+)?into|exchanged\s+for|became)[^.;]{0,160}?\bone\b[^.;]{0,80}?\bshares?\b"
    r"|one[-\s]for[-\s]one|\b1[-\s]for[-\s]1\b", re.I)


def one_for_one_quote(document: str) -> str | None:
    """Sentence of a succession 8-K12B stating a one-for-one share exchange."""
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", document)))
    match = ONE_FOR_ONE_RE.search(text)
    return text[max(0, match.start() - 120):match.end() + 60] if match else None


def completion_reports(life: dict, event_day: str) -> list[dict]:
    """8-Ks around a delisting that report completion, delisting or bankruptcy."""
    day = date.fromisoformat(event_day)
    rows = [row for row in life["current_reports"]
            if -45 <= (date.fromisoformat(row["filed"]) - day).days <= 10 and
            TERMINAL_ITEMS & set(row["items"].split(","))]
    return sorted(rows, key=lambda row: abs((date.fromisoformat(row["filed"]) - day).days))


def fetch_report(cik: str, report: dict) -> tuple[str, Path]:
    url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
           f"{report['accession'].replace('-', '')}/{report['primary']}")
    return url, sec_history.download(url, TERMINAL_DIR / f"{report['accession']}_{Path(report['primary']).name}")


def extract_terms(document: str) -> dict:
    """Consideration stated in a completion 8-K; never inferred from prices.

    Returns every cash amount and exchange ratio quoted after "right to
    receive", with the matched sentence as evidence. Elections, several
    amounts or mixed consideration are left for explicit review.
    """
    text = html.unescape(re.sub(r"<[^>]+>", " ", document))
    text = re.sub(r"\s+", " ", text)
    cash: list[tuple[float, str]] = []
    stock: list[tuple[float, str, str]] = []
    mixed = False
    for anchor in RECEIVE_RE.finditer(text):
        # Terms follow the phrase closely; a fixed window tolerates the
        # periods inside ratios ("0.2240") and names ("Corp.").
        window = text[anchor.start():anchor.end() + 260]
        for match in CASH_RE.finditer(window):
            cash.append((float(match.group(1).replace(",", "")), window))
            # The clause that carries the amount: up to its defined term,
            # sentence or list end. Any other component makes it mixed.
            tail = window[match.end():match.end() + 80]
            cut = min([index for index in (tail.find(". "), tail.find("(the"), tail.find("(“"), tail.find(";"))
                       if index >= 0], default=len(tail))
            clause = window[:match.end()] + tail[:cut]
            mixed = mixed or bool(MIXED_RE.search(clause)) or "(i)" in window[:match.start()]
        stock += [(float(match.group(1)), match.group(2).strip(), window) for match in STOCK_RE.finditer(window)]
    return {"cash": sorted({value for value, _ in cash}), "stock": sorted({(ratio, issuer) for ratio, issuer, _ in stock}),
            "mixed": mixed or bool(re.search(r"contingent value right", text, re.I)),
            "election": bool(ELECTION_RE.search(text)),
            "bankruptcy": bool(re.search(r"\bchapter 11\b|\bbankruptcy\b", text, re.I)),
            "quotes": [quote for _, quote in cash][:3] + [quote for *_, quote in stock][:3]}


def classify_terminal(items: set[str], terms: dict) -> tuple[str, str, dict]:
    """(event_type, status, economic fields) from SEC items and quoted terms."""
    if "1.03" in items:
        return "bankruptcy_liquidation", "terminal_return_unknown", {}
    if terms["election"] or terms.get("mixed") or len(terms["cash"]) > 1 or len(terms["stock"]) > 1:
        return "merger", "terminal_return_unknown", {}
    if terms["cash"] and not terms["stock"]:
        return "cash_acquisition", "terminal_return_confirmed", {"cash_per_share": terms["cash"][0]}
    if terms["stock"]:
        # Stock consideration needs the successor's attributed closing price;
        # it is recorded but never collapsed into the target's last price.
        return ("merger" if terms["cash"] else "stock_acquisition"), "terminal_return_unknown", {
            "exchange_ratio": terms["stock"][0][0], "cash_per_share": terms["cash"][0] if terms["cash"] else None}
    return "delisting", "terminal_return_unknown", {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-frames", action="store_true")
    parser.add_argument("--fetch-submissions", type=Path,
                        help="Text file with one CIK per line to cache SEC submissions for")
    args = parser.parse_args()
    report = {}
    if args.fetch_frames:
        report["frames"] = fetch_frames()
    if args.fetch_submissions:
        ciks = {line.strip() for line in args.fetch_submissions.read_text().splitlines() if line.strip()}
        report["submissions"] = fetch_submissions(ciks)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
