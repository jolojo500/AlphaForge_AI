"""Current holdings parsing, proxy mapping, and trade calculation (Issue #120).

Track A owned.
"""

from __future__ import annotations

import re
from typing import Any

# Default cash proxy in the 31-asset universe (ultra-short term Canadian bond ETF)
CASH_PROXY = "ZST.TO"

# Common proxies mapping tickers outside the 31-asset universe to assets within it
COMMON_PROXIES: dict[str, str] = {
    # Cash / Money Market / HISA
    "CASH": CASH_PROXY,
    "CAD": CASH_PROXY,
    "USD": CASH_PROXY,
    "CASH.TO": CASH_PROXY,
    "PSA.TO": CASH_PROXY,
    "CSAV.TO": CASH_PROXY,
    "CMR.TO": CASH_PROXY,
    "CBIL.TO": CASH_PROXY,
    "HISA.TO": CASH_PROXY,
    "SHY": CASH_PROXY,
    "BIL": CASH_PROXY,
    # Canadian broad equities
    "VCN.TO": "XIU.TO",
    "XIC.TO": "XIU.TO",
    "VCE.TO": "XIU.TO",
    "HXT.TO": "XIU.TO",
    "ZCN.TO": "XIU.TO",
    "XMD.TO": "XIU.TO",
    # Canadian financials
    "BNS.TO": "RY.TO",
    "BMO.TO": "RY.TO",
    "CM.TO": "RY.TO",
    "NA.TO": "RY.TO",
    "LB.TO": "RY.TO",
    "SLF.TO": "MFC.TO",
    "GWO.TO": "MFC.TO",
    "IAG.TO": "MFC.TO",
    # Canadian energy
    "SU.TO": "CNQ.TO",
    "CVE.TO": "CNQ.TO",
    "TOU.TO": "CNQ.TO",
    "ARX.TO": "CNQ.TO",
    "TRP.TO": "ENB.TO",
    "PPL.TO": "ENB.TO",
    "KEY.TO": "ENB.TO",
    # Canadian industrials & rails
    "CP.TO": "CNR.TO",
    "WCN.TO": "CNR.TO",
    "TIH.TO": "CNR.TO",
    # Canadian utilities & telecom
    "BCE.TO": "FTS.TO",
    "T.TO": "FTS.TO",
    "RCI.B.TO": "FTS.TO",
    "QBR.B.TO": "FTS.TO",
    "EMA.TO": "FTS.TO",
    "AQN.TO": "FTS.TO",
    "H.TO": "FTS.TO",
    # Canadian consumer & retail
    "L.TO": "ATD.TO",
    "WN.TO": "ATD.TO",
    "MRU.TO": "ATD.TO",
    "DOL.TO": "ATD.TO",
    # Canadian tech
    "OTEX.TO": "SHOP.TO",
    "GIB.A.TO": "CSU.TO",
    "LSPD.TO": "SHOP.TO",
    "BB.TO": "SHOP.TO",
    "CTS.TO": "SHOP.TO",
    # Canadian bonds
    "ZAG.TO": "XBB.TO",
    "VAB.TO": "XBB.TO",
    "XQB.TO": "XBB.TO",
    "XSB.TO": CASH_PROXY,
    "VSB.TO": CASH_PROXY,
    # US broad equities
    "VOO": "SPY",
    "IVV": "SPY",
    "VTI": "SPY",
    "SCHX": "SPY",
    "ITOT": "SPY",
    "DIA": "SPY",
    "VFINX": "SPY",
    "XSP.TO": "SPY",
    "VFV.TO": "SPY",
    "ZSP.TO": "SPY",
    # US tech / growth
    "XLK": "QQQ",
    "VGT": "QQQ",
    "SMH": "QQQ",
    "SOXX": "QQQ",
    "ARKK": "QQQ",
    "HXQ.TO": "QQQ",
    "ZQQ.TO": "QQQ",
    "XQQ.TO": "QQQ",
    "META": "GOOGL",
    "NFLX": "GOOGL",
    "AVGO": "MSFT",
    "ADBE": "MSFT",
    "CRM": "MSFT",
    "AMD": "NVDA",
    "INTC": "NVDA",
    # US ESG
    "SUSL": "ESGV",
    "ESGU": "ESGV",
    "ICLN": "ESGV",
    # US financials
    "BRK.A": "JPM",
    "BRK.B": "JPM",
    "V": "JPM",
    "MA": "JPM",
    "BAC": "JPM",
    "WFC": "JPM",
    "GS": "JPM",
    "MS": "JPM",
    # US healthcare
    "UNH": "JNJ",
    "ABBV": "JNJ",
    "MRK": "JNJ",
    "PFE": "JNJ",
    "LLY": "JNJ",
    # US consumer
    "WMT": "PG",
    "COST": "PG",
    "PEP": "PG",
    "KO": "PG",
    "MCD": "PG",
    "NKE": "PG",
    "HD": "AMZN",
    # US energy
    "CVX": "XOM",
    "COP": "XOM",
    "SLB": "XOM",
    # US bonds
    "BND": "AGG",
    "IEF": "AGG",
    "GOVT": "AGG",
    "VCIT": "AGG",
    "LQD": "AGG",
    "EDV": "TLT",
    "VGLT": "TLT",
    "ZROZ": "TLT",
    # Commodities
    "IAU": "GLD",
    "PHYS": "GLD",
    "SLV": "GLD",
    "CGL.TO": "GLD",
    # Crypto
    "SOL-USD": "ETH-USD",
    "ADA-USD": "ETH-USD",
    "XRP-USD": "BTC-USD",
    "IBIT": "BTC-USD",
    "FBTC": "BTC-USD",
    "BTCC.TO": "BTC-USD",
    "BTCC.B.TO": "BTC-USD",
    "ETHH.TO": "ETH-USD",
}


def _parse_num(raw_val: str) -> float | None:
    s = raw_val.strip().replace("$", "").replace(" ", "").rstrip("%")
    if not s:
        return None
    # Check if comma is used as thousands separator: e.g. 50,000 or 1,000,000
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", s):
        s = s.replace(",", "")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", s):
        # European format e.g. 50.000,50
        s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s:
        # e.g. 25,5% or 50,000
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) == 3 and parts[0].isdigit() and int(parts[0]) > 0:
            s = parts[0] + parts[1]
        else:
            s = s.replace(",", ".")
    try:
        val = float(s)
        return val if val > 0 else None
    except ValueError:
        return None


def parse_holdings(raw: Any) -> dict[str, float]:
    """Parse holdings from a dict, list, or CSV/text string.

    Accepts:
    - Dict: {"XIU.TO": 0.5, "ZST.TO": 0.5} or {"XIU.TO": 50000, ...}
    - CSV/TSV/multiline string:
      XIU.TO, 50000
      ZST.TO, 50%
      or with headers (ticker, weight/amount).
    """
    if not raw:
        return {}

    if isinstance(raw, dict):
        out: dict[str, float] = {}
        for k, v in raw.items():
            if not k:
                continue
            ticker = str(k).strip().upper()
            try:
                val = float(v)
                if val > 0:
                    out[ticker] = val
            except (ValueError, TypeError):
                continue
        return out

    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}

        out = {}
        # Try delimiter sniff or line-by-line regex
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines:
            # Skip comments or markdown headers
            if line.startswith("#") or line.startswith("//"):
                continue

            # Determine delimiter: priority semicolon, tab, comma, multiple spaces
            if ";" in line:
                parts = line.split(";", 1)
            elif "\t" in line:
                parts = line.split("\t", 1)
            elif "," in line:
                parts = line.split(",", 1)
            elif re.search(r"\s{2,}", line):
                parts = re.split(r"\s{2,}", line, maxsplit=1)
            else:
                parts = line.split(maxsplit=1)

            if len(parts) < 2:
                continue

            raw_ticker = parts[0].strip().upper().replace("$", "")
            # Skip header lines like "TICKER", "SYMBOL", "ACTIF"
            if raw_ticker in ("TICKER", "SYMBOL", "ACTIF", "TITRE", "NOM", "ASSET"):
                continue

            val = _parse_num(parts[1])
            if val is not None:
                out[raw_ticker] = val

        return out

    return {}


def resolve_holdings(
    holdings: dict[str, float],
    universe_tickers: set[str],
) -> tuple[dict[str, float], dict[str, str], list[str], float]:
    """Map raw holdings to the 31-asset universe via direct match or proxy.

    Returns:
    - mapped_weights: {universe_ticker: normalized_weight} summing to 1.0 (if any valid)
    - proxies_used: {original_ticker: proxy_ticker}
    - not_analysed: list of original tickers that could not be mapped
    - not_analysed_share: ratio of portfolio value not analysed (0.0 to 1.0)
    """
    if not holdings:
        return {}, {}, [], 0.0

    total_raw = sum(holdings.values())
    if total_raw <= 0:
        return {}, {}, [], 0.0

    universe_upper = {t.upper(): t for t in universe_tickers}
    mapped_amounts: dict[str, float] = {}
    proxies_used: dict[str, str] = {}
    not_analysed: list[str] = []
    unanalysed_val = 0.0

    for ticker, val in holdings.items():
        t_clean = ticker.strip().upper()
        # Direct match in universe
        if t_clean in universe_upper:
            target = universe_upper[t_clean]
            mapped_amounts[target] = mapped_amounts.get(target, 0.0) + val
        # Check proxy
        elif t_clean in COMMON_PROXIES:
            target = COMMON_PROXIES[t_clean]
            proxies_used[ticker] = target
            mapped_amounts[target] = mapped_amounts.get(target, 0.0) + val
        else:
            not_analysed.append(ticker)
            unanalysed_val += val

    not_analysed_share = round(unanalysed_val / total_raw, 4)

    # Normalize mapped weights to sum to 1.0
    mapped_sum = sum(mapped_amounts.values())
    if mapped_sum > 0:
        mapped_weights = {t: round(amt / mapped_sum, 6) for t, amt in mapped_amounts.items()}
        # Normalize rounding error
        s = sum(mapped_weights.values())
        if mapped_weights and s > 0:
            first = next(iter(mapped_weights))
            mapped_weights[first] += round(1.0 - s, 6)
    else:
        mapped_weights = {}

    return mapped_weights, proxies_used, not_analysed, not_analysed_share


def build_as_requested_from_current(
    current_weights: dict[str, float],
    idea_ticker: str,
    idea_weight: float,
    cash_ticker: str = CASH_PROXY,
) -> dict[str, float]:
    """Build the as_requested scenario: client's current portfolio + requested idea.

    The idea is funded from cash (e.g. ZST.TO) if present; if cash is insufficient or zero,
    the remaining amount is funded pro rata from the other non-idea holdings.
    """
    idea_weight = min(max(float(idea_weight), 0.0), 1.0)
    if idea_weight == 0.0:
        return dict(current_weights)

    out = {t: float(w) for t, w in current_weights.items() if w > 1e-6}
    existing_idea = out.get(idea_ticker, 0.0)
    additional_needed = idea_weight - existing_idea

    if additional_needed <= 1e-6:
        # Already holds equal or more than requested
        return out

    # Check cash availability
    cash_available = out.get(cash_ticker, 0.0)
    if cash_available > 1e-6:
        cash_used = min(cash_available, additional_needed)
        new_cash = cash_available - cash_used
        if new_cash > 1e-6:
            out[cash_ticker] = new_cash
        else:
            out.pop(cash_ticker, None)
        additional_needed -= cash_used

    # Fund remainder pro rata from non-idea holdings
    if additional_needed > 1e-6:
        non_idea_tickers = [t for t in out if t != idea_ticker]
        non_idea_sum = sum(out[t] for t in non_idea_tickers)
        if non_idea_sum > 1e-6:
            scale = max(0.0, non_idea_sum - additional_needed) / non_idea_sum
            for t in non_idea_tickers:
                new_w = out[t] * scale
                if new_w > 1e-6:
                    out[t] = new_w
                else:
                    out.pop(t, None)

    out[idea_ticker] = idea_weight

    # Final normalization to ensure sum == 1.0
    tot = sum(out.values())
    if tot > 0:
        out = {t: round(w / tot, 6) for t, w in out.items()}
        diff = 1.0 - sum(out.values())
        if abs(diff) > 1e-8:
            out[idea_ticker] = round(out[idea_ticker] + diff, 6)

    return out


def calculate_trades_and_turnover(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    budget_cad: float | None = None,
) -> tuple[list[dict[str, Any]], float]:
    """Calculate trades to transition from current_weights to target_weights, and turnover %.

    Turnover % is 0.5 * sum(|w_target - w_curr|) which equals sum(buys) == sum(sells).
    """
    all_tickers = sorted(set(current_weights.keys()) | set(target_weights.keys()))
    trades: list[dict[str, Any]] = []
    total_abs_diff = 0.0

    for t in all_tickers:
        w_curr = current_weights.get(t, 0.0)
        w_tgt = target_weights.get(t, 0.0)
        diff = round(w_tgt - w_curr, 4)
        total_abs_diff += abs(diff)

        if abs(diff) >= 0.0001:
            trade: dict[str, Any] = {
                "ticker": t,
                "current_weight": round(w_curr, 4),
                "target_weight": round(w_tgt, 4),
                "change": diff,
                "action": "Achat" if diff > 0 else "Vente",
                "action_en": "BUY" if diff > 0 else "SELL",
            }
            if budget_cad and budget_cad > 0:
                trade["amount_cad"] = round(diff * budget_cad, 2)
            trades.append(trade)

    trades.sort(key=lambda x: abs(x["change"]), reverse=True)
    turnover = round(total_abs_diff / 2.0, 4)
    return trades, turnover
