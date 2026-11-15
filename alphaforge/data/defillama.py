"""DefiLlama crypto context data client (Track A).

Retrieves crypto market context from DefiLlama (free, no API key):
- Ethereum chain Total Value Locked (TVL) at as-of date and 30d/365d changes
- Total circulating USD stablecoin supply at as-of date and 30d change
- Bitcoin (BTC) and Ether (ETH) DefiLlama price at as-of date

Strict AS-OF safety: only points dated on or before `as_of_date` are used.
Endpoints used (only these four):
- https://coins.llama.fi/prices/current/{coins}
- https://coins.llama.fi/chart/{coins}?start={start}&span={span}&period={period}
- https://api.llama.fi/v2/historicalChainTvl/{chain}
- https://stablecoins.llama.fi/stablecoincharts/{chart_type}
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from alphaforge import config

DEFAULT_TIMEOUT_S = 8.0
DEFAULT_CACHE_HOURS = 6.0

PRICES_CURRENT_URL = "https://coins.llama.fi/prices/current/{coins}"
CHART_URL = "https://coins.llama.fi/chart/{coins}"
HISTORICAL_TVL_URL = "https://api.llama.fi/v2/historicalChainTvl/{chain}"
STABLECOIN_CHARTS_URL = "https://stablecoins.llama.fi/stablecoincharts/{chart_type}"


class DefiLlamaContext(BaseModel):
    as_of: dt.date
    eth_tvl: float | None = None
    eth_tvl_date: dt.date | None = None
    eth_tvl_change_30d: float | None = None
    eth_tvl_change_365d: float | None = None
    stablecoin_supply: float | None = None
    stablecoin_date: dt.date | None = None
    stablecoin_change_30d: float | None = None
    btc_price: float | None = None
    btc_price_date: dt.date | None = None
    eth_price: float | None = None
    eth_price_date: dt.date | None = None
    source: str = "DefiLlama"
    urls: dict[str, str] = Field(default_factory=dict)


def _to_date(val: int | str) -> dt.date:
    """Convert unix timestamp (int or string) to UTC date."""
    return dt.datetime.fromtimestamp(int(val), tz=dt.UTC).date()


class DefiLlamaClient:
    """HTTP client with disk cache and committed snapshot fallback."""

    def __init__(
        self,
        cache_dir: Path | str | None = None,
        snapshot_path: Path | str | None = None,
        timeout_s: float | None = None,
        cache_ttl_hours: float | None = None,
        mode: str | None = None,
        http_client: httpx.Client | None = None,
    ):
        self.cache_dir = Path(cache_dir) if cache_dir else config.CACHE_DIR / "defillama"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.snapshot_path = Path(snapshot_path) if snapshot_path else self._find_snapshot()
        self.timeout_s = float(
            timeout_s if timeout_s is not None else os.getenv("AF_LLAMA_TIMEOUT_S", DEFAULT_TIMEOUT_S)
        )
        self.cache_ttl_hours = float(
            cache_ttl_hours
            if cache_ttl_hours is not None
            else os.getenv("AF_LLAMA_CACHE_HOURS", DEFAULT_CACHE_HOURS)
        )
        self.mode = (
            mode if mode is not None else os.getenv("AF_CRYPTO_CONTEXT", "cache")
        ).lower()
        self._client = http_client

    def _find_snapshot(self) -> Path | None:
        candidates = [
            config.CACHE_DIR / "defillama" / "snapshot.json",
        ]
        for p in candidates:
            if p.is_file():
                return p
        return None

    def load_snapshot(self) -> dict | None:
        if self.snapshot_path and self.snapshot_path.is_file():
            try:
                return json.loads(self.snapshot_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
        return None

    def _is_cache_valid(self, path: Path) -> bool:
        if not path.is_file():
            return False
        age_s = time.time() - path.stat().st_mtime
        return age_s < self.cache_ttl_hours * 3600

    def _read_cache(self, key: str) -> Any | None:
        path = self.cache_dir / f"{key}.json"
        if self._is_cache_valid(path):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
        return None

    def _write_cache(self, key: str, data: Any) -> None:
        try:
            path = self.cache_dir / f"{key}.json"
            path.write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            pass

    def _get_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(timeout=self.timeout_s)

    # ------------------------------------------------------------------- 4 endpoints
    def get_prices_current(
        self, coins: str | list[str] = "coingecko:bitcoin,coingecko:ethereum"
    ) -> dict | None:
        """Endpoint 1: current prices."""
        if self.mode == "off":
            return None

        coins_str = ",".join(coins) if isinstance(coins, list) else coins
        cache_key = f"prices_current_{coins_str.replace(':', '_').replace(',', '__')}"

        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        if self.mode == "live":
            url = PRICES_CURRENT_URL.format(coins=coins_str)
            try:
                client = self._get_client()
                resp = client.get(url, headers={"User-Agent": "AlphaForge/1.0"})
                resp.raise_for_status()
                data = resp.json()
                self._write_cache(cache_key, data)
                return data
            except Exception:
                pass

        # Fallback to snapshot
        snap = self.load_snapshot()
        if snap and "prices_current" in snap:
            full_coins = snap["prices_current"].get("coins", {})
            wanted = coins_str.split(",")
            filtered = {k: v for k, v in full_coins.items() if k in wanted}
            if filtered:
                return {"coins": filtered}
            return snap["prices_current"]
        return None

    def get_chart(
        self,
        coins: str | list[str] = "coingecko:bitcoin,coingecko:ethereum",
        start: int | None = None,
        span: int | None = None,
        period: str = "1d",
    ) -> dict | None:
        """Endpoint 2: historical price chart series."""
        if self.mode == "off":
            return None

        coins_str = ",".join(coins) if isinstance(coins, list) else coins
        cache_key = f"chart_{coins_str.replace(':', '_').replace(',', '__')}_{start}_{span}_{period}"

        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        if self.mode == "live":
            url = CHART_URL.format(coins=coins_str)
            params: dict[str, Any] = {"period": period}
            if start is not None:
                params["start"] = start
            if span is not None:
                params["span"] = span
            try:
                client = self._get_client()
                resp = client.get(url, params=params, headers={"User-Agent": "AlphaForge/1.0"})
                resp.raise_for_status()
                data = resp.json()
                self._write_cache(cache_key, data)
                return data
            except Exception:
                pass

        # Fallback to snapshot
        snap = self.load_snapshot()
        if snap and "chart" in snap:
            full_coins = snap["chart"].get("coins", {})
            wanted = coins_str.split(",")
            filtered = {k: v for k, v in full_coins.items() if k in wanted}
            if filtered:
                return {"coins": filtered}
            return snap["chart"]
        return None

    def get_historical_chain_tvl(self, chain: str = "Ethereum") -> list[dict] | None:
        """Endpoint 3: historical chain TVL."""
        if self.mode == "off":
            return None

        cache_key = f"tvl_{chain.lower()}"

        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        if self.mode == "live":
            url = HISTORICAL_TVL_URL.format(chain=chain)
            try:
                client = self._get_client()
                resp = client.get(url, headers={"User-Agent": "AlphaForge/1.0"})
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    self._write_cache(cache_key, data)
                    return data
            except Exception:
                pass

        # Fallback to snapshot
        snap = self.load_snapshot()
        if snap:
            tvl = snap.get(f"tvl_{chain.lower()}") or snap.get("tvl_ethereum") or snap.get("tvl")
            if isinstance(tvl, list):
                return tvl
        return None

    def get_stablecoin_charts(self, chart_type: str = "all") -> list[dict] | None:
        """Endpoint 4: historical stablecoins total circulating."""
        if self.mode == "off":
            return None

        cache_key = f"stablecoins_{chart_type}"

        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        if self.mode == "live":
            url = STABLECOIN_CHARTS_URL.format(chart_type=chart_type)
            try:
                client = self._get_client()
                resp = client.get(url, headers={"User-Agent": "AlphaForge/1.0"})
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    self._write_cache(cache_key, data)
                    return data
            except Exception:
                pass

        # Fallback to snapshot
        snap = self.load_snapshot()
        if snap and "stablecoins" in snap:
            stb = snap["stablecoins"]
            if isinstance(stb, list):
                return stb
        return None

    # ------------------------------------------------------------------- High-level context
    def get_crypto_context(self, as_of: dt.date | None = None) -> DefiLlamaContext | None:
        """Build crypto market context safe as of `as_of`.

        Only points on or before `as_of` are used. Historical series are used for past dates.
        """
        if self.mode == "off":
            return None

        as_of = as_of or config.DEFAULT_AS_OF
        today_utc = dt.datetime.now(dt.UTC).date()

        # 1. Ethereum TVL & changes
        eth_tvl = None
        eth_tvl_date = None
        eth_tvl_change_30d = None
        eth_tvl_change_365d = None

        tvl_data = self.get_historical_chain_tvl("Ethereum")
        if tvl_data:
            valid_tvl = []
            for item in tvl_data:
                if isinstance(item, dict) and "date" in item and "tvl" in item:
                    d = _to_date(item["date"])
                    if d <= as_of:
                        valid_tvl.append((d, float(item["tvl"])))
            valid_tvl.sort(key=lambda x: x[0])
            if valid_tvl:
                eth_tvl_date, eth_tvl = valid_tvl[-1]

                # 30-day change
                target_30d = eth_tvl_date - dt.timedelta(days=30)
                p30 = [x for x in valid_tvl if x[0] <= target_30d]
                if p30 and p30[-1][1] > 0:
                    eth_tvl_change_30d = round(((eth_tvl - p30[-1][1]) / p30[-1][1]) * 100, 4)

                # 365-day change
                target_365d = eth_tvl_date - dt.timedelta(days=365)
                p365 = [x for x in valid_tvl if x[0] <= target_365d]
                if p365 and p365[-1][1] > 0:
                    eth_tvl_change_365d = round(((eth_tvl - p365[-1][1]) / p365[-1][1]) * 100, 4)

        # 2. Stablecoin supply & 30d change
        stablecoin_supply = None
        stablecoin_date = None
        stablecoin_change_30d = None

        stb_data = self.get_stablecoin_charts("all")
        if stb_data:
            valid_stb = []
            for item in stb_data:
                if isinstance(item, dict) and "date" in item:
                    circ = item.get("totalCirculatingUSD", {})
                    pegged = circ.get("peggedUSD")
                    if pegged is not None:
                        d = _to_date(item["date"])
                        if d <= as_of:
                            valid_stb.append((d, float(pegged)))
            valid_stb.sort(key=lambda x: x[0])
            if valid_stb:
                stablecoin_date, stablecoin_supply = valid_stb[-1]
                target_30d = stablecoin_date - dt.timedelta(days=30)
                p30 = [x for x in valid_stb if x[0] <= target_30d]
                if p30 and p30[-1][1] > 0:
                    stablecoin_change_30d = round(((stablecoin_supply - p30[-1][1]) / p30[-1][1]) * 100, 4)

        # 3. BTC and ETH prices
        btc_price = None
        btc_price_date = None
        eth_price = None
        eth_price_date = None

        # AS-OF SAFETY: if as_of is today or future, current prices may be checked
        if as_of >= today_utc:
            curr = self.get_prices_current("coingecko:bitcoin,coingecko:ethereum")
            if curr and "coins" in curr:
                coins_dict = curr["coins"]
                if "coingecko:bitcoin" in coins_dict:
                    b_info = coins_dict["coingecko:bitcoin"]
                    b_date = _to_date(b_info.get("timestamp", 0))
                    if b_date <= as_of:
                        btc_price = float(b_info["price"])
                        btc_price_date = b_date
                if "coingecko:ethereum" in coins_dict:
                    e_info = coins_dict["coingecko:ethereum"]
                    e_date = _to_date(e_info.get("timestamp", 0))
                    if e_date <= as_of:
                        eth_price = float(e_info["price"])
                        eth_price_date = e_date

        # For historical dates or when current prices are unavailable/dated later, use chart
        if btc_price is None or eth_price is None:
            as_of_dt = dt.datetime(as_of.year, as_of.month, as_of.day, 0, 0, 0, tzinfo=dt.UTC)
            start_ts = int((as_of_dt - dt.timedelta(days=10)).timestamp())
            chart_data = self.get_chart(
                "coingecko:bitcoin,coingecko:ethereum", start=start_ts, span=15, period="1d"
            )

            coins_data = dict((chart_data or {}).get("coins", {}))
            if "coingecko:bitcoin" not in coins_data:
                btc_only = self.get_chart("coingecko:bitcoin", start=start_ts, span=15, period="1d")
                if btc_only and "coins" in btc_only:
                    coins_data.update(btc_only["coins"])
            if "coingecko:ethereum" not in coins_data:
                eth_only = self.get_chart("coingecko:ethereum", start=start_ts, span=15, period="1d")
                if eth_only and "coins" in eth_only:
                    coins_data.update(eth_only["coins"])

            if "coingecko:bitcoin" in coins_data and btc_price is None:
                prices_list = coins_data["coingecko:bitcoin"].get("prices", [])
                valid_p = []
                for p in prices_list:
                    d = _to_date(p["timestamp"])
                    if d <= as_of:
                        valid_p.append((d, float(p["price"])))
                valid_p.sort(key=lambda x: x[0])
                if valid_p:
                    btc_price_date, btc_price = valid_p[-1]

            if "coingecko:ethereum" in coins_data and eth_price is None:
                prices_list = coins_data["coingecko:ethereum"].get("prices", [])
                valid_p = []
                for p in prices_list:
                    d = _to_date(p["timestamp"])
                    if d <= as_of:
                        valid_p.append((d, float(p["price"])))
                valid_p.sort(key=lambda x: x[0])
                if valid_p:
                    eth_price_date, eth_price = valid_p[-1]

        if (
            eth_tvl is None
            and stablecoin_supply is None
            and btc_price is None
            and eth_price is None
        ):
            return None

        urls = {
            "tvl": HISTORICAL_TVL_URL.format(chain="Ethereum"),
            "stablecoins": STABLECOIN_CHARTS_URL.format(chart_type="all"),
            "btc_chart": CHART_URL.format(coins="coingecko:bitcoin"),
            "eth_chart": CHART_URL.format(coins="coingecko:ethereum"),
            "prices_current": PRICES_CURRENT_URL.format(coins="coingecko:bitcoin,coingecko:ethereum"),
        }

        return DefiLlamaContext(
            as_of=as_of,
            eth_tvl=eth_tvl,
            eth_tvl_date=eth_tvl_date,
            eth_tvl_change_30d=eth_tvl_change_30d,
            eth_tvl_change_365d=eth_tvl_change_365d,
            stablecoin_supply=stablecoin_supply,
            stablecoin_date=stablecoin_date,
            stablecoin_change_30d=stablecoin_change_30d,
            btc_price=btc_price,
            btc_price_date=btc_price_date,
            eth_price=eth_price,
            eth_price_date=eth_price_date,
            source="DefiLlama",
            urls=urls,
        )


def get_crypto_context(as_of: dt.date | None = None) -> DefiLlamaContext | None:
    """Convenience helper to retrieve crypto context using the default client."""
    client = DefiLlamaClient()
    return client.get_crypto_context(as_of)
