"""Single F6 bridge to the unchanged point-in-time ranking engine."""


def run_historical(as_of: str) -> dict:
    from gabi import screener_asof

    return screener_asof.build_ranking_as_of(as_of)


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
