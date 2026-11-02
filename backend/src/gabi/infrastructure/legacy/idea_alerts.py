"""Worker composition of the idea alert job (#247): the same local services the API uses, read-only."""

from collections.abc import Callable
from datetime import date

from gabi.infrastructure.settings import Settings


def run_idea_alerts(settings: Settings, today: Callable[[], date],
                    progress: Callable[[float, str], None] | None = None) -> dict:
    from gabi.application.market.checklist import CompanyChecklist
    from gabi.application.market.company_research import CompanyResearch
    from gabi.application.portfolio import idea_alerts
    from gabi.application.portfolio.ideas import Ideas
    from gabi.infrastructure.legacy.company import LegacyCompanyMath
    from gabi.infrastructure.legacy.filings import compare_cached
    from gabi.infrastructure.legacy.market import calculators, model_policy
    from gabi.infrastructure.model_versions import active_model
    from gabi.infrastructure.storage.cache_reads import SqliteCacheReads
    from gabi.infrastructure.storage.checklist_thresholds import FileChecklistThresholds
    from gabi.infrastructure.storage.company_research import SqliteCompanyResearch
    from gabi.infrastructure.storage.ideas import SqliteIdeas
    from gabi.infrastructure.storage.investment_cards import SqliteInvestmentCards
    from gabi.infrastructure.storage.market import ReadOnlyMarket
    from gabi.infrastructure.storage.sec_reads import SqliteSecReads
    from gabi.infrastructure.storage.signals import SqliteSignals
    from gabi.infrastructure.storage.simulations import SqliteSimulations

    database = settings.data_dir / "gabi.db"
    model = active_model()
    market = ReadOnlyMarket(settings, calculators(model.technical), model_policy(model), model.benchmark_symbol,
                            model.risk_free_rate, metrics_version=model.metrics_version)
    signals = SqliteSignals(settings.data_dir)
    try:
        checklist = CompanyChecklist(SqliteSecReads(database), SqliteCacheReads(database),
                                     SqliteCompanyResearch(settings.data_dir),
                                     FileChecklistThresholds(settings.data_dir), today)
        research = CompanyResearch(SqliteCompanyResearch(settings.data_dir), market.company_events,
                                   lambda symbol: compare_cached(symbol, *signals.filing_facts(symbol)),
                                   LegacyCompanyMath(), today)
        cards = SqliteInvestmentCards(settings.data_dir)
        return idea_alerts.run(
            Ideas(SqliteIdeas(settings.data_dir), SqliteSimulations(settings.data_dir).prices, today),
            card=lambda card_id: cards.get(card_id) or {}, checklist=checklist.company,
            filings=research.filing_changes, overview=research.overview, insiders=research.insiders, today=today,
            progress=progress or (lambda share, message: None))
    finally:
        market.close()
