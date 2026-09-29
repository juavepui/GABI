import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import config, edgar, filing_tracker, storage


def _isolate_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")


def _seed_filing(symbol, accn, form, start_date, end_date, filed_date, *,
                 revenue, operating_income, gross_profit, ocf, capex, net_income, equity, debt, cash):
    """Un filing sintético completo (todas las etiquetas que usa
    _period_metrics_for_accn) bajo un único accn, como un filing real."""
    duration_rows = [
        ("Revenues", revenue), ("OperatingIncomeLoss", operating_income), ("GrossProfit", gross_profit),
        ("NetCashProvidedByUsedInOperatingActivities", ocf),
        ("PaymentsToAcquirePropertyPlantAndEquipment", capex), ("NetIncomeLoss", net_income),
    ]
    instant_rows = [("StockholdersEquity", equity), ("LongTermDebtNoncurrent", debt),
                    ("CashAndCashEquivalentsAtCarryingValue", cash)]
    fp = "FY" if form == "10-K" else "Q1"
    rows = [
        {"tag": tag, "unit": "USD", "start_date": start_date, "end_date": end_date, "val": val,
         "form": form, "fp": fp, "fy": 2024, "filed_date": filed_date, "accn": accn}
        for tag, val in duration_rows
    ] + [
        {"tag": tag, "unit": "USD", "start_date": "", "end_date": end_date, "val": val,
         "form": form, "fp": fp, "fy": 2024, "filed_date": filed_date, "accn": accn}
        for tag, val in instant_rows
    ]
    edgar.upsert_edgar_facts(symbol, rows)


def _seed_cik(symbol, cik):
    with storage.get_connection() as conn:
        conn.executescript(edgar.SCHEMA)
        conn.execute("INSERT OR REPLACE INTO edgar_metrics (symbol, cik, fetched_at) VALUES (?,?,?)",
                     (symbol, cik, "2024-01-01T00:00:00"))
        conn.commit()


def test_list_filings_derives_from_edgar_facts_and_persists_metadata(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    _seed_cik("AAA", "0000000001")
    _seed_filing("AAA", "acc-2023", "10-K", "2023-01-01", "2023-12-31", "2024-02-01",
                revenue=1000, operating_income=200, gross_profit=500, ocf=250, capex=50,
                net_income=150, equity=600, debt=200, cash=300)
    _seed_filing("AAA", "acc-2024", "10-K", "2024-01-01", "2024-12-31", "2025-02-01",
                revenue=1100, operating_income=220, gross_profit=550, ocf=260, capex=60,
                net_income=160, equity=650, debt=210, cash=310)

    filings = filing_tracker.list_filings("AAA", "10-K")
    assert list(filings["accn"]) == ["acc-2023", "acc-2024"]  # ordenado por filed_date
    assert filings.iloc[0]["filed_date"] == "2024-02-01"
    assert filings.iloc[1]["period_end"] == "2024-12-31"
    assert filings.iloc[0]["url"].endswith("acc-2023-index.htm")

    with storage.get_connection() as conn:
        conn.executescript(filing_tracker.SCHEMA)
        n = conn.execute("SELECT COUNT(*) FROM filing_metadata WHERE symbol='AAA'").fetchone()[0]
    assert n == 2  # se persistió de paso


def test_list_filings_without_cik_returns_null_url(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    _seed_filing("BBB", "acc-1", "10-K", "2023-01-01", "2023-12-31", "2024-02-01",
                revenue=100, operating_income=10, gross_profit=40, ocf=15, capex=5,
                net_income=8, equity=50, debt=20, cash=30)
    filings = filing_tracker.list_filings("BBB", "10-K")
    assert filings.iloc[0]["url"] is None


def test_list_filings_empty_when_no_facts(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    filings = filing_tracker.list_filings("NUNCA", "10-K")
    assert filings.empty


def test_list_filings_rejects_unknown_form():
    try:
        filing_tracker.list_filings("AAA", "8-K")
        assert False, "debía lanzar ValueError"
    except ValueError:
        pass


def test_latest_two_filings_with_single_filing_has_no_comparable(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    _seed_filing("AAA", "acc-1", "10-K", "2023-01-01", "2023-12-31", "2024-02-01",
                revenue=100, operating_income=10, gross_profit=40, ocf=15, capex=5,
                net_income=8, equity=50, debt=20, cash=30)
    current, previous = filing_tracker.latest_two_filings("AAA", "10-K")
    assert current["accn"] == "acc-1"
    assert previous is None


def test_latest_two_filings_without_any_filing_returns_none_none(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    current, previous = filing_tracker.latest_two_filings("NUNCA", "10-K")
    assert current is None and previous is None


def test_compare_filing_metrics_flags_material_revenue_growth_as_improvement():
    previous = {"revenue": 1000.0, "operating_margin": 0.20, "fcf": 200.0, "debt": 100.0, "cash": 50.0, "roic": 0.10}
    current = {"revenue": 1200.0, "operating_margin": 0.20, "fcf": 200.0, "debt": 100.0, "cash": 50.0, "roic": 0.10}
    rows = filing_tracker.compare_filing_metrics(previous, current)
    revenue_row = next(r for r in rows if r["metric"] == "revenue")
    assert revenue_row["severity"] == "MATERIAL"
    assert revenue_row["direction"] == "improvement"
    assert revenue_row["pct_change"] == 0.2


def test_compare_filing_metrics_flags_debt_increase_as_deterioration():
    previous = {"debt": 100.0}
    current = {"debt": 130.0}  # +30%, por encima del umbral (15%)
    rows = filing_tracker.compare_filing_metrics(previous, current)
    debt_row = next(r for r in rows if r["metric"] == "debt")
    assert debt_row["severity"] == "MATERIAL"
    assert debt_row["direction"] == "deterioration"  # más deuda es peor, aunque el número suba


def test_compare_filing_metrics_below_threshold_is_stable_info():
    previous = {"revenue": 1000.0}
    current = {"revenue": 1050.0}  # +5%, por debajo del umbral (10%)
    rows = filing_tracker.compare_filing_metrics(previous, current)
    assert rows[0]["severity"] == "INFO"
    assert rows[0]["direction"] == "stable"


def test_compare_filing_metrics_margin_uses_absolute_points_not_relative_pct():
    # +2pp (20% -> 22%) es +10% relativo -- por encima del umbral relativo
    # pero por debajo del umbral en puntos absolutos (5pp) -- no debe marcar MATERIAL.
    previous = {"operating_margin": 0.20}
    current = {"operating_margin": 0.22}
    rows = filing_tracker.compare_filing_metrics(previous, current)
    assert rows[0]["severity"] == "INFO"


def test_compare_filing_metrics_skips_metrics_missing_in_either_side():
    previous = {"revenue": 1000.0, "roic": None}
    current = {"revenue": 1200.0}  # roic falta en current, debt falta en ambos
    rows = filing_tracker.compare_filing_metrics(previous, current)
    assert {r["metric"] for r in rows} == {"revenue"}


def test_compare_filing_metrics_is_deterministic():
    previous = {"revenue": 1000.0, "fcf": 200.0}
    current = {"revenue": 1200.0, "fcf": 100.0}
    assert filing_tracker.compare_filing_metrics(previous, current) == filing_tracker.compare_filing_metrics(previous, current)


def test_compare_filings_without_any_filing_gives_reason_not_crash(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    result = filing_tracker.compare_filings("NUNCA", "10-K")
    assert result["rows"] == []
    assert result["current"] is None
    assert result["reason"]


def test_compare_filings_with_single_filing_gives_reason_not_crash(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    _seed_filing("AAA", "acc-1", "10-K", "2023-01-01", "2023-12-31", "2024-02-01",
                revenue=100, operating_income=10, gross_profit=40, ocf=15, capex=5,
                net_income=8, equity=50, debt=20, cash=30)
    result = filing_tracker.compare_filings("AAA", "10-K")
    assert result["rows"] == []
    assert result["current"] is not None
    assert result["previous"] is None
    assert "comparable anterior" in result["reason"]


def test_compare_filings_end_to_end_identifies_current_and_previous(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    _seed_cik("AAA", "0000000001")
    _seed_filing("AAA", "acc-2023", "10-K", "2023-01-01", "2023-12-31", "2024-02-01",
                revenue=1000, operating_income=200, gross_profit=500, ocf=250, capex=50,
                net_income=150, equity=600, debt=200, cash=300)
    _seed_filing("AAA", "acc-2024", "10-K", "2024-01-01", "2024-12-31", "2025-02-01",
                revenue=1300, operating_income=220, gross_profit=550, ocf=260, capex=60,
                net_income=160, equity=650, debt=350, cash=310)  # revenue +30%, debt +75%

    result = filing_tracker.compare_filings("AAA", "10-K")
    assert result["reason"] is None
    assert result["current"]["accn"] == "acc-2024"
    assert result["previous"]["accn"] == "acc-2023"
    by_metric = {r["metric"]: r for r in result["rows"]}
    assert by_metric["revenue"]["severity"] == "MATERIAL"
    assert by_metric["revenue"]["direction"] == "improvement"
    assert by_metric["debt"]["severity"] == "MATERIAL"
    assert by_metric["debt"]["direction"] == "deterioration"


def test_compare_filings_quarterly_uses_quarter_only_facts(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    _seed_cik("AAA", "0000000001")
    _seed_filing("AAA", "acc-q1", "10-Q", "2024-01-01", "2024-03-31", "2024-05-01",
                revenue=300, operating_income=50, gross_profit=150, ocf=60, capex=10,
                net_income=40, equity=600, debt=200, cash=300)
    _seed_filing("AAA", "acc-q2", "10-Q", "2024-04-01", "2024-06-30", "2024-08-01",
                revenue=360, operating_income=55, gross_profit=170, ocf=65, capex=12,
                net_income=45, equity=610, debt=200, cash=305)  # revenue +20%

    result = filing_tracker.compare_filings("AAA", "10-Q")
    assert result["reason"] is None
    by_metric = {r["metric"]: r for r in result["rows"]}
    assert by_metric["revenue"]["previous_value"] == 300
    assert by_metric["revenue"]["current_value"] == 360
    assert by_metric["revenue"]["severity"] == "MATERIAL"


def test_record_comparison_is_idempotent(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    _seed_cik("AAA", "0000000001")
    _seed_filing("AAA", "acc-2023", "10-K", "2023-01-01", "2023-12-31", "2024-02-01",
                revenue=1000, operating_income=200, gross_profit=500, ocf=250, capex=50,
                net_income=150, equity=600, debt=200, cash=300)
    _seed_filing("AAA", "acc-2024", "10-K", "2024-01-01", "2024-12-31", "2025-02-01",
                revenue=1300, operating_income=220, gross_profit=550, ocf=260, capex=60,
                net_income=160, equity=650, debt=200, cash=310)

    result = filing_tracker.compare_filings("AAA", "10-K")
    filing_tracker.record_comparison(result)
    filing_tracker.record_comparison(result)  # repetido

    with storage.get_connection() as conn:
        conn.executescript(filing_tracker.SCHEMA)
        n = conn.execute("SELECT COUNT(*) FROM filing_comparisons WHERE symbol='AAA'").fetchone()[0]
    assert n == len(result["rows"])


def test_record_comparison_noop_without_previous_filing(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    result = {"symbol": "AAA", "form": "10-K", "rows": [{"metric": "revenue"}], "current": None, "previous": None}
    filing_tracker.record_comparison(result)  # no debe lanzar excepción
    with storage.get_connection() as conn:
        conn.executescript(filing_tracker.SCHEMA)
        n = conn.execute("SELECT COUNT(*) FROM filing_comparisons").fetchone()[0]
    assert n == 0


def test_material_events_for_signal_monitor_only_includes_material_rows(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    _seed_cik("AAA", "0000000001")
    _seed_filing("AAA", "acc-2023", "10-K", "2023-01-01", "2023-12-31", "2024-02-01",
                revenue=1000, operating_income=200, gross_profit=500, ocf=250, capex=50,
                net_income=150, equity=600, debt=200, cash=300)
    _seed_filing("AAA", "acc-2024", "10-K", "2024-01-01", "2024-12-31", "2025-02-01",
                revenue=1010, operating_income=200, gross_profit=500, ocf=250, capex=50,
                net_income=150, equity=600, debt=350, cash=300)  # solo debt cambia materialmente (+75%)

    result = filing_tracker.compare_filings("AAA", "10-K")
    events = filing_tracker.material_events_for_signal_monitor(result)
    assert len(events) == 1
    assert events[0]["symbol"] == "AAA"
    assert events[0]["event_type"] == "filing_debt_deterioration"
    assert events[0]["severity"] == "MATERIAL"
    assert "10-K" in events[0]["cause"]


def test_material_events_for_signal_monitor_empty_without_previous_filing(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    _seed_filing("AAA", "acc-1", "10-K", "2023-01-01", "2023-12-31", "2024-02-01",
                revenue=100, operating_income=10, gross_profit=40, ocf=15, capex=5,
                net_income=8, equity=50, debt=20, cash=30)
    result = filing_tracker.compare_filings("AAA", "10-K")
    assert filing_tracker.material_events_for_signal_monitor(result) == []
