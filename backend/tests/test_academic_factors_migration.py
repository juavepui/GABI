"""Original factor math and CSV bytes against bounded, explicit modern ports."""

import hashlib
import io
import json
import types
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gabi.application.research.academic_factors import prepare_factor_snapshot, read_cached_factors, refresh_factors
from gabi.domain.research import academic_factors as factors
from gabi.infrastructure.providers.academic_factors import FF5_URL, FrenchFactorSource
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.academic_factors import FileFactorCache

REFERENCE = json.loads((Path(__file__).parent / "fixtures/academic_factors_migration.json").read_text(encoding="utf-8"))
FIVE = "header\n202301,1,.1,.2,.3,.4,.01\n202302,2,.2,.3,.4,.5,.02\n202303,3,.3,.4,.5,.6,.03\n2023,8,8,8,8,8,8\n"
MOMENTUM = "header\n202301,.5\n202302,.6\n202304,.7\n"


class Source:
    def __init__(self):
        self.calls = 0

    def tables(self):
        self.calls += 1
        return FIVE, MOMENTUM


def original():
    module = types.ModuleType("gabi._academic_reference")
    module.__package__ = "gabi"
    exec(compile(REFERENCE["original_source"], "original_academic_factors", "exec"), module.__dict__)
    return module


@pytest.mark.parametrize("lags", [None, 0, 1, 3, 35])
def test_full_ols_hac_reference_is_exact(lags):
    rng = np.random.default_rng(71)
    matrix = np.column_stack([np.ones(36), rng.normal(0, .03, (36, 6))])
    values = matrix @ np.array([.01, .97, -.2, .3, .5, .1, .2]) + rng.normal(0, .015, 36)
    names = ["alpha", *factors.DEFAULT_FACTOR_COLS]
    assert factors._ols(values, matrix, names, hac_lags=lags) == original()._ols(values, matrix, names, hac_lags=lags)


@pytest.mark.parametrize("months", [1, 3, 6, 12])
def test_full_aligned_regression_reference_is_exact(months):
    rng = np.random.default_rng(42)
    dates = pd.date_range("2000-01-01", periods=36 * months, freq="MS")
    frame = pd.DataFrame(rng.normal(.005, .02, (len(dates), 6)), index=dates, columns=factors.DEFAULT_FACTOR_COLS)
    frame["RF"] = .001
    rows = [{"fecha": date, "hasta": date + pd.DateOffset(months=months), "retorno": float(rng.normal(.02, .05))}
            for date in dates[::months]]
    periods = pd.DataFrame(rows).sample(frac=1, random_state=31)
    assert factors.regress_returns_on_factors(periods, frame) == original().regress_returns_on_factors(periods, frame)


@pytest.mark.parametrize("text", [FIVE, "annual\n2023,1,2,3,4,5,6\n", "202301,nan,0,0,0,0,0\n202302,bad,0,0,0,0,0\n"])
def test_monthly_parser_keeps_original_units_absences_and_order(text):
    columns = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"]
    pd.testing.assert_frame_equal(factors._parse_monthly_csv(text, columns), original()._parse_monthly_csv(text, columns))


def test_whole_fresh_cache_and_cached_bytes_match_original(tmp_path):
    old = original()
    old.config = types.SimpleNamespace(DATA_DIR=tmp_path / "old")
    old._download_zip_csv = lambda url: FIVE if "5_Factors" in url else MOMENTUM
    expected = old.fetch_ff_factors()
    cache = FileFactorCache(tmp_path / "new")
    source = Source()
    snapshot = prepare_factor_snapshot(cache, source)
    pd.testing.assert_frame_equal(snapshot.factors, expected)
    assert cache.path.read_bytes() == (tmp_path / "old/ff_factors.csv").read_bytes()
    assert snapshot.source["sha256"] == hashlib.sha256(cache.path.read_bytes()).hexdigest()
    assert list(snapshot.factors.columns) == ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF", "Mom"]
    assert list(snapshot.factors.index) == list(pd.to_datetime(["2023-01-01", "2023-02-01"]))
    pd.testing.assert_frame_equal(prepare_factor_snapshot(cache, source).factors, old.fetch_ff_factors())
    assert source.calls == 1
    prepare_factor_snapshot(cache, source, force_refresh=True)
    assert source.calls == 2
    assert not list(cache.path.parent.glob(".ff_factors_*"))


def test_read_query_has_no_write_or_download_and_missing_cache_stays_missing(tmp_path, monkeypatch):
    cache = FileFactorCache(tmp_path / "missing")
    assert read_cached_factors(cache) is None
    assert not cache.path.parent.exists()
    refresh_factors(cache, Source())
    before = cache.path.read_bytes()
    monkeypatch.setattr(cache, "save_snapshot", lambda *args: pytest.fail("no cache write"))
    monkeypatch.setattr(FrenchFactorSource, "tables", lambda *args: pytest.fail("no network"))
    assert read_cached_factors(cache) is not None
    assert cache.path.read_bytes() == before


@pytest.mark.parametrize("limits", [{"max_bytes": 1}, {"max_rows": 1}])
def test_resource_limits_preserve_existing_cache_on_failed_refresh(tmp_path, limits):
    cache = FileFactorCache(tmp_path)
    refresh_factors(cache, Source())
    before = cache.path.read_bytes()
    bounded = FileFactorCache(tmp_path, **limits)
    with pytest.raises(ValueError, match="limit"):
        refresh_factors(bounded, Source(), force_refresh=True)
    assert cache.path.read_bytes() == before
    with pytest.raises(ValueError, match="limit"):
        read_cached_factors(bounded)


def test_zip_provider_keeps_first_csv_headers_timeout_and_decoding(monkeypatch):
    from gabi.infrastructure.providers import academic_factors as provider

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("first.csv", b"header\xff\n202301,1\n")
        archive.writestr("ignored.csv", b"other")
    calls = []

    class Response:
        content = stream.getvalue()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def iter_content(self, chunk_size):
            assert chunk_size == 64_000
            yield self.content

        def raise_for_status(self):
            calls.append("status")

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(provider.requests, "get", get)
    assert FrenchFactorSource().csv(FF5_URL) == "header\ufffd\n202301,1\n"
    assert calls == [(FF5_URL, {"timeout": 30, "headers": provider.HEADERS, "stream": True}), "status"]
    for source in (FrenchFactorSource(max_zip_bytes=1), FrenchFactorSource(max_csv_bytes=1)):
        with pytest.raises(ValueError, match="limit"):
            source.csv(FF5_URL)


def test_compatibility_default_factor_overrides_are_retained(monkeypatch):
    from gabi import academic_factors as facade

    captured = []

    def regression(*args, **kwargs):
        captured.append(args[2])
        return {}

    monkeypatch.setattr(facade, "DEFAULT_FACTOR_COLS", ["Mkt-RF"])
    monkeypatch.setattr(factors, "regress_returns_on_factors", regression)
    facade.regress_returns_on_factors(pd.DataFrame(), pd.DataFrame())
    assert captured == [["Mkt-RF"]]
    assert isinstance(factors.DEFAULT_FACTOR_COLS, tuple)


def test_worker_bootstrap_uses_explicit_cache_without_legacy_factor_fetch(tmp_path, monkeypatch):
    from gabi import academic_factors as facade
    from gabi_cli.bootstrap import build_executor

    refresh_factors(FileFactorCache(tmp_path), Source())
    monkeypatch.setattr(facade, "fetch_ff_factors", lambda *args: pytest.fail("legacy factor cache"))
    monkeypatch.setattr(FrenchFactorSource, "tables", lambda *args: pytest.fail("network on cache hit"))
    executor = build_executor(Settings(tmp_path))
    assert executor.factor_loader is not None
    snapshot = executor.factor_loader()
    assert snapshot.source["file"] == "ff_factors.csv"
    assert snapshot.source["sha256"] == hashlib.sha256((tmp_path / "ff_factors.csv").read_bytes()).hexdigest()
