"""Complete quarterly coverage report with scoped source and publication ports."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from gabi.domain.research.coverage import CoverageParameters, compare_prices
from gabi.domain.research.quarterly_coverage import CompanyCoverageInputs, company_quarter


@dataclass(frozen=True)
class CoverageMetadata:
    members: pd.DataFrame
    mappings: dict[str, str]
    blocked: dict[str, str]


@dataclass(frozen=True)
class CoverageReport:
    comparisons: pd.DataFrame
    details: pd.DataFrame
    quarters: pd.DataFrame
    missing: pd.DataFrame
    summary: dict


class CoverageReader(Protocol):
    def metadata(self) -> CoverageMetadata: ...
    def benchmark(self) -> pd.DataFrame: ...
    def company(self, symbol: str, cik: str) -> CompanyCoverageInputs: ...


class CoverageWriter(Protocol):
    def save(self, report: CoverageReport) -> None: ...


def audit(reader: CoverageReader, sessions: pd.DatetimeIndex, *,
          parameters: CoverageParameters = CoverageParameters(), max_symbols: int = 1000,
          progress: Callable[[str], None] | None = None) -> CoverageReport:
    metadata = reader.metadata()
    targets = {symbol for value in metadata.members.tickers for symbol in value.split(",")}
    if len(targets) > max_symbols:
        raise ValueError("Quarterly coverage symbol limit exceeded")
    dates = pd.date_range("1996-03-31", "2015-12-31", freq="QE")
    members = {day.date().isoformat(): metadata.members[metadata.members.date <= day.date().isoformat()].iloc[-1].tickers.split(",")
               for day in dates}
    expected = {day.date().isoformat(): sessions[sessions <= day][-253:] for day in dates}
    benchmark = reader.benchmark()
    comparisons = {}
    rows: dict[tuple[str, str], dict] = {}
    # Load one company once; do not retain every source series in memory.
    for symbol in sorted(targets):
        cik = metadata.mappings.get(symbol, "")
        inputs = reader.company(symbol, cik)
        comparison = compare_prices(inputs.yahoo, inputs.archive)
        comparisons[symbol] = comparison
        for date in dates:
            day = date.date().isoformat()
            if symbol in members[day]:
                rows[day, symbol] = company_quarter(inputs, benchmark, symbol, cik, date, expected[day],
                                                   metadata.blocked.get(symbol, ""), comparison["status"], parameters=parameters)
    details, quarters = [], []
    for date in dates:
        day = date.date().isoformat()
        quarter_rows = [rows[day, symbol] for symbol in members[day]]
        details.extend(quarter_rows)
        group = pd.DataFrame(quarter_rows)
        counts = {key: int(group[key].sum()) for key in ["all_13", "eligible_by_metric_rule", "before_all_13",
                   "before_eligible_by_metric_rule", "prices_253_recent", "fresh_filing", "identity_verified", "sector_verified", "fully_validated"]}
        counts["all_13_fresh_prices_and_filing"] = int((group.all_13 & group.prices_253_recent & group.fresh_filing).sum())
        quarters.append(dict(date=day, members=len(members[day]), **counts))
        if progress:
            progress(f"{day} complete metrics {counts['all_13']} / {len(members[day])}")
    detail_frame = pd.DataFrame(details)
    missing = detail_frame.assign(metric=lambda frame: frame.missing_metrics.str.split(";")).explode("metric")
    missing = missing[missing.metric != ""].groupby(["date", "metric"]).size().rename("companies").reset_index()
    summary = dict(quarters=len(quarters), company_quarters=len(details), metrics=list(parameters.metrics),
                   numerical_only=True, sector_verified=False,
                   source_comparison=pd.Series([record["status"] for record in comparisons.values()]).value_counts().to_dict(),
                   final_quarter=quarters[-1])
    return CoverageReport(pd.DataFrame([dict(symbol=symbol, **record) for symbol, record in comparisons.items()]),
                          detail_frame, pd.DataFrame(quarters), missing, summary)


def publish(reader: CoverageReader, sessions: pd.DatetimeIndex, writer: CoverageWriter, *,
            parameters: CoverageParameters = CoverageParameters(), progress: Callable[[str], None] | None = None) -> dict:
    report = audit(reader, sessions, parameters=parameters, progress=progress)
    writer.save(report)
    return report.summary
