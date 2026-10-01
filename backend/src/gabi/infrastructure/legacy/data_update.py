"""The old Configuración download and key storage through the unchanged screener/config."""

from pathlib import Path

from gabi.application.errors import QueryError


def run_data_update(options: dict) -> dict:
    """Worker only (its LegacyExecutor checks the data directory): screener.refresh_data as the old button."""
    from gabi import screener
    from gabi.application.administration.data_update import summarize_update

    symbols = options["symbols"] or screener.get_universe(limit=options["universe_limit"])["symbol"].tolist()
    # A retry forces the download, as «Reintentar solo los fallidos» did.
    force = True if options["symbols"] is not None else options["force"]
    return summarize_update(options, symbols, screener.refresh_data(symbols, force=force))


class LegacyKeyWriter:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def save(self, source: str, key: str) -> None:
        from gabi import config

        save, path = {"fred": (config.save_fred_key, config.FRED_KEY_PATH),
                      "tiingo": (config.save_tiingo_key, config.TIINGO_KEY_PATH),
                      "nasdaq": (config.save_nasdaq_data_link_key, config.NASDAQ_DATA_LINK_KEY_PATH),
                      "fmp": (config.save_fmp_key, config.FMP_KEY_PATH)}[source]
        # The key paths are computed at import: check the file itself, not only DATA_DIR.
        if config.DATA_DIR.resolve() != self.data_dir.resolve() or path.parent.resolve() != self.data_dir.resolve():
            raise QueryError("settings_unavailable", "La configuración no usa el directorio de datos de la API.", 503)
        save(key)
