import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi import academic_factors as af
from gabi import config


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


def test_hac_intercept_only_matches_hand_calculation():
    # mean=3, residuals=(-2,-1,1,0,2), sum(e²)=10, sum(e[t]*e[t-1])=1.
    # Bartlett L=1: meat=10+2*(1/2)*1=11; cov=11/5² * 5/4 = .55.
    result = af._ols(np.array([1., 2., 4., 3., 5.]), np.ones((5, 1)), ["alpha"], hac_lags=1)
    assert result["coef"]["alpha"] == pytest.approx(3)
    assert result["se"]["alpha"] == pytest.approx(np.sqrt(.55))
    assert result["t_stat"]["alpha"] == pytest.approx(3 / np.sqrt(.55))
    assert result["se_ols"]["alpha"] == pytest.approx(np.sqrt(.5))


@pytest.mark.parametrize("lags", [0, 1, 3, 4, 35])
def test_hac_matches_dense_bartlett_covariance_for_all_coefficients(lags):
    # Independent dense temporal kernel formulation; includes six factors,
    # nonconstant residual variance, HC1 (L=0), and the boundary L=n-1.
    rng = np.random.default_rng(21)
    n, k = 36, 7
    X = np.column_stack([np.ones(n), rng.normal(0, .03, (n, k - 1))])
    y = X @ np.array([.01, .97, -.2, .3, .5, .1, .2]) + rng.normal(size=n) * np.linspace(.01, .04, n)
    beta = np.linalg.solve(X.T @ X, X.T @ y)
    residuals = y - X @ beta
    distance = np.abs(np.arange(n)[:, None] - np.arange(n)[None, :])
    kernel = np.maximum(1 - distance / (lags + 1), 0)
    omega = kernel * np.outer(residuals, residuals)
    bread = np.linalg.inv(X.T @ X)
    expected_cov = bread @ X.T @ omega @ X @ bread * n / (n - k)
    names = ["alpha"] + af.DEFAULT_FACTOR_COLS
    result = af._ols(y, X, names, hac_lags=lags)
    expected_se = np.sqrt(np.diag(expected_cov))
    np.testing.assert_allclose(list(result["se"].values()), expected_se, rtol=1e-10)
    np.testing.assert_allclose(list(result["t_stat"].values()), beta / expected_se, rtol=1e-10)
    np.testing.assert_allclose(list(result["coef"].values()), beta, rtol=1e-10)
    classical_se = np.sqrt(np.diag(bread) * (residuals @ residuals) / (n - k))
    np.testing.assert_allclose(list(result["se_ols"].values()), classical_se, rtol=1e-10)
    assert result["hac_lags"] == lags
    assert result["cov_type"] == "HAC"
    assert result["hac_kernel"] == "bartlett"
    assert result["hac_small_sample_correction"] is True


def test_hac_reduces_alpha_t_stat_with_persistent_residuals():
    rng = np.random.default_rng(42)
    residuals = np.zeros(500)
    for t in range(1, len(residuals)):
        residuals[t] = .85 * residuals[t - 1] + rng.normal(0, .01)
    result = af._ols(.02 + residuals, np.ones((500, 1)), ["alpha"], hac_lags=4)
    assert result["se"]["alpha"] > result["se_ols"]["alpha"]
    assert abs(result["t_stat"]["alpha"]) < abs(result["t_stat_ols"]["alpha"])


@pytest.mark.parametrize("lags", [-1, 5, 1.5, True, "3"])
def test_hac_rejects_invalid_lags(lags):
    with pytest.raises(ValueError, match="hac_lags"):
        af._ols(np.arange(5.), np.ones((5, 1)), ["alpha"], hac_lags=lags)


@pytest.mark.parametrize("case", ["singular", "no_dof", "nan", "inf"])
def test_hac_rejects_unidentifiable_or_nonfinite_regressions(case):
    X = np.column_stack([np.ones(5), np.arange(5.)])
    y = np.arange(5.)
    if case == "singular":
        X[:, 1] = 1
    elif case == "no_dof":
        X, y = X[:2], y[:2]
    elif case == "nan":
        y[0] = np.nan
    else:
        X[0, 1] = np.inf
    with pytest.raises(ValueError):
        af._ols(y, X, ["alpha", "factor"])


def _noisy_periods(months=3):
    dates = pd.date_range("2010-01-01", periods=36 * months, freq="MS")
    rng = np.random.default_rng(23)
    factors = pd.DataFrame({"Mkt-RF": rng.normal(.005, .02, len(dates)), "RF": .001}, index=dates)
    rows = []
    for start in dates[::months]:
        end = start + pd.DateOffset(months=months)
        market = af.quarterly_period_return(factors, "Mkt-RF", start, end)
        rf = af.quarterly_period_return(factors, "RF", start, end)
        rows.append({"fecha": start, "hasta": end, "retorno": rf + .01 + .9 * market + rng.normal(0, .01)})
    return pd.DataFrame(rows), factors


@pytest.mark.parametrize("months", [1, 3, 6, 12])
def test_regression_hac_order_lags_and_annualization(months):
    periods, factors = _noisy_periods(months)
    result = af.regress_returns_on_factors(periods, factors, ["Mkt-RF"])
    shuffled = af.regress_returns_on_factors(periods.sample(frac=1, random_state=5), factors, ["Mkt-RF"])
    assert shuffled == result
    assert result["hac_lags"] == 3
    assert result["periods_per_year"] == 12 / months
    assert result["alpha_anualizado"] == pytest.approx((1 + result["coef"]["alpha"]) ** (12 / months) - 1)
    overridden = af.regress_returns_on_factors(periods, factors, ["Mkt-RF"], hac_lags=4)
    assert overridden["hac_lags"] == 4
    assert overridden["coef"] == result["coef"]
    assert overridden["r2"] == result["r2"]
    assert overridden["se_ols"] == result["se_ols"]
    assert overridden["se"]["alpha"] != result["se"]["alpha"]


@pytest.mark.parametrize("case", ["gap", "duplicate", "duration", "missing_factors"])
def test_regression_rejects_irregular_hac_time_axis(case):
    periods, factors = _noisy_periods()
    if case == "gap":
        periods = periods.drop(index=5)
    elif case == "duplicate":
        periods = pd.concat([periods, periods.iloc[[5]]])
    elif case == "duration":
        periods.loc[5, "hasta"] += pd.DateOffset(months=1)
    else:
        factors = factors.drop(factors.index[15:18])
    with pytest.raises(ValueError, match="consecutivos"):
        af.regress_returns_on_factors(periods, factors, ["Mkt-RF"])
