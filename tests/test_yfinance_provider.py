"""A-7, A-13: YFinanceProvider. Offline tests use a fake yfinance module; the live test needs network."""

import datetime as dt
import json
import logging
import sys
import types

import numpy as np
import pandas as pd
import pytest

from alphaforge import config
from alphaforge.data.csv_provider import CsvProvider
from alphaforge.data.provider import clear_provider_cache, get_provider
from alphaforge.data.yfinance_provider import YFinanceProvider, to_long

DAYS = pd.bdate_range("2026-11-02", "2026-11-12")
FIELDS = ["Adj Close", "Close", "High", "Low", "Open", "Volume"]


def _fake_download(tickers, **kwargs):
    """Mimic yf.download(group_by="column"): columns MultiIndex (Price, Ticker)."""
    tickers = [tickers] if isinstance(tickers, str) else list(tickers)
    cols = pd.MultiIndex.from_product([FIELDS, tickers], names=["Price", "Ticker"])
    data = np.tile(np.arange(len(DAYS), dtype=float)[:, None] + 100.0, (1, len(cols)))
    df = pd.DataFrame(data, index=pd.DatetimeIndex(DAYS, name="Date"), columns=cols)
    if "CAD=X" in tickers:
        for f in FIELDS:
            df.loc[:, (f, "CAD=X")] = 1.40
    return df


class _FakeTicker:
    def __init__(self, ticker):
        idx = pd.DatetimeIndex([DAYS[3]], tz="America/New_York")
        self.actions = pd.DataFrame(
            {"Dividends": [0.5 if ticker == "SPY" else 0.0], "Stock Splits": [0.0]},
            index=idx,
        )


@pytest.fixture
def fake_yf(monkeypatch):
    mod = types.ModuleType("yfinance")
    mod.download = _fake_download
    mod.Ticker = _FakeTicker
    monkeypatch.setitem(sys.modules, "yfinance", mod)
    YFinanceProvider._fallback_warned = False
    clear_provider_cache()
    return mod


def test_prices_have_the_same_shape_as_csv(fake_yf, tmp_path):
    yp = YFinanceProvider(cache_dir=tmp_path, end="2026-11-12")
    got = yp.prices(["SPY", "RY.TO"])
    want = CsvProvider().prices(["SPY", "RY.TO"])
    assert list(got.columns) == list(want.columns)
    assert set(got["ticker"]) == {"SPY", "RY.TO"}
    assert got.loc[got["ticker"] == "RY.TO", "currency"].eq("CAD").all()
    assert pd.api.types.is_datetime64_any_dtype(got["date"])
    assert len(got) == 2 * len(DAYS)


def test_fx_and_prices_cad_work_end_to_end(fake_yf, tmp_path):
    yp = YFinanceProvider(cache_dir=tmp_path, end="2026-11-12")
    fx = yp.fx()
    assert list(fx.columns) == ["date", "usdcad", "cadusd"]
    assert fx["usdcad"].eq(1.40).all()
    w = yp.prices_cad(["SPY", "RY.TO", "BTC-USD"], "2026-11-12")
    assert not w.isna().any().any()
    assert w["SPY"].iloc[0] == pytest.approx(100.0 * 1.40)  # USD converted with CAD=X
    assert w["RY.TO"].iloc[0] == pytest.approx(100.0)  # CAD untouched


def test_universe_and_macro_come_from_the_starter_csvs(fake_yf, tmp_path):
    yp = YFinanceProvider(cache_dir=tmp_path, end="2026-11-12")
    assert yp.universe().equals(CsvProvider().universe())
    assert yp.macro().equals(CsvProvider().macro())


def test_corporate_actions_from_ticker_actions(fake_yf, tmp_path):
    ca = YFinanceProvider(cache_dir=tmp_path, end="2026-11-12").corporate_actions()
    assert list(ca.columns) == ["ex_date", "ticker", "action", "value", "unit"]
    spy = ca[ca["ticker"] == "SPY"]
    assert spy["action"].tolist() == ["dividend"] and spy["value"].tolist() == [0.5]
    assert spy["ex_date"].iloc[0] == DAYS[3]  # timezone dropped


def test_to_long_accepts_flat_and_ticker_first_layouts():
    flat = _fake_download("SPY").droplevel("Ticker", axis=1)
    assert set(to_long(flat, ["SPY"], {"SPY": "USD"})["ticker"]) == {"SPY"}
    ticker_first = _fake_download(["SPY", "QQQ"]).swaplevel(0, 1, axis=1)
    long = to_long(ticker_first, ["QQQ", "SPY"], {"SPY": "USD", "QQQ": "USD"})
    assert set(long["ticker"]) == {"SPY", "QQQ"} and long["adj_close"].notna().all()


def test_missing_yfinance_gives_a_clear_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "yfinance", None)
    with pytest.raises(RuntimeError, match="yfinance"):
        YFinanceProvider(end="2026-11-12").prices(["SPY"])


def test_get_provider_selects_yfinance(fake_yf):
    assert get_provider("yfinance").name == "yfinance"  # nothing downloaded until used


def test_cache_hit_avoids_second_download(fake_yf, tmp_path):
    call_count = 0
    orig_download = fake_yf.download

    def counted_download(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return orig_download(*args, **kwargs)

    fake_yf.download = counted_download

    yp1 = YFinanceProvider(cache_dir=tmp_path, end="2026-11-12")
    _ = yp1.prices(["SPY"])
    assert call_count == 1
    assert (tmp_path / "metadata.json").exists()
    assert (tmp_path / "prices.csv").exists()
    assert (tmp_path / "fx.csv").exists()

    # Second instance with same cache_dir hits cache without re-downloading
    yp2 = YFinanceProvider(cache_dir=tmp_path, end="2026-11-12")
    _ = yp2.prices(["SPY"])
    assert call_count == 1


def test_ttl_expiry_redownloads(fake_yf, tmp_path):
    call_count = 0
    orig_download = fake_yf.download

    def counted_download(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return orig_download(*args, **kwargs)

    fake_yf.download = counted_download

    # 1. First download
    yp1 = YFinanceProvider(cache_dir=tmp_path, cache_hours=12, end="2026-11-12")
    _ = yp1.prices(["SPY"])
    assert call_count == 1

    # 2. Age metadata to 13 hours ago (TTL is 12)
    meta_path = tmp_path / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["downloaded_at"] = (
        dt.datetime.now(dt.UTC) - dt.timedelta(hours=13)
    ).isoformat()
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    # 3. New instance with expired TTL re-downloads
    yp2 = YFinanceProvider(cache_dir=tmp_path, cache_hours=12, end="2026-11-12")
    _ = yp2.prices(["SPY"])
    assert call_count == 2


def test_failure_whole_dataset_csv_fallback(fake_yf, tmp_path, caplog):
    def failing_download(*args, **kwargs):
        raise ConnectionError("Yahoo Finance rate limited or blocked IP")

    fake_yf.download = failing_download
    yp = YFinanceProvider(cache_dir=tmp_path, end="2026-11-12")

    with caplog.at_level(logging.WARNING):
        prices = yp.prices(["SPY"])
        fx = yp.fx()
        ca = yp.corporate_actions()

    assert yp.fallback is True
    csv_p = CsvProvider()
    assert len(prices) == len(csv_p.prices(["SPY"], end="2026-11-12"))
    assert len(fx) == len(csv_p.fx())
    assert len(ca) == len(csv_p.corporate_actions())
    assert yp.evidence_source == "prices_daily.csv + fx_usdcad_daily.csv"
    assert yp.default_as_of == config.DEFAULT_AS_OF
    # Logged warning once
    warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("falling back to starter CSV" in m for m in warnings)


def test_empty_frame_triggers_fallback(fake_yf, tmp_path):
    fake_yf.download = lambda *args, **kwargs: pd.DataFrame()
    yp = YFinanceProvider(cache_dir=tmp_path, end="2026-11-12")
    prices = yp.prices(["SPY"])
    assert yp.fallback is True
    assert len(prices) > 0


def test_too_little_history_triggers_fallback(fake_yf, tmp_path):
    # Only return 2 rows total (< 5 observations)
    orig = fake_yf.download

    def short_download(*args, **kwargs):
        df = orig(*args, **kwargs)
        return df.iloc[:2]

    fake_yf.download = short_download
    yp = YFinanceProvider(cache_dir=tmp_path, end="2026-11-12")
    _ = yp.prices(["SPY"])
    assert yp.fallback is True


def test_health_payload_csv_and_yfinance(fake_yf, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from alphaforge.api.server import app

    client = TestClient(app)

    # 1. CSV
    monkeypatch.setenv("AF_DATA_PROVIDER", "csv")
    clear_provider_cache()
    resp_csv = client.get("/health")
    assert resp_csv.status_code == 200
    d_csv = resp_csv.json()
    assert d_csv["status"] == "ok"
    assert d_csv["data_provider"] == "csv"
    assert d_csv["data_as_of"] == "2026-11-12"
    assert d_csv["fallback"] is False

    # 2. YFinance live / successful
    monkeypatch.setenv("AF_DATA_PROVIDER", "yfinance")
    monkeypatch.setenv("AF_YF_CACHE_DIR", str(tmp_path))
    clear_provider_cache()
    resp_yf = client.get("/health")
    assert resp_yf.status_code == 200
    d_yf = resp_yf.json()
    assert d_yf["status"] == "ok"
    assert d_yf["data_provider"] == "yfinance"
    assert d_yf["data_as_of"] == "2026-11-12"  # from fake_yf DAYS[-1]
    assert d_yf["fallback"] is False

    # 3. YFinance failure -> fallback
    clear_provider_cache()
    fake_yf.download = lambda *args, **kwargs: None
    fb_dir = tmp_path / "fb_dir"
    monkeypatch.setenv("AF_YF_CACHE_DIR", str(fb_dir))
    resp_fb = client.get("/health")
    assert resp_fb.status_code == 200
    d_fb = resp_fb.json()
    assert d_fb["status"] == "ok"
    assert d_fb["data_provider"] == "yfinance"
    assert d_fb["data_as_of"] == "2026-11-12"
    assert d_fb["fallback"] is True


def test_evidence_source_text(fake_yf, tmp_path, monkeypatch):
    from alphaforge.nodes.quant import quant_node
    from alphaforge.state import GraphState

    monkeypatch.setenv("AF_DATA_PROVIDER", "yfinance")
    monkeypatch.setenv("AF_YF_CACHE_DIR", str(tmp_path))
    clear_provider_cache()

    state = GraphState(
        persona="robert",
        request_text="test",
        as_of_date=dt.date(2026, 11, 12),
        eligible_universe=["SPY", "RY.TO"],
    )
    res = quant_node(state)
    ev = res["evidence"]
    price_ev = [e for e in ev.values() if "Historique trop court" in str(e.value)]
    assert len(price_ev) > 0
    today_str = dt.date.today().isoformat()
    assert price_ev[0].source == f"Yahoo Finance via yfinance, téléchargé le {today_str}"

    # Now with fallback
    clear_provider_cache()
    fake_yf.download = lambda *args, **kwargs: None
    fb_dir = tmp_path / "fb_quant"
    monkeypatch.setenv("AF_YF_CACHE_DIR", str(fb_dir))
    res_fb = quant_node(state)
    ev_fb = res_fb["evidence"]
    vol_fb = [
        e
        for e in ev_fb.values()
        if isinstance(e.value, dict)
        and e.value.get("metric") == "volatility_ann"
    ]
    assert len(vol_fb) > 0
    assert vol_fb[0].source == "prices_daily.csv + fx_usdcad_daily.csv"


def test_as_of_date_selection(fake_yf, tmp_path, monkeypatch):
    from alphaforge.graph import initial_state

    # 1. CSV provider -> default 2026-11-12
    monkeypatch.setenv("AF_DATA_PROVIDER", "csv")
    clear_provider_cache()
    st_csv = initial_state("robert", "test")
    assert st_csv["as_of_date"] == dt.date(2026, 11, 12)

    # 2. YFinance provider -> last available trading day in data
    monkeypatch.setenv("AF_DATA_PROVIDER", "yfinance")
    monkeypatch.setenv("AF_YF_CACHE_DIR", str(tmp_path))
    clear_provider_cache()
    st_yf = initial_state("robert", "test")
    assert st_yf["as_of_date"] == DAYS[-1].date()


@pytest.mark.live
def test_live_spy_month_matches_csv():
    pytest.importorskip("yfinance")
    start, end = dt.date(2026, 10, 1), dt.date(2026, 10, 30)
    live = (
        YFinanceProvider(start=start, end=end).prices(["SPY"]).set_index("date")["close"]
    )
    csv = CsvProvider().prices(["SPY"], start=start, end=end).set_index("date")["close"]
    both = pd.concat([live, csv], axis=1, keys=["live", "csv"]).dropna()
    assert len(both) >= 15
    assert ((both["live"] / both["csv"] - 1).abs() < 0.005).all()


def test_symbol_dropped_by_the_batch_is_fetched_again(fake_yf, tmp_path):
    """Live: the threaded batch dropped GLD and the whole site fell back to the frozen dataset."""
    calls = []

    def flaky_download(tickers, **kwargs):
        tickers = [tickers] if isinstance(tickers, str) else list(tickers)
        calls.append((len(tickers), kwargs.get("threads")))
        if len(tickers) > 5:  # the batch: Yahoo returns everything but GLD
            tickers = [t for t in tickers if t != "GLD"]
        return _fake_download(tickers, **kwargs)

    fake_yf.download = flaky_download
    yp = YFinanceProvider(cache_dir=tmp_path, end="2026-11-12")
    got = yp.prices(["GLD", "SPY"])
    assert yp.fallback is False
    assert set(got["ticker"]) == {"GLD", "SPY"}
    assert calls[1] == (1, False)  # only the missing symbol, sequentially


def test_symbol_still_missing_after_the_retry_falls_back(fake_yf, tmp_path):
    def never_gld(tickers, **kwargs):
        tickers = [tickers] if isinstance(tickers, str) else list(tickers)
        rest = [t for t in tickers if t != "GLD"]
        return _fake_download(rest, **kwargs) if rest else pd.DataFrame()

    fake_yf.download = never_gld
    yp = YFinanceProvider(cache_dir=tmp_path, end="2026-11-12")
    yp.prices(["SPY"])
    assert yp.fallback is True
