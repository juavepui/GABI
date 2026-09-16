import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import edgar


def _annual_entry(start, end, val, form="10-K", fp="FY"):
    return {"start": start, "end": end, "val": val, "form": form, "fp": fp}


def test_extract_annual_values_filters_out_quarterly_entries_within_10k():
    # Igual que en los datos reales de SEC: un 10-K puede incluir, mezclados,
    # algunos periodos trimestrales de contexto con el mismo form/fp — deben
    # descartarse y quedarse solo con los periodos ~anuales (340-380 días).
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            _annual_entry("2016-10-01", "2016-12-31", 50_000),  # trimestre, descartar
                            _annual_entry("2016-01-01", "2016-12-31", 200_000),  # anual
                            _annual_entry("2017-01-01", "2017-12-31", 220_000),  # anual
                            _annual_entry("2018-01-01", "2018-12-31", 250_000),  # anual
                            _annual_entry("2019-01-01", "2019-12-31", 280_000),  # anual
                        ]
                    }
                }
            }
        }
    }
    series = edgar._extract_annual_values(facts, edgar.REVENUE_TAGS)
    assert series == [
        ("2016-12-31", 200_000),
        ("2017-12-31", 220_000),
        ("2018-12-31", 250_000),
        ("2019-12-31", 280_000),
    ]


def test_extract_annual_values_falls_back_to_next_tag_when_first_missing():
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            _annual_entry("2016-01-01", "2016-12-31", 100),
                            _annual_entry("2017-01-01", "2017-12-31", 110),
                        ]
                    }
                }
            }
        }
    }
    # RevenueFromContractWithCustomerExcludingAssessedTax no existe -> debe
    # probar el siguiente tag de la lista (Revenues) y encontrarlo.
    series = edgar._extract_annual_values(facts, edgar.REVENUE_TAGS)
    assert series == [("2016-12-31", 100), ("2017-12-31", 110)]


def test_extract_annual_values_returns_empty_when_no_tag_present():
    facts = {"facts": {"us-gaap": {}}}
    assert edgar._extract_annual_values(facts, edgar.REVENUE_TAGS) == []


def test_cagr_from_series_basic():
    series = [("2019", 100), ("2020", 110), ("2021", 121), ("2022", 133.1)]
    cagr = edgar._cagr_from_series(series, years=3)
    assert round(cagr, 4) == 0.10  # 10% anual compuesto exacto por construcción


def test_cagr_from_series_needs_enough_years():
    assert edgar._cagr_from_series([("2021", 100), ("2022", 110)], years=3) is None


def test_cagr_from_series_none_on_negative_or_zero_base():
    series = [("2019", -50), ("2020", 10), ("2021", 20), ("2022", 30)]
    assert edgar._cagr_from_series(series, years=3) is None


def test_compute_edgar_metrics_end_to_end():
    def series(tag, values, start_year=2019):
        return {
            "units": {
                "USD": [
                    _annual_entry(f"{start_year + i}-01-01", f"{start_year + i}-12-31", v)
                    for i, v in enumerate(values)
                ]
            }
        }

    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": series("Revenues", [1000, 1100, 1210, 1331]),
                "NetIncomeLoss": series("NetIncomeLoss", [100, 110, 120, 140]),
                "NetCashProvidedByUsedInOperatingActivities": series("ocf", [150, 160, 170, 190]),
                "PaymentsToAcquirePropertyPlantAndEquipment": series("capex", [30, 30, 35, 40]),
                "StockholdersEquity": series("equity", [500, 540, 590, 650]),
                "LongTermDebtNoncurrent": series("debt", [200, 190, 180, 170]),
            }
        }
    }
    metrics = edgar.compute_edgar_metrics(facts)
    assert metrics["revenue_cagr_3y"] is not None
    assert round(metrics["revenue_cagr_3y"], 3) == 0.1
    assert metrics["fcf_cagr_3y"] is not None
    assert metrics["roic"] is not None
    # ROIC del último año: 140 / (650 + 170)
    assert round(metrics["roic"], 4) == round(140 / (650 + 170), 4)


def test_extract_instant_values_handles_balance_sheet_facts_without_start():
    # A diferencia de Revenue (duration: start+end), las partidas de balance
    # como StockholdersEquity son "instant" en XBRL: solo tienen 'end', sin
    # 'start'. Es el bug real que se detectó probando con datos en vivo de la SEC.
    facts = {
        "facts": {
            "us-gaap": {
                "StockholdersEquity": {
                    "units": {
                        "USD": [
                            {"end": "2021-12-31", "val": 500, "form": "10-K", "fp": "FY"},
                            {"end": "2022-12-31", "val": 600, "form": "10-K", "fp": "FY"},
                        ]
                    }
                }
            }
        }
    }
    series = edgar._extract_instant_values(facts, edgar.EQUITY_TAGS)
    assert series == [("2021-12-31", 500), ("2022-12-31", 600)]


def test_extract_raw_facts_keeps_everything_unfiltered():
    # A diferencia de _extract_annual_values, esto NO debe descartar
    # trimestres, restataciones repetidas del mismo periodo, ni nada: es la
    # capa de ingesta "solo datos limpios y auditables", sin interpretar.
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {"start": "2016-10-01", "end": "2016-12-31", "val": 50_000,
                             "form": "10-K", "fp": "FY", "fy": 2016, "filed": "2017-02-01", "accn": "0001-16-A"},
                            {"start": "2016-01-01", "end": "2016-12-31", "val": 200_000,
                             "form": "10-K", "fp": "FY", "fy": 2016, "filed": "2017-02-01", "accn": "0001-16-B"},
                            # Misma partida re-presentada (restated) en el 10-K del año siguiente.
                            {"start": "2016-01-01", "end": "2016-12-31", "val": 201_500,
                             "form": "10-K", "fp": "FY", "fy": 2017, "filed": "2018-02-01", "accn": "0001-17-A"},
                        ]
                    }
                }
            }
        }
    }
    rows = edgar._extract_raw_facts(facts, edgar.REVENUE_TAGS)
    assert len(rows) == 3  # nada descartado, ni el trimestre ni la restatación
    accns = {r["accn"] for r in rows}
    assert accns == {"0001-16-A", "0001-16-B", "0001-17-A"}
    assert all(r["filed_date"] for r in rows)


def test_extract_raw_facts_skips_entries_without_accession_number():
    facts = {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {"USD": [{"start": "2016-01-01", "end": "2016-12-31", "val": 100, "form": "10-K", "fp": "FY"}]}
                }
            }
        }
    }
    assert edgar._extract_raw_facts(facts, edgar.NET_INCOME_TAGS) == []


def test_upsert_and_get_edgar_facts_roundtrip(tmp_path, monkeypatch):
    from gabi import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test_gabi.db")

    rows = [
        {"tag": "Revenues", "unit": "USD", "start_date": "2018-01-01", "end_date": "2018-12-31",
         "val": 1000.0, "form": "10-K", "fp": "FY", "fy": 2018, "filed_date": "2019-02-01", "accn": "acc-1"},
        {"tag": "NetIncomeLoss", "unit": "USD", "start_date": "2018-01-01", "end_date": "2018-12-31",
         "val": 100.0, "form": "10-K", "fp": "FY", "fy": 2018, "filed_date": "2019-02-01", "accn": "acc-2"},
    ]
    edgar.upsert_edgar_facts("ACME", rows)

    all_facts = edgar.get_edgar_facts("ACME")
    assert len(all_facts) == 2

    only_revenue = edgar.get_edgar_facts("ACME", tags=["Revenues"])
    assert len(only_revenue) == 1
    assert only_revenue.iloc[0]["val"] == 1000.0

    # Re-insertar los mismos hechos (misma clave) no debe duplicar filas.
    edgar.upsert_edgar_facts("ACME", rows)
    assert len(edgar.get_edgar_facts("ACME")) == 2


def test_get_value_as_of_avoids_look_ahead_bias(tmp_path, monkeypatch):
    from gabi import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test_gabi.db")

    # El resultado FY2018 (100) se presenta el 2019-02-01; una restatación
    # posterior (110) se presenta el 2020-02-01, dentro del 10-K de FY2019.
    rows = [
        {"tag": "NetIncomeLoss", "unit": "USD", "start_date": "2018-01-01", "end_date": "2018-12-31",
         "val": 100.0, "form": "10-K", "fp": "FY", "fy": 2018, "filed_date": "2019-02-01", "accn": "acc-1"},
        {"tag": "NetIncomeLoss", "unit": "USD", "start_date": "2018-01-01", "end_date": "2018-12-31",
         "val": 110.0, "form": "10-K", "fp": "FY", "fy": 2019, "filed_date": "2020-02-01", "accn": "acc-2"},
    ]
    edgar.upsert_edgar_facts("ACME", rows)

    # Antes de que se presentara nada: no había dato disponible todavía.
    assert edgar.get_value_as_of("ACME", ["NetIncomeLoss"], "2019-01-01") is None
    # Justo tras la primera presentación: el valor original, no la revisión futura.
    assert edgar.get_value_as_of("ACME", ["NetIncomeLoss"], "2019-06-01") == 100.0
    # Tras la restatación: ya se conoce el valor revisado.
    assert edgar.get_value_as_of("ACME", ["NetIncomeLoss"], "2020-06-01") == 110.0


def test_compute_edgar_metrics_includes_margins_ebitda_and_net_debt():
    def series(values, start_year=2019):
        return {
            "units": {
                "USD": [
                    _annual_entry(f"{start_year + i}-01-01", f"{start_year + i}-12-31", v)
                    for i, v in enumerate(values)
                ]
            }
        }

    def instant_series(values, start_year=2019):
        return {
            "units": {
                "USD": [
                    {"end": f"{start_year + i}-12-31", "val": v, "form": "10-K", "fp": "FY"}
                    for i, v in enumerate(values)
                ]
            }
        }

    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": series([1000, 1100]),
                "NetIncomeLoss": series([100, 130]),
                "NetCashProvidedByUsedInOperatingActivities": series([150, 170]),
                "PaymentsToAcquirePropertyPlantAndEquipment": series([30, 35]),
                "StockholdersEquity": instant_series([500, 560]),
                "LongTermDebtNoncurrent": instant_series([200, 190]),
                "GrossProfit": series([600, 660]),
                "OperatingIncomeLoss": series([180, 200]),
                "DepreciationDepletionAndAmortization": series([40, 45]),
                "CashAndCashEquivalentsAtCarryingValue": instant_series([80, 90]),
            }
        }
    }
    m = edgar.compute_edgar_metrics(facts)

    assert round(m["gross_margin"], 4) == round(660 / 1100, 4)
    assert round(m["operating_margin"], 4) == round(200 / 1100, 4)
    assert round(m["profit_margin"], 4) == round(130 / 1100, 4)
    assert m["latest_ebitda"] == 200 + 45  # operating income + D&A
    # deuda neta = deuda - caja = 190 - 90 = 100; ebitda = 245 -> ratio ~0.408
    assert round(m["net_debt_to_ebitda"], 3) == round(100 / 245, 3)
    assert round(m["revenue_growth_yoy"], 3) == round(1100 / 1000 - 1, 3)
    assert round(m["earnings_growth_yoy"], 3) == round(130 / 100 - 1, 3)
    assert m["latest_revenue"] == 1100
    assert m["latest_period_end"] == "2020-12-31"


def test_compute_edgar_metrics_as_of_matches_live_when_no_restatements(tmp_path, monkeypatch):
    from gabi import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test_gabi.db")

    rows = [
        {"tag": "Revenues", "unit": "USD", "start_date": "2019-01-01", "end_date": "2019-12-31",
         "val": 1000.0, "form": "10-K", "fp": "FY", "fy": 2019, "filed_date": "2020-02-01", "accn": "a1"},
        {"tag": "Revenues", "unit": "USD", "start_date": "2020-01-01", "end_date": "2020-12-31",
         "val": 1200.0, "form": "10-K", "fp": "FY", "fy": 2020, "filed_date": "2021-02-01", "accn": "a2"},
    ]
    edgar.upsert_edgar_facts("ACME", rows)

    # A fecha 2020-06-01 solo se conocía el ejercicio 2019 (el de 2020 se
    # presentó en 2021-02-01) -> el 'último ingreso conocido' debe ser 1000,
    # no 1200 (eso sería look-ahead bias).
    m_2020 = edgar.compute_edgar_metrics_as_of("ACME", "2020-06-01")
    assert m_2020["latest_revenue"] == 1000.0

    m_2021 = edgar.compute_edgar_metrics_as_of("ACME", "2021-06-01")
    assert m_2021["latest_revenue"] == 1200.0


def test_get_shares_outstanding_as_of(tmp_path, monkeypatch):
    from gabi import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test_gabi.db")

    rows = [
        {"tag": "CommonStockSharesOutstanding", "unit": "shares", "start_date": "",
         "end_date": "2019-12-31", "val": 1_000_000.0, "form": "10-K", "fp": "FY",
         "fy": 2019, "filed_date": "2020-02-01", "accn": "a1"},
        {"tag": "CommonStockSharesOutstanding", "unit": "shares", "start_date": "",
         "end_date": "2020-12-31", "val": 900_000.0, "form": "10-K", "fp": "FY",
         "fy": 2020, "filed_date": "2021-02-01", "accn": "a2"},
    ]
    edgar.upsert_edgar_facts("ACME", rows)

    assert edgar.get_shares_outstanding_as_of("ACME", "2020-06-01") == 1_000_000.0
    assert edgar.get_shares_outstanding_as_of("ACME", "2021-06-01") == 900_000.0
    assert edgar.get_shares_outstanding_as_of("ACME", "2019-01-01") is None


def test_get_cik_for_symbol_prefers_live_map_and_remembers_it(tmp_path, monkeypatch):
    from gabi import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test_gabi.db")

    cik_map = pd.DataFrame([{"symbol": "AAA", "cik": "0000000001", "title": "Acme Corp"}])
    cik, title = edgar.get_cik_for_symbol("AAA", cik_map=cik_map)
    assert (cik, title) == ("0000000001", "Acme Corp")

    # Debe haber quedado recordado localmente aunque ya no esté en un mapeo en vivo futuro.
    empty_live_map = pd.DataFrame(columns=["symbol", "cik", "title"])
    cik2, title2 = edgar.get_cik_for_symbol("AAA", cik_map=empty_live_map)
    assert (cik2, title2) == ("0000000001", "Acme Corp")


def test_get_cik_for_symbol_returns_none_when_never_resolved(tmp_path, monkeypatch):
    from gabi import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test_gabi.db")

    empty_live_map = pd.DataFrame(columns=["symbol", "cik", "title"])
    assert edgar.get_cik_for_symbol("NUNCA", cik_map=empty_live_map) == (None, None)


def test_get_resolved_title_surfaces_ticker_recycling_risk(tmp_path, monkeypatch):
    # No "arregla" el reciclaje (ver comentario en RESOLUTIONS_SCHEMA): el
    # objetivo es que el nombre resuelto quede disponible para que la UI lo
    # muestre y el usuario pueda notar que "APC" ya no es la empresa que él
    # recuerda de 2019.
    from gabi import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test_gabi.db")

    cik_map = pd.DataFrame([{"symbol": "APC", "cik": "0002080921", "title": "ARKO Petroleum Corp."}])
    edgar.get_cik_for_symbol("APC", cik_map=cik_map)
    assert edgar.get_resolved_title("APC") == "ARKO Petroleum Corp."


def test_extract_latest_filings_builds_correct_url():
    submissions = {
        "cik": 320193,
        "filings": {
            "recent": {
                "form": ["8-K", "10-Q", "10-K", "10-Q"],
                "filingDate": ["2024-01-05", "2024-02-01", "2023-11-01", "2023-08-01"],
                "accessionNumber": ["0000320193-24-000005", "0000320193-24-000010", "0000320193-23-000106", "0000320193-23-000070"],
                "primaryDocument": ["a.htm", "b.htm", "aapl-20230930.htm", "d.htm"],
            }
        },
    }
    result = edgar.extract_latest_filings(submissions)
    assert result["latest_10k_date"] == "2023-11-01"
    assert result["latest_10k_url"] == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm"
    )
    assert result["latest_10q_date"] == "2024-02-01"
    assert "000032019324000010" in result["latest_10q_url"]
