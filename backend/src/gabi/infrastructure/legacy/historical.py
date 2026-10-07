"""Single F6 bridge to the unchanged point-in-time ranking engine."""


def run_historical(as_of: str) -> dict:
    from gabi import edgar, screener_asof

    result = screener_asof.build_ranking_as_of(as_of)
    table = result["table"]
    if not table.empty:
        # The old page looked the SEC title up on every render; the job stores it once with the artifact.
        result["table"] = table.assign(resolved_title=[edgar.get_resolved_title(symbol) for symbol in table.index])
    return result


class LegacyRankingQuality:
    """Coverage aggregation and warning texts shared with the Streamlit pages."""

    @staticmethod
    def block_coverage(table) -> dict:
        from gabi import data_quality

        return data_quality.score_block_coverage(table)

    @staticmethod
    def block_warnings(blocks: dict, threshold: float) -> list[str]:
        from gabi import data_quality

        return data_quality.block_coverage_warnings(blocks, threshold)

    @staticmethod
    def ranking_warnings(quality: dict, threshold: float) -> list[str]:
        from gabi import data_quality

        return data_quality.ranking_quality_warnings(quality, threshold)


def run_outcomes(data_dir, request: dict) -> dict:
    """The "Resultado posterior" and block comparison of the old page, with bounded observed prices."""
    from gabi.application.market.snapshot_math import SnapshotCalculations
    from gabi.application.research.historical_outcomes import build_outcomes
    from gabi.application.research.reservations import OBSERVED_END
    from gabi.infrastructure.storage.jobs import SqliteJobs
    from gabi.infrastructure.storage.window_prices import SqliteWindowPrices

    jobs = SqliteJobs(data_dir)
    source = jobs.get(request["source_job_id"])
    if source["kind"] != "historical_ranking":
        raise ValueError("El trabajo de origen no es un ranking histórico.")
    ranking = jobs.result(request["source_job_id"])  # Verifies the stored SHA-256.
    prices = SqliteWindowPrices(data_dir, OBSERVED_END)
    return build_outcomes(ranking, request, source["result_sha256"],
                          lambda symbols, as_of, months, cost: SnapshotCalculations.evaluate(
                              symbols, as_of, months, cost_bps=cost, price_at=prices, today=OBSERVED_END))
