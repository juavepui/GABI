import sys
from pathlib import Path

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
