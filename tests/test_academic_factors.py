import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi import academic_factors as af, config


def test_parse_monthly_csv_ignores_annual_section():
    text = (
        "Some header text\n"
        ",Mkt-RF,SMB\n"
        "202301,   1.50,   0.30\n"
        "202302,  -2.00,   0.10\n"
        "\n"
        "Annual\n"
        "2023,  -5.00,   2.00\n"
    )
    df = af._parse_monthly_csv(text, ["Mkt-RF", "SMB"])
    assert len(df) == 2
    assert df.index[0] == pd.Timestamp("2023-01-01")
    assert df["Mkt-RF"].iloc[0] == pytest.approx(.015)  # dividido por 100
    assert df["SMB"].iloc[1] == pytest.approx(.001)


def test_quarterly_period_return_compounds_monthly_returns():
    factors = pd.DataFrame(
        {"Mkt-RF": [.01, .02, -.01]},
        index=pd.to_datetime(["2023-01-01", "2023-02-01", "2023-03-01"]),
    )
    ret = af.quarterly_period_return(factors, "Mkt-RF", "2023-01-02", "2023-04-02")
    expected = (1.01 * 1.02 * .99) - 1
    assert ret == pytest.approx(expected)


def test_quarterly_period_return_none_when_no_data_in_window():
    factors = pd.DataFrame({"Mkt-RF": [.01]}, index=pd.to_datetime(["2020-01-01"]))
    assert af.quarterly_period_return(factors, "Mkt-RF", "2023-01-02", "2023-04-02") is None


def test_ols_recovers_exact_coefficients_without_noise():
    rng = np.random.default_rng(0)
    x1 = rng.normal(size=50)
    x2 = rng.normal(size=50)
    y = 0.02 + 3 * x1 - 1.5 * x2  # sin ruido: alfa=0.02, beta1=3, beta2=-1.5
    X = np.column_stack([np.ones(50), x1, x2])
    result = af._ols(y, X, ["alpha", "b1", "b2"])
    assert result["coef"]["alpha"] == pytest.approx(0.02, abs=1e-8)
    assert result["coef"]["b1"] == pytest.approx(3.0, abs=1e-8)
    assert result["coef"]["b2"] == pytest.approx(-1.5, abs=1e-8)
    assert result["r2"] == pytest.approx(1.0, abs=1e-6)


def test_regress_returns_on_factors_end_to_end():
    dates = pd.date_range("2020-01-01", periods=48, freq="MS")
    rng = np.random.default_rng(1)
    factors = pd.DataFrame({
        "Mkt-RF": rng.normal(0.005, 0.02, len(dates)),
        "SMB": rng.normal(0, 0.01, len(dates)),
        "HML": rng.normal(0, 0.01, len(dates)),
        "RMW": rng.normal(0, 0.01, len(dates)),
        "CMA": rng.normal(0, 0.01, len(dates)),
        "Mom": rng.normal(0, 0.01, len(dates)),
        "RF": np.full(len(dates), 0.001),
    }, index=dates)

    period_rows = []
    current = pd.Timestamp("2020-01-02")
    end_ts = pd.Timestamp("2023-10-02")
    while current + pd.DateOffset(months=3) <= end_ts:
        end = current + pd.DateOffset(months=3)
        mkt = af.quarterly_period_return(factors, "Mkt-RF", current.isoformat(), end.isoformat())
        # retorno de GABI = 1x el factor de mercado, sin alfa real -- para
        # comprobar que la regresion no "descubre" alfa donde no lo hay.
        period_rows.append({"fecha": current.date().isoformat(), "hasta": end.date().isoformat(),
                            "retorno": mkt if mkt is not None else 0})
        current = end
    period_returns = pd.DataFrame(period_rows)

    result = af.regress_returns_on_factors(period_returns, factors)
    assert result["periodos_alineados"] == len(period_returns)
    assert result["coef"]["Mkt-RF"] == pytest.approx(1.0, abs=.05)
    assert abs(result["coef"]["alpha"]) < 0.01  # sin alfa real: debe salir cerca de 0


def test_regress_returns_on_factors_raises_with_too_few_aligned_periods():
    factors = pd.DataFrame({c: [] for c in af.DEFAULT_FACTOR_COLS + ["RF"]}, index=pd.DatetimeIndex([]))
    period_returns = pd.DataFrame([{"fecha": "2020-01-02", "hasta": "2020-04-02", "retorno": .05}])
    with pytest.raises(ValueError, match="insuficientes"):
        af.regress_returns_on_factors(period_returns, factors)


def test_fetch_ff_factors_caches_to_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)

    five_csv = "hdr\n,Mkt-RF,SMB,HML,RMW,CMA,RF\n202301,   1.00,   0.10,   0.20,   0.30,   0.40,   0.01\n"
    mom_csv = "hdr\n,Mom\n202301,   0.50\n"
    calls = []

    def fake_download(url):
        calls.append(url)
        return five_csv if "5_Factors" in url else mom_csv

    monkeypatch.setattr(af, "_download_zip_csv", fake_download)
    df = af.fetch_ff_factors()
    assert len(calls) == 2
    assert list(df.columns) == ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF", "Mom"]
    assert (tmp_path / "ff_factors.csv").exists()

    # segunda llamada: debe usar el caché, sin volver a descargar
    df2 = af.fetch_ff_factors()
    assert len(calls) == 2
    assert df2["Mkt-RF"].iloc[0] == pytest.approx(.01)
