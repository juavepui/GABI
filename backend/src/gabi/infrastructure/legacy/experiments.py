"""Unchanged Research Lab statistics (stats_rigor, block_bootstrap, portfolio_metrics); no storage access."""


class LegacyExperimentMath:
    @staticmethod
    def psr_from_returns(returns, periods_per_year: float) -> dict:
        from gabi import stats_rigor

        return stats_rigor.probabilistic_sharpe_ratio_from_returns(returns, periods_per_year)

    @staticmethod
    def deflated_sharpe(sharpe: float, trial_sharpes: list[float], n_obs: int, periods_per_year: float,
                        skew: float, kurtosis: float) -> dict:
        from gabi import stats_rigor

        return stats_rigor.deflated_sharpe_ratio(sharpe, trial_sharpes, n_obs=n_obs,
                                                 periods_per_year=periods_per_year, skew=skew, kurtosis=kurtosis)

    @staticmethod
    def psr_annualized(sharpe: float, n_obs: int, periods_per_year: float, skew: float, kurtosis: float) -> float:
        from gabi import stats_rigor

        return stats_rigor.probabilistic_sharpe_ratio_annualized(sharpe, n_obs, periods_per_year, skew=skew,
                                                                 kurtosis=kurtosis, benchmark_sharpe=0.0)

    @staticmethod
    def tail_risk(returns, horizon: str) -> dict:
        from gabi import portfolio_metrics

        return portfolio_metrics.tail_risk_metrics(returns, horizon=horizon)

    @staticmethod
    def pbo(matrix, n_splits: int) -> dict:
        from gabi import stats_rigor

        return stats_rigor.pbo_cscv(matrix, n_splits=n_splits)

    @staticmethod
    def block_lengths() -> dict:
        from gabi import block_bootstrap

        return block_bootstrap.BLOCK_LENGTHS

    @staticmethod
    def bootstrap(matrix, periods_per_year: float):
        from gabi import block_bootstrap

        return block_bootstrap.analyze_sensitivity(matrix, periods_per_year=periods_per_year, strategy="strategy")

