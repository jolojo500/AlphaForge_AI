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


_HEADER_WORDS = ("TICKER", "SYMBOL", "ACTIF", "TITRE", "NOM", "ASSET")
# Spoken names and short symbols mapped to the universe ticker when one exists.
TICKER_ALIASES: dict[str, str] = {
    "BTC": "BTC-USD",
    "BITCOIN": "BTC-USD",
    "XBT": "BTC-USD",
    "ETH": "ETH-USD",
    "ETHER": "ETH-USD",
    "ETHEREUM": "ETH-USD",
}
_SUM_TOLERANCE = 1e-6


class HoldingsError(ValueError):
    """Declared holdings that cannot be read as a portfolio (e.g. more than 100 %)."""


class DeclaredHoldings(dict):
    """Analysed holdings at declared weights; keeps the unanalysed part and the cash.

    A plain dict for every caller of `parse_holdings`; `parse_holdings_detailed` reads the
    extra attributes back so the unanalysed lines are not lost when a caller parses twice.
    """

    unanalysed: dict[str, float]
    cash: float
    total_amount: float | None

    def __init__(self, analysed=(), unanalysed=None, cash=0.0, total_amount=None):
        super().__init__(analysed)
        self.unanalysed = dict(unanalysed or {})
        self.cash = cash
        self.total_amount = total_amount


def _universe_tickers() -> list[str]:
    import csv

    from alphaforge import config

    with open(config.STARTER_DIR / "assets_universe.csv", newline="") as f:
        return [r["ticker"] for r in csv.DictReader(f)]


def normalise_ticker(raw: str, universe: list[str] | set[str] | None = None) -> tuple[str, bool]:
    """(ticker, analysed). Maps "BTC" or "RY" style input to the universe ticker when one
    exists; a ticker with a documented proxy stays analysed under its own symbol; anything
    else is returned upper-cased and flagged as not analysed. Never guesses."""
    tickers = list(universe) if universe is not None else _universe_tickers()
    key = str(raw).strip().upper().replace("$", "")
    by_upper = {t.upper(): t for t in tickers}
    if key in by_upper:
        return by_upper[key], True
    if key in TICKER_ALIASES and TICKER_ALIASES[key] in tickers:
        return TICKER_ALIASES[key], True
    for t in tickers:  # "RY" -> "RY.TO", "BTC" -> "BTC-USD"
        if key and key in (t.upper().split(".")[0], t.upper().split("-")[0]):
            return t, True
    if key in COMMON_PROXIES:
        return key, True
    return key, False


def _raw_pairs(raw: Any) -> list[tuple[str, float]]:
    """(ticker as typed, positive number) pairs from a dict, a list or a CSV/text string."""
    pairs: list[tuple[str, float]] = []
    if not raw:
        return pairs
    if isinstance(raw, dict):
        for k, v in raw.items():
            if not k:
                continue
            try:
                val = float(str(v).replace("%", "").replace(",", ".")) if isinstance(v, str) else float(v)
            except (ValueError, TypeError):
                continue
            if val > 0:
                pairs.append((str(k).strip().upper(), val))
        return pairs
    if isinstance(raw, (list, tuple)):
        for row in raw:
            if isinstance(row, dict):
                k = row.get("ticker") or row.get("symbol") or row.get("actif")
                v = row.get("weight", row.get("poids", row.get("amount", row.get("value"))))
                if k is not None and v is not None:
                    pairs += _raw_pairs({k: v})
            elif isinstance(row, (list, tuple)) and len(row) >= 2:
                pairs += _raw_pairs({row[0]: row[1]})
        return pairs
    if isinstance(raw, str):
        for line in (ln.strip() for ln in raw.strip().splitlines()):
            if not line or line.startswith("#") or line.startswith("//"):
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
            if raw_ticker in _HEADER_WORDS:
                continue
            val = _parse_num(parts[1])
            if val is not None:
                pairs.append((raw_ticker, val))
    return pairs


def _fr_pct(x: float) -> str:
    return f"{x * 100:.1f}".replace(".", ",") + " %"


def parse_holdings_detailed(raw: Any) -> dict[str, Any]:
    """Declared holdings as fractions of the WHOLE portfolio, never rescaled.

    Returns {"analysed": {ticker: w}, "unanalysed": {ticker: w}, "cash": float}.

    Units: values all at or below 1 are fractions (0.3); values adding up to at most 100
    are percentages (30); any value above 100 means dollar amounts, converted to shares of
    their total. A declared total below 100 % leaves the remainder as cash; above 100 %
    raises `HoldingsError` (a ValueError) with a French message.
    """
    if isinstance(raw, DeclaredHoldings):
        return {"analysed": dict(raw), "unanalysed": dict(raw.unanalysed), "cash": raw.cash}
    pairs = _raw_pairs(raw)
    if not pairs:
        return {"analysed": {}, "unanalysed": {}, "cash": 0.0}

    values = [v for _, v in pairs]
    total = sum(values)
    if max(values) > 100.0:  # dollar amounts
        scale = 1.0 / total
    elif max(values) <= 1.0:  # fractions
        if total > 1.0 + _SUM_TOLERANCE:
            raise HoldingsError(
                f"Les avoirs déclarés totalisent {_fr_pct(total)}, soit plus de 100 % du "
                "portefeuille : corrigez les pondérations avant de lancer l'analyse."
            )
        scale = 1.0
    else:  # percentages
        if total > 100.0 + 1e-4:
            raise HoldingsError(
                f"Les avoirs déclarés totalisent {_fr_pct(total / 100)}, soit plus de 100 % du "
                "portefeuille : corrigez les pondérations avant de lancer l'analyse."
            )
        scale = 0.01

    universe = _universe_tickers()
    analysed: dict[str, float] = {}
    unanalysed: dict[str, float] = {}
    for typed, val in pairs:
        ticker, known = normalise_ticker(typed, universe)
        bucket = analysed if known else unanalysed
        bucket[ticker] = round(bucket.get(ticker, 0.0) + val * scale, 6)
    declared = sum(analysed.values()) + sum(unanalysed.values())
    cash = round(max(0.0, 1.0 - declared), 6)
    if cash < 1e-5:
        cash = 0.0
    return {"analysed": analysed, "unanalysed": unanalysed, "cash": cash}


def declared_total_amount(raw: Any) -> float | None:
    """Total dollar value when the holdings were typed as amounts, else None."""
    if isinstance(raw, DeclaredHoldings):
        return raw.total_amount
    values = [v for _, v in _raw_pairs(raw)]
    return float(sum(values)) if values and max(values) > 100.0 else None


def parse_holdings(raw: Any) -> dict[str, float]:
    """Analysed holdings at their DECLARED weights (fractions of the whole portfolio).

    Accepts a dict ({"XIU.TO": 0.5}, {"XIU.TO": 50}, {"XIU.TO": 50000}), a list of rows, or
    CSV/TSV/multiline text ("XIU.TO, 50%"). Never rescaled: holdings outside the universe
    and undeclared cash keep their share (see `parse_holdings_detailed`), so the weights
    returned here may add up to less than 1. The returned dict carries `.unanalysed`,
    `.cash` and `.total_amount` for callers that need them.
    """
    if isinstance(raw, DeclaredHoldings):
        return raw
    d = parse_holdings_detailed(raw)
    return DeclaredHoldings(d["analysed"], d["unanalysed"], d["cash"], declared_total_amount(raw))


def resolve_holdings(
    holdings: dict[str, float],
    universe_tickers: set[str],
) -> tuple[dict[str, float], dict[str, str], list[str], float]:
    """Map holdings to the 31-asset universe via direct match or proxy, WITHOUT rescaling.

    Weights are shares of the whole declared portfolio: fractions summing to at most 1 are
    kept as they are; larger numbers (percentages or dollar amounts) are divided by their
    total. The analysed part is never stretched to 100 % (final report, finding 2).

    Returns:
    - mapped_weights: {universe_ticker: share of the whole portfolio}; adds up to less than
      1 when part of the portfolio is not analysed or is cash
    - proxies_used: {original_ticker: proxy_ticker}
    - not_analysed: list of original tickers that could not be mapped
    - not_analysed_share: share of the portfolio value not analysed (0.0 to 1.0)
    """
    if not holdings:
        return {}, {}, [], 0.0

    total_raw = sum(holdings.values())
    if total_raw <= 0:
        return {}, {}, [], 0.0
    # Same unit rule as parse_holdings_detailed: fractions, then percentages, then amounts.
    biggest = max(holdings.values())
    if biggest <= 1.0 and total_raw <= 1.0 + _SUM_TOLERANCE:
        scale = 1.0
    elif biggest <= 100.0 and total_raw <= 100.0 + 1e-4:
        scale = 0.01
    else:
        scale = 1.0 / total_raw

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
        elif t_clean in COMMON_PROXIES and COMMON_PROXIES[t_clean] in universe_tickers:
            target = COMMON_PROXIES[t_clean]
            proxies_used[ticker] = target
            mapped_amounts[target] = mapped_amounts.get(target, 0.0) + val
        else:
            not_analysed.append(ticker)
            unanalysed_val += val

    unanalysed = getattr(holdings, "unanalysed", None) or {}
    for t in unanalysed:
        if t not in not_analysed:
            not_analysed.append(t)
    not_analysed_share = round(unanalysed_val * scale + sum(unanalysed.values()), 4)
    mapped_weights = {t: round(amt * scale, 6) for t, amt in mapped_amounts.items()}
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
    if budget_cad is None:
        total = getattr(current_weights, "total_amount", None)
        if total is not None and total > 0:
            budget_cad = float(total)
        elif current_weights and max(current_weights.values()) > 100.0:
            budget_cad = float(sum(current_weights.values()))

    if current_weights and max(current_weights.values()) > 100.0:
        tot = sum(current_weights.values())
        current_weights = {t: val / tot for t, val in current_weights.items()}

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
