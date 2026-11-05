"""Etiquetas en palabras del panel macro (#309): una por bloque, con reglas fijas y documentadas.

Son contexto, no señal: no cambian la puntuación ni el ranking, y ninguna regla está validada para
anticipar la bolsa. Cada etiqueta dice de qué serie y fecha sale y qué regla se aplicó, para que el
usuario pueda comprobarla. Sin dato, la etiqueta lo dice en vez de suponer.
"""

# block: (title, series shown in it, in order)
BLOCKS: dict[str, tuple[str, tuple[str, ...]]] = {
    "liquidity": ("Liquidez", ("WALCL",)),
    "inflation_rates": ("Inflación y tipos", ("CPIAUCSL", "T10YIE", "FEDFUNDS", "DGS10", "DFII10")),
    "growth_jobs": ("Crecimiento y empleo", ("UNRATE", "ICSA", "SAHMREALTIME", "T10Y2Y")),
    "conditions": ("Condiciones financieras", ("NFCI", "BAMLH0A0HYM2", "DTWEXBGS")),
}

LIQUIDITY_FLAT_PCT = 1.0  # Fed balance change in ~3 months within ±1 %: «estable».
INFLATION_TARGET = 2.0  # The Fed's target.
INFLATION_NEAR = 3.0  # CPI ≤ 3 %: «cerca del objetivo»; above, «por encima»; above HIGH, «alta».
INFLATION_HIGH = 5.0
SAHM_RECESSION = 0.5  # The rule's own threshold.
SAHM_WATCH = 0.3
NFCI_TIGHT = 0.0  # NFCI is 0 at average conditions; positive is tighter than average.
SPREAD_CALM = 4.0  # High-yield spread in %, used only without NFCI.
SPREAD_STRESS = 6.0


def _label(block: str, text: str, tone: str, series_id: str | None, value: float | None, date, rule: str) -> dict:
    return {"block": block, "title": BLOCKS[block][0], "label": text, "tone": tone, "series_id": series_id,
            "value": value, "date": date, "rule": rule}


def _missing(block: str, series: str) -> dict:
    return _label(block, "Sin datos", "neutral", None, None, None,
                  f"Faltan los datos de {series} guardados en tu equipo.")


def liquidity(row: dict | None) -> dict:
    if not row or row.get("latest_value") is None or row.get("change_3m") is None:
        return _missing("liquidity", "WALCL")
    before = row["latest_value"] - row["change_3m"]
    pct = 100 * row["change_3m"] / before if before else 0.0
    rule = (f"Cambio del balance de la Fed en unos 3 meses: estable si está entre −{LIQUIDITY_FLAT_PCT:g} % "
            f"y +{LIQUIDITY_FLAT_PCT:g} %.")
    if pct > LIQUIDITY_FLAT_PCT:
        return _label("liquidity", "Aumentando", "neutral", "WALCL", pct, row["latest_date"], rule)
    if pct < -LIQUIDITY_FLAT_PCT:
        return _label("liquidity", "Bajando", "neutral", "WALCL", pct, row["latest_date"], rule)
    return _label("liquidity", "Estable", "neutral", "WALCL", pct, row["latest_date"], rule)


def inflation(row: dict | None) -> dict:
    if not row or row.get("latest_value") is None:
        return _missing("inflation_rates", "CPIAUCSL")
    value = row["latest_value"]
    rule = (f"Inflación interanual frente al objetivo del {INFLATION_TARGET:g} % de la Fed: cerca hasta el "
            f"{INFLATION_NEAR:g} %, alta por encima del {INFLATION_HIGH:g} %.")
    if value > INFLATION_HIGH:
        return _label("inflation_rates", "Inflación alta", "bad", "CPIAUCSL", value, row["latest_date"], rule)
    if value > INFLATION_NEAR:
        return _label("inflation_rates", "Inflación por encima del objetivo", "bad", "CPIAUCSL", value,
                      row["latest_date"], rule)
    return _label("inflation_rates", "Inflación cerca del objetivo", "good", "CPIAUCSL", value,
                  row["latest_date"], rule)


def growth(row: dict | None) -> dict:
    if not row or row.get("latest_value") is None:
        return _missing("growth_jobs", "SAHMREALTIME")
    value = row["latest_value"]
    rule = (f"Regla de Sahm: desde {SAHM_RECESSION:g} ha coincidido con el inicio de las recesiones; "
            f"entre {SAHM_WATCH:g} y {SAHM_RECESSION:g}, el paro está subiendo.")
    if value >= SAHM_RECESSION:
        return _label("growth_jobs", "Señal de recesión", "bad", "SAHMREALTIME", value, row["latest_date"], rule)
    if value >= SAHM_WATCH:
        return _label("growth_jobs", "Empleo debilitándose", "bad", "SAHMREALTIME", value, row["latest_date"], rule)
    return _label("growth_jobs", "Empleo sólido", "good", "SAHMREALTIME", value, row["latest_date"], rule)


def conditions(nfci: dict | None, spread: dict | None) -> dict:
    if nfci and nfci.get("latest_value") is not None:
        value = nfci["latest_value"]
        rule = "Índice de la Fed de Chicago (NFCI): 0 es la media histórica; por debajo, más holgadas."
        if value < NFCI_TIGHT:
            return _label("conditions", "Holgadas", "good", "NFCI", value, nfci["latest_date"], rule)
        return _label("conditions", "Más tensas que la media", "bad", "NFCI", value, nfci["latest_date"], rule)
    if spread and spread.get("latest_value") is not None:
        value = spread["latest_value"]
        rule = (f"Sin el índice NFCI, se usa la sobreprima del bono basura: holgadas por debajo del "
                f"{SPREAD_CALM:g} %, tensas por encima del {SPREAD_STRESS:g} %.")
        if value < SPREAD_CALM:
            return _label("conditions", "Holgadas", "good", "BAMLH0A0HYM2", value, spread["latest_date"], rule)
        if value > SPREAD_STRESS:
            return _label("conditions", "Tensas", "bad", "BAMLH0A0HYM2", value, spread["latest_date"], rule)
        return _label("conditions", "Normales", "neutral", "BAMLH0A0HYM2", value, spread["latest_date"], rule)
    return _missing("conditions", "NFCI")


def labels(rows: list[dict]) -> list[dict]:
    """One label per block, in BLOCKS order, from the panel rows already read."""
    by_id = {row["series_id"]: row for row in rows}
    return [liquidity(by_id.get("WALCL")), inflation(by_id.get("CPIAUCSL")), growth(by_id.get("SAHMREALTIME")),
            conditions(by_id.get("NFCI"), by_id.get("BAMLH0A0HYM2"))]
