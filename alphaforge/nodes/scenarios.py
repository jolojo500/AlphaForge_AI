"""Scenario builder (PRD 5.7). Track A: three comparable portfolios from the same evidence.

as_requested      judge: the idea at its stated weight, the rest is the baseline scaled down.
                  build: the stated preferences taken literally (equal weight, no risk control).
capped            judge: the idea fixed at the profile's cap, the rest risk-minimised around it.
                  build: the portfolio closest to the stated preferences that respects the caps.
profile_baseline  long-only minimum variance under the profile's caps. No expected returns.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from alphaforge.costs import (
    CAPITAL_PRESERVATION_FOREIGN_BOND_CAP,
    all_in_cost,
    calculate_fee_drag,
    capital_preservation_foreign_bond_evidence,
    etf_mer_evidence,
    fx_conversion_cost,
    fx_conversion_evidence,
)
from alphaforge.data.index_history import (
    SOURCE_URL as INDEX_SOURCE_URL,
)
from alphaforge.data.index_history import (
    load_index_history,
    proxy_drawdown,
    proxy_label,
    proxy_shares,
    proxy_stress,
)
from alphaforge.data.provider import get_provider
from alphaforge.evidence import EvidenceRegistry
from alphaforge.nodes.quant import (
    GICS_SECTORS,
    OTHER_SECTOR,
    concentration,
    max_drawdown,
    stress_2022,
    stress_2022_note,
    usd_exposure,
    volatility,
)
from alphaforge.nodes.screening import HOLDINGS_DIR, load_esgv
from alphaforge.personas import PERSONAS
from alphaforge.state import (
    SCENARIO_METRICS,
    SCENARIO_NAMES,
    GraphState,
    Profile,
    Scenario,
    effective_risk,
)
from alphaforge.tax import asset_location_note, scenario_tax_drag, tax_rules_evidence
from alphaforge.tracing import traced

try:  # Track B supplies LLM-drafted notes in B-6; templated notes until then
    from alphaforge.llm import draft_notes
except ImportError:
    draft_notes = None

# Caps per risk tolerance (PRD 5.7), cited as an assumption. equity_min keeps a growth profile
# from collapsing into short bonds, which a pure minimum-variance optimiser would do.
CAPS = {
    "high": {"single_stock": 0.10, "etf": 0.25, "crypto_total": 0.10, "equity_max": 1.00, "equity_min": 0.80},
    "moderate": {"single_stock": 0.07, "etf": 0.25, "crypto_total": 0.00, "equity_max": 0.70, "equity_min": 0.50},
    "low_moderate": {"single_stock": 0.05, "etf": 0.25, "crypto_total": 0.00, "equity_max": 0.40, "equity_min": 0.20},
    "low": {"single_stock": 0.03, "etf": 0.25, "crypto_total": 0.00, "equity_max": 0.25, "equity_min": 0.10},
}
PREFERENCE_SECTORS = {
    "likes_tech": {"Information Technology", "Communication Services", "Broad market (U.S. growth/tech-heavy)"},
    "likes_crypto": {"Crypto asset"},
}
EQUITY_CLASSES = {"equity", "etf_equity"}
# Asset-class codes a question may name in `Profile.requested_allocation`.
REQUEST_CLASSES = {
    "crypto": {"crypto"},
    "equity": EQUITY_CLASSES,
    "bond": {"etf_bond"},
    "gold": {"etf_commodity"},
}
MIN_LINE = 0.02  # no line under 2 % in `capped` and `profile_baseline`
MAX_LINES = 12  # at most 12 lines in `capped` and `profile_baseline`
# High-risk growth profiles (caps table: 80-100 % equities): the baseline targets the middle
# of the band and holds no ultra-short bond sleeve, which is a cash substitute.
GROWTH_HIGH_EQUITY_MIN = 0.90
ULTRA_SHORT_BOND = "ZST.TO"
REQUEST_TOL = 1e-4
GAP_LABEL_FR = "Écart de pondération (illustratif)"
GAP_LABEL_EN = "Weight difference (illustrative)"
DEFAULT_IDEA_WEIGHT = 0.20  # when a judge request names a ticker but no weight
OVERLAP_ETF_SHARE = 0.5  # an ETF cited for overlap keeps half of the ETF cap
CONCENTRATION_SHARE = 0.8  # a line cited for concentration keeps 80 % of its cap
_OVERLAP_RE = re.compile(r"chevauch|overlap|double emploi|détient déjà|deja|déjà")
_DROP_RE = re.compile(r"exclu|controvers|esg|contradi|interdit")
_CONC_RE = re.compile(r"concentr|taux|obligat|secteur|duration|devise|currency|rate|sensib")
ESG_TILT_NON_MEMBER_REDUCTION = 0.50  # fixed factor reducing non-member equity weight by 50%
SOURCE = "prices_daily.csv + fx_usdcad_daily.csv"
METHODS = {
    "volatility_ann": "annualised std of daily log returns of the scenario rebalanced daily, CAD",
    "max_drawdown": "largest peak-to-trough fall of the scenario value, CAD",
    "stress_2022": "total return of the scenario in CAD over 2022-01-03..2022-12-30",
    "top_weight": "largest single weight in the scenario",
    "sector_concentration_hhi": "Herfindahl index of the sector weights after looking through ETF holdings "
    "(SPY, QQQ, ESGV, XIU.TO replaced by their cached holdings; a holding outside the universe has no "
    f"documented sector ('{OTHER_SECTOR}') and that share is assumed spread evenly across the "
    f"{GICS_SECTORS} GICS sectors: HHI = sum(known share^2) + other^2 / {GICS_SECTORS}); decimal, "
    "effective sectors = 1 / HHI",
    "us_exposure": "look-through weight in US-listed names, ETF holdings included (crypto not counted)",
    "tax_drag": "estimated annual tax drag based on historical dividend/interest yields and account tax rules",
    "fee_drag": "weighted average management expense ratio (MER) across holdings",
    "esg_proxy_share": "part du portefeuille dans des titres présents dans le fonds ESGV (indicateur indirect)",
    "currency_usd_exposure": "share of the weights in assets priced in USD (BTC-USD and ETH-USD count as USD)",
    "effective_sectors": "1 / Herfindahl index of the sector weights after looking through ETF holdings "
    "(≈ N secteurs effectifs)",
    "all_in_cost": "annual ratio: fee drag + estimated annual tax drag + the one-time FX conversion cost on "
    "the USD-priced share amortised over the profile horizon (min 1 year)",
    "canada_exposure": "look-through weight in TSX-listed names, ETF holdings included",
    "top_name_exposure": "largest look-through exposure to a single name: held directly plus via ETF holdings",
    "max_drawdown_long_proxy": "largest peak-to-trough fall of a monthly-rebalanced proxy portfolio built "
    "from long index histories mapped from the scenario's US-equity / Canadian-equity / bond shares",
    "stress_2000_02_proxy": "total return of the index-proxy portfolio over the dot-com bear market, "
    "month-ends 2000-03-31..2002-09-30",
    "stress_2008_proxy": "total return of the index-proxy portfolio over the 2008 financial crisis, "
    "month-ends 2007-10-31..2009-02-28",
}
EXTRA_METRICS: tuple[str, ...] = (
    "currency_usd_exposure", "effective_sectors", "all_in_cost", "canada_exposure", "top_name_exposure",
)
EXTRA_UNITS = {
    "currency_usd_exposure": "ratio", "effective_sectors": "count", "all_in_cost": "ratio",
    "canada_exposure": "ratio", "top_name_exposure": "ratio",
}
PROXY_METRICS: tuple[str, ...] = ("max_drawdown_long_proxy", "stress_2000_02_proxy", "stress_2008_proxy")
SURVIVORSHIP_NOTE_FR = (
    "Biais du survivant : l'univers ne contient que des actifs encore cotés aujourd'hui et l'historique "
    "de prix commence en 2021-11 ; les rendements historiques glissants et les pertes maximales ci-contre "
    "peuvent paraître meilleurs que ce qu'un investisseur aurait vécu (historique, pas une prévision)."
)


# --- caps ---------------------------------------------------------------------------------


def caps_for(profile: Profile, rounds: int = 0) -> dict[str, float]:
    """Profile caps for the lower of tolerance and capacity. `rounds` is kept for callers;
    objections no longer tighten every cap (#116), see `targeted_changes`."""
    caps = dict(CAPS.get(effective_risk(profile.risk_tolerance, profile.risk_capacity), CAPS["moderate"]))
    if profile.objective == "capital_preservation":
        caps["foreign_fixed_income_unhedged"] = CAPITAL_PRESERVATION_FOREIGN_BOND_CAP
    return caps


def _asset_caps(tickers: list[str], info: pd.DataFrame, caps: dict) -> np.ndarray:
    out = []
    foreign_bond_cap = caps.get("foreign_fixed_income_unhedged")
    for t in tickers:
        cls = info.at[t, "asset_class"]
        curr = info.at[t, "currency"] if "currency" in info.columns else "CAD"
        if cls == "equity":
            cap = caps["single_stock"]
        elif cls == "crypto":
            cap = caps["crypto_total"]
        else:
            cap = caps["etf"]
        if foreign_bond_cap is not None and cls == "etf_bond" and curr != "CAD":
            cap = min(cap, foreign_bond_cap)
        out.append(min(cap, caps.get("per_ticker", {}).get(t, cap)))
    return np.array(out, dtype=float)


def _group_masks(tickers: list[str], info: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    cls = info.loc[tickers, "asset_class"].to_numpy()
    return np.isin(cls, list(EQUITY_CLASSES)), cls == "crypto"


# --- optimiser ----------------------------------------------------------------------------


def _fill(raw: np.ndarray, ub: np.ndarray, total: float) -> np.ndarray:
    """Spread `total` proportionally to `raw`, never above `ub` (water-filling)."""
    if total <= 0 or len(raw) == 0:
        return np.zeros(len(raw))
    raw = np.where(np.isfinite(raw) & (raw > 0), raw, 1e-12)
    w = np.minimum(raw / raw.sum() * total, ub)
    for _ in range(100):
        deficit = total - w.sum()
        free = w < ub - 1e-12
        if deficit <= 1e-12 or not free.any():
            break
        share = np.where(free, raw, 0.0)
        w = np.minimum(w + deficit * share / share.sum(), ub)
    return w


def _feasible(w, lb, ub, eq, cr, caps, equity_floor, tol=1e-6) -> bool:
    ok = abs(w.sum() - 1) < tol and (w >= lb - tol).all() and (w <= ub + tol).all()
    if cr.any():
        ok = ok and w[cr].sum() <= caps["crypto_total"] + tol
    if eq.any():
        ok = ok and w[eq].sum() <= caps["equity_max"] + tol
        if equity_floor:
            ok = ok and w[eq].sum() >= caps["equity_min"] - tol
    return bool(ok)


def _clean(w: pd.Series) -> pd.Series:
    """Drop dust, renormalise, sorted by ticker."""
    w = w[w > 1e-6]
    return (w / w.sum()).sort_index()


def optimize(
    cov: pd.DataFrame,
    info: pd.DataFrame,
    caps: dict,
    *,
    target: pd.Series | None = None,
    fixed: dict[str, float] | None = None,
    equity_floor: bool = True,
    min_line: float = 0.0,
) -> pd.Series:
    """Long-only weights under the caps (scipy SLSQP). No expected returns anywhere.

    min_line: lower bound of every line that is not pinned (used by `limit_lines`).

    target None: minimum variance. target given: closest portfolio to `target` (least squares).
    fixed: tickers pinned to a weight. If the solver fails, falls back to inverse-volatility
    (risk parity) weights water-filled under the per-asset caps.
    """
    tickers = list(cov.index)
    n = len(tickers)
    fixed = fixed or {}
    ub = _asset_caps(tickers, info, caps)
    lb = np.minimum(np.full(n, float(min_line)), ub)
    pinned = np.array([t in fixed for t in tickers])
    lb[pinned] = ub[pinned] = [fixed[t] for t in tickers if t in fixed]
    eq, cr = _group_masks(tickers, info)
    sigma = np.nan_to_num(cov.to_numpy()) * 1e4  # scaled for the solver
    tgt = None if target is None else target.reindex(tickers).fillna(0.0).to_numpy()

    def fun(w):
        if tgt is None:
            return float(w @ sigma @ w)
        return float(((w - tgt) ** 2).sum())

    def jac(w):
        if tgt is None:
            return 2 * sigma @ w
        return 2 * (w - tgt)

    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    if cr.any():
        cons.append({"type": "ineq", "fun": lambda w: caps["crypto_total"] - w[cr].sum()})
    if eq.any():
        cons.append({"type": "ineq", "fun": lambda w: caps["equity_max"] - w[eq].sum()})
        if equity_floor:
            cons.append({"type": "ineq", "fun": lambda w: w[eq].sum() - caps["equity_min"]})

    x0 = np.clip(np.full(n, 1.0 / n), lb, ub)
    res = minimize(
        fun, x0, jac=jac, method="SLSQP", bounds=list(zip(lb, ub, strict=True)),
        constraints=cons, options={"maxiter": 500, "ftol": 1e-12},
    )
    w = np.clip(res.x, lb, ub) if res.success else None
    if w is None or not _feasible(w, lb, ub, eq, cr, caps, equity_floor):
        vol = np.sqrt(np.clip(np.nan_to_num(np.diag(cov.to_numpy()), nan=1.0), 1e-12, None))
        w = np.where(pinned, lb, 0.0)
        w[~pinned] = _fill(1.0 / vol[~pinned], ub[~pinned], 1.0 - w.sum())
    return _clean(pd.Series(w, index=tickers))


def _valid(w: pd.Series, info, caps, fixed, equity_floor: bool, min_line: float) -> bool:
    """Caps, floors, sum to 1 and the minimum line size all hold for `w`."""
    tickers = list(w.index)
    ub = _asset_caps(tickers, info, caps)
    lb = np.minimum(np.full(len(tickers), float(min_line)), ub)
    for i, t in enumerate(tickers):
        if t in fixed:
            lb[i] = ub[i] = fixed[t]
    eq, cr = _group_masks(tickers, info)
    return _feasible(w.to_numpy(), lb, ub, eq, cr, caps, equity_floor)


def limit_lines(
    w: pd.Series,
    cov: pd.DataFrame,
    info: pd.DataFrame,
    caps: dict,
    *,
    fixed: dict[str, float] | None = None,
    equity_floor: bool = True,
    min_line: float = MIN_LINE,
    max_lines: int = MAX_LINES,
    min_variance: bool = False,
) -> pd.Series:
    """No dust: at most `max_lines` lines and none under `min_line` (deterministic).

    Keeps the largest lines of `w` (ties broken by ticker), then takes on those lines, under
    the same caps and floors and with `min_line` as a lower bound, the minimum-variance
    portfolio (`min_variance`, for a scenario that was a minimum-variance one) or else the
    closest portfolio to `w`.
    A minimum-variance scenario starts from the lines already at `min_line` or more and adds
    the next largest one until the caps can be met; otherwise `max_lines` lines are kept. A pinned line (`fixed`, the requested idea) keeps its weight even
    when it is under `min_line`. Returns `w` unchanged if no subset satisfies the caps.
    Not applied to `capital_preservation` profiles (see `build_scenarios`): their `capped`
    and `profile_baseline` keep every line of the optimiser, including lines under
    `min_line`, because the optimiser spreads the bond sleeve on purpose (#186 item 8).
    """
    fixed = {t: v for t, v in (fixed or {}).items() if t in w.index and v > 1e-6}
    free = w.drop(labels=list(fixed))
    if len(w) <= max_lines and (free >= min_line - 1e-9).all():
        return w
    ub = dict(zip(free.index, _asset_caps(list(free.index), info, caps), strict=True))
    var = {t: float(cov.at[t, t]) for t in free.index}
    # largest first; equal weights (to 0.01 %) go to the less volatile line, then by ticker
    order = [
        t for t in sorted(free.index, key=lambda t: (-round(float(free[t]), 4), var[t], t))
        if ub[t] >= min_line
    ]
    room = min(max(max_lines - len(fixed), 0), len(order))
    start = max(1, sum(1 for t in order[:room] if free[t] >= min_line - 1e-9))
    # minimum variance: as few lines as the caps allow; closest-to-`w`: as many as allowed
    sizes = range(start, room + 1) if min_variance else [room, *range(start, room)]
    for k in sizes:
        keep = sorted(set(order[:k]) | set(fixed))
        sub = optimize(
            cov.loc[keep, keep], info, caps,
            target=None if min_variance else w.reindex(keep).fillna(0.0),
            fixed=fixed, equity_floor=equity_floor, min_line=min_line,
        )
        if _valid(sub, info, caps, fixed, equity_floor, min_line):
            return sub
    return w


# --- scenarios ----------------------------------------------------------------------------


def calculate_esg_proxy_share(
    weights: pd.Series | dict[str, float],
    holdings_dir: Path | str | dt.date | None = None,
    as_of: dt.date | str | None = None,
) -> float:
    """Share of the portfolio in ESG-proxy assets (ESGV holdings or ESGV ETF)."""
    w = weights.to_dict() if isinstance(weights, pd.Series) else dict(weights)
    esgv = load_esgv(holdings_dir=holdings_dir, as_of=as_of)
    held = {h.get("ticker") for h in (esgv or {}).get("holdings", [])}
    held.add("ESGV")
    return float(sum(float(weight) for ticker, weight in w.items() if ticker in held))


def apply_esg_tilt(
    weights: pd.Series,
    universe: list[str],
    info: pd.DataFrame,
    caps: dict,
    esg_proxy_set: set[str],
    fixed: dict[str, float] | None = None,
    reduction_factor: float = ESG_TILT_NON_MEMBER_REDUCTION,
) -> pd.Series:
    """Deterministic tilt favouring covered ESG-proxy assets inside existing caps.

    Among equity lines, reduces non-member equity weights by `reduction_factor`
    and reallocates the released weight to eligible ESG-proxy equity assets
    (ESGV ETF and ESGV-member stocks) without exceeding any asset cap.
    Non-equity lines (bonds, crypto, gold) and fixed weights are untouched.
    """
    fixed = fixed or {}
    w = weights.copy()
    tickers = list(w.index)

    non_member_eq = [
        t for t in tickers
        if info.at[t, "asset_class"] in EQUITY_CLASSES
        and t not in esg_proxy_set
        and t not in fixed
    ]
    member_eq = [
        t for t in universe
        if info.at[t, "asset_class"] in EQUITY_CLASSES
        and t in esg_proxy_set
        and t not in fixed
    ]

    if not non_member_eq or not member_eq:
        return _clean(w)

    released = 0.0
    for t in non_member_eq:
        reduction = w[t] * reduction_factor
        w[t] -= reduction
        released += reduction

    if released <= 1e-9:
        return _clean(w)

    ub_dict = {t: float(_asset_caps([t], info, caps)[0]) for t in member_eq}
    cur_weights = {t: float(w.get(t, 0.0)) for t in member_eq}
    headroom = {t: max(0.0, ub_dict[t] - cur_weights[t]) for t in member_eq}
    total_headroom = sum(headroom.values())

    if total_headroom <= 1e-9:
        for t in non_member_eq:
            w[t] += released * (w[t] / sum(w[t] for t in non_member_eq))
        return _clean(w)

    alloc = min(released, total_headroom)
    # Prefer ESGV ETF first if eligible, then member stocks sorted by headroom
    for t in sorted(member_eq, key=lambda x: (x != "ESGV", -headroom[x], x)):
        add = min(headroom[t], alloc)
        cur_weights[t] += add
        alloc -= add
        if alloc <= 1e-9:
            break

    for t, new_val in cur_weights.items():
        w[t] = new_val

    leftover = released - min(released, total_headroom)
    if leftover > 1e-9:
        sum_non = sum(w[t] for t in non_member_eq)
        for t in non_member_eq:
            w[t] += leftover * (w[t] / sum_non)

    return _clean(w)


def _preference_portfolio(profile: Profile, universe: list[str], info: pd.DataFrame) -> pd.Series:
    sectors = set().union(*(PREFERENCE_SECTORS.get(p, set()) for p in profile.preferences))
    picks = [t for t in universe if info.at[t, "sector"] in sectors] or list(universe)
    return pd.Series(1.0 / len(picks), index=picks)


def _num(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return v if math.isfinite(v) and v > 0 else 0.0


def _ratio(x) -> float:
    """A weight as a ratio: values above 1 are read as percentages."""
    v = _num(x)
    return v / 100.0 if v > 1.0 else v


def requested_idea_of(profile: Profile) -> dict | None:
    """The single idea named by the question ({"ticker", "weight"}), if any."""
    idea = profile.requested_idea
    return idea if isinstance(idea, dict) and idea.get("ticker") else None


def translate_request(profile: Profile, info: pd.DataFrame) -> dict | None:
    """What the question asks for, as weights on universe tickers. None for a build request.

    Returns {"kind", "weights" (ticker -> weight), "groups" (label, tickers, asked weight),
    "blocked" (tickers the remainder must not use), "problems" (French sentences)}.
    `requested_allocation` wins over `requested_idea`. A class weight ("crypto", "equity",
    "bond", "gold") is split equally across the universe assets of that class, whether or not
    screening kept them: the as_requested scenario always shows what was asked.
    """
    by_upper = {str(t).upper(): t for t in info.index}
    alloc = profile.requested_allocation
    idea = requested_idea_of(profile)
    if alloc and len(alloc) == 1:
        # One ticker at one weight is an idea ("25 % dans TSLA"), not a full allocation: the
        # idea path keeps the rest of the portfolio on the baseline and pins the idea in
        # `capped` at the profile cap. Agent 1 fills both fields for such a question.
        (key, raw), = alloc.items()
        k = str(key).strip()
        same_as_idea = idea is None or str(idea["ticker"]).strip().upper() == k.upper()
        if k.lower() not in REQUEST_CLASSES and same_as_idea:
            idea, alloc = {"ticker": k, "weight": raw}, None
    if alloc:
        explicit: dict[str, float] = {}
        classes: dict[str, float] = {}
        problems: list[str] = []
        for key, raw in alloc.items():
            wt = _ratio(raw)
            k = str(key).strip()
            if k.lower() in REQUEST_CLASSES:
                classes[k.lower()] = classes.get(k.lower(), 0.0) + wt
            elif k.upper() in by_upper:
                t = by_upper[k.upper()]
                explicit[t] = explicit.get(t, 0.0) + wt
            else:
                problems.append(f"« {k} » ({wt:.1%}) n'est pas dans l'univers analysé")
        weights = dict(explicit)
        groups = [(t, [t], wt) for t, wt in sorted(explicit.items())]
        blocked = set(explicit)
        for code, wt in sorted(classes.items()):
            in_class = [
                t
                for t in info.index
                if info.at[t, "asset_class"] in REQUEST_CLASSES[code]
                and not str(info.at[t, "asset_id"] if "asset_id" in info.columns else "").startswith("DYN_")
            ]
            blocked.update(in_class)
            members = sorted(t for t in in_class if t not in explicit)
            if not members:
                problems.append(f"aucun actif de la classe « {code} » à pondérer")
                continue
            for t in members:
                weights[t] = weights.get(t, 0.0) + wt / len(members)
            groups.append((code, members, wt))
        total = sum(weights.values())
        if total > 1.0 + REQUEST_TOL:
            problems.append(f"les poids demandés totalisent {total:.1%}, plus que 100 %")
            weights = {t: w / total for t, w in weights.items()}
        if not weights:
            problems.append("aucun poids de la demande n'a pu être associé à un actif analysé")
        return {"kind": "allocation", "weights": weights, "groups": groups,
                "blocked": blocked, "problems": problems}
    if idea:
        t = by_upper.get(str(idea["ticker"]).strip().upper())
        w_req = min(_ratio(idea.get("weight")) or DEFAULT_IDEA_WEIGHT, 1.0)
        if t is None:
            return {"kind": "idea", "weights": {}, "groups": [], "blocked": set(),
                    "problems": [f"« {idea['ticker']} » n'est pas dans l'univers analysé"]}
        return {"kind": "idea", "weights": {t: w_req}, "groups": [(t, [t], w_req)],
                "blocked": {t}, "problems": []}
    if profile.requested_vehicle:
        return {"kind": "vehicle", "weights": {}, "groups": [], "blocked": set(),
                "problems": [f"« {profile.requested_vehicle} » est hors de l'univers analysé et "
                             "aucun actif analysé ne lui a été associé"]}
    return None


def request_gaps(as_requested: pd.Series | dict, request: dict | None) -> list[str]:
    """Requested assets or weights that are NOT in as_requested (empty list = all present)."""
    if not request:
        return []
    w = dict(as_requested)
    out = list(request["problems"])
    for label, tickers, asked in request["groups"]:
        got = sum(float(w.get(t, 0.0)) for t in tickers)
        if abs(got - asked) > REQUEST_TOL:
            out.append(f"{label} : {asked:.1%} demandé, {got:.1%} dans le scénario")
    return out


def _with_remainder(asked: dict[str, float], filler: pd.Series) -> pd.Series:
    """`asked` at exactly its weights, the remainder spread like `filler`."""
    rest = max(1.0 - sum(asked.values()), 0.0)
    out = pd.Series(asked, dtype=float)
    if rest > 1e-9 and len(filler) and filler.sum() > 0:
        out = pd.concat([out, filler / filler.sum() * rest])
    return out


def growth_calibration(profile: Profile) -> dict | None:
    """Baseline calibration for a high-risk growth profile, read from the caps table."""
    if profile.objective == "growth" and effective_risk(profile.risk_tolerance, profile.risk_capacity) == "high":
        return {"equity_min": GROWTH_HIGH_EQUITY_MIN, "excluded": ULTRA_SHORT_BOND}
    return None


def build_scenarios(
    profile: Profile,
    eligible: list[str],
    prices: pd.DataFrame,
    info: pd.DataFrame,
    *,
    rounds: int = 0,
    drop: tuple[str, ...] | list[str] = (),
    per_ticker: dict[str, float] | None = None,
    current_weights: pd.Series | None = None,
) -> tuple[dict[str, pd.Series], dict[str, float]]:
    """Weights of the scenarios and the caps used. `prices` must cover every ticker.

    `per_ticker` caps come from blocking objections and apply to the lines they cite only;
    the requested idea in `capped` stays at the profile cap (#116). `current_weights`, when
    given, are the analysed holdings at their DECLARED weights (they may sum to less than 1)."""
    profile_caps = caps_for(profile, rounds)
    caps = {**profile_caps, "per_ticker": dict(per_ticker or {})}
    opt_caps = caps
    calib = growth_calibration(profile)
    if calib:
        opt_caps = {
            **caps,
            "equity_min": max(caps["equity_min"], calib["equity_min"]),
            "per_ticker": {**caps["per_ticker"], calib["excluded"]: 0.0},
        }
    universe = [t for t in sorted(eligible) if t not in set(drop)] or sorted(eligible)
    cov = prices.pct_change(fill_method=None).dropna().cov().loc[universe, universe]
    baseline = optimize(cov, info, opt_caps)

    request = translate_request(profile, info)
    asked = {t: w for t, w in (request or {}).get("weights", {}).items() if t in prices.columns}
    fixed_capped: dict[str, float] = {}
    capped_floor = True
    if request and request["kind"] == "allocation" and asked:
        blocked = request["blocked"]
        pref = _preference_portfolio(profile, universe, info)
        filler = pref.drop(labels=[t for t in pref.index if t in blocked])
        if filler.empty:
            filler = baseline.drop(labels=[t for t in baseline.index if t in blocked])
        as_requested = _with_remainder(asked, filler)
        target = as_requested.reindex(universe).fillna(0.0)
        capped = optimize(cov, info, opt_caps, target=target, equity_floor=False)
        capped_floor = False
    elif request and request["kind"] == "idea" and asked:
        ticker, w_req = next(iter(asked.items()))
        as_requested = None
        if current_weights is not None and current_weights.sum() >= 1.0 - 1e-3:
            from alphaforge.holdings import build_as_requested_from_current

            cand = pd.Series(build_as_requested_from_current(current_weights.to_dict(), ticker, w_req))
            if abs(float(cand.get(ticker, 0.0)) - w_req) <= REQUEST_TOL:
                as_requested = cand
        if as_requested is None:  # the idea at exactly its stated weight, the rest is the baseline
            as_requested = _with_remainder({ticker: w_req}, baseline.drop(ticker, errors="ignore"))
        if ticker in universe:
            w_cap = min(w_req, float(_asset_caps([ticker], info, profile_caps)[0]))
            fixed_capped = {ticker: w_cap}
            judge_caps = opt_caps
            if info.at[ticker, "asset_class"] not in EQUITY_CLASSES and opt_caps["equity_min"] > 1.0 - w_cap:
                # A pinned bond, gold or crypto line must leave room for the equity floor,
                # otherwise SLSQP is infeasible and the fallback silently ignores the floor.
                judge_caps = {**opt_caps, "equity_min": max(0.0, 1.0 - w_cap)}
            capped = optimize(cov, info, judge_caps, fixed=fixed_capped)
        else:
            capped = baseline.copy()  # excluded by a constraint: capped at zero
    else:
        as_requested = _preference_portfolio(profile, universe, info)
        capped = optimize(cov, info, opt_caps, target=as_requested, equity_floor=False)
        capped_floor = False

    if "esg_tilt" in profile.preferences:
        esgv = load_esgv()
        esg_proxy_set = {h.get("ticker") for h in (esgv or {}).get("holdings", [])} | {"ESGV"}
        capped = apply_esg_tilt(capped, universe, info, opt_caps, esg_proxy_set, fixed=fixed_capped)
        baseline = apply_esg_tilt(baseline, universe, info, opt_caps, esg_proxy_set)

    tilted = "esg_tilt" in profile.preferences  # a tilted scenario is kept close to its tilt
    if profile.objective != "capital_preservation":
        capped = limit_lines(capped, cov, info, opt_caps, fixed=fixed_capped, equity_floor=capped_floor,
                             min_variance=capped_floor and not tilted)
        baseline = limit_lines(baseline, cov, info, opt_caps, min_variance=not tilted)

    weights = {"as_requested": _clean(as_requested), "capped": capped, "profile_baseline": baseline}
    if current_weights is not None:
        w_cur = current_weights[current_weights > 1e-6].sort_index()
        weights["current"] = w_cur  # declared weights, never rescaled
    return weights, caps


def resolve_current(profile: Profile, info: pd.DataFrame) -> dict | None:
    """Declared holdings split into analysed, not analysed and cash. Nothing is rescaled.

    Weights at or under 1 in total are declared weights and are kept as they are; larger
    totals are percentages (up to 100) or dollar amounts, turned into shares of the declared
    total. A holding outside the universe keeps its declared weight: through a documented
    proxy when one exists, otherwise as "not analysed". What is left is cash.
    """
    from alphaforge.holdings import COMMON_PROXIES

    raw = {str(k).strip(): _num(v) for k, v in (profile.current_holdings or {}).items()}
    raw = {k: v for k, v in raw.items() if k and v > 0}
    extra = {str(k).strip(): _ratio(v) for k, v in (profile.holdings_unanalysed or {}).items()}
    extra = {k: v for k, v in extra.items() if k and v > 0}
    if not raw and not extra:
        return None
    total = sum(raw.values())
    if not raw or max(raw.values()) <= 1.0 + 1e-6:
        divisor = max(1.0, total)  # declared weights (a total slightly over 1 is rounding, not percentages)
    elif total <= 100.0 + 1e-6:
        divisor = 100.0  # percentages
    else:
        # dollar amounts: shares of the declared budget when there is one, so the undeclared
        # remainder is cash; shares of the declared total otherwise
        budget = _num(profile.budget_cad) if profile.budget_cad else 0.0
        divisor = max(total, budget)
    by_upper = {str(t).upper(): t for t in info.index}
    analysed: dict[str, float] = {}
    proxies: dict[str, str] = {}
    unanalysed = dict(extra)
    for k, v in raw.items():
        w = v / divisor
        up = k.upper()
        if up in by_upper:
            analysed[by_upper[up]] = analysed.get(by_upper[up], 0.0) + w
        elif up in COMMON_PROXIES and up not in {e.upper() for e in extra}:
            proxies[k] = COMMON_PROXIES[up]
            analysed[proxies[k]] = analysed.get(proxies[k], 0.0) + w
        else:
            unanalysed[k] = unanalysed.get(k, 0.0) + w
    known = sum(analysed.values()) + sum(unanalysed.values())
    if profile.holdings_cash is not None:
        cash = min(_ratio(profile.holdings_cash), max(1.0 - known, 0.0))
    else:
        cash = max(1.0 - known, 0.0)
    return {
        "analysed": {t: round(w, 6) for t, w in analysed.items()},
        "proxies": proxies,
        "unanalysed": {t: round(w, 6) for t, w in unanalysed.items()},
        "cash": round(cash, 6),
    }


def weight_gaps(
    analysed: dict[str, float],
    cash: float,
    target: dict[str, float],
    budget_cad: float | None = None,
) -> tuple[list[dict], float]:
    """Illustrative weight differences between the declared holdings and a scenario.

    Only known amounts move: the analysed holdings (budget × declared weight) and cash. The
    scenario weights apply to that part; holdings that are not analysed are left as they are
    and never appear here. No line is an order: each entry is a difference in weight (share
    of the whole portfolio) and, when the budget is known, the same difference in dollars.
    Turnover = 0.5 × (sum of absolute differences + cash used).
    """
    investable = sum(analysed.values()) + cash
    gaps: list[dict] = []
    moved = 0.0
    net = 0.0
    for t in sorted(set(analysed) | set(target)):
        cur = float(analysed.get(t, 0.0))
        tgt = float(target.get(t, 0.0)) * investable
        diff = round(tgt - cur, 4)
        moved += abs(diff)
        net += diff
        if abs(diff) < 1e-4:
            continue
        gap = {
            "ticker": t,
            "current_weight": round(cur, 4),
            "target_weight": round(tgt, 4),
            "change": diff,
            "action": GAP_LABEL_FR,
            "action_en": GAP_LABEL_EN,
        }
        if budget_cad and budget_cad > 0:
            gap["amount_cad"] = round(diff * budget_cad, 2)
        gaps.append(gap)
    gaps.sort(key=lambda g: (-abs(g["change"]), g["ticker"]))
    return gaps, round((moved + abs(net)) / 2.0, 4)


def scenario_metrics(
    weights: pd.Series,
    prices: pd.DataFrame,
    info: pd.DataFrame,
    *,
    account_type: str = "non_registered",
    as_of: dt.date | None = None,
    holdings_dir: Path | str | dt.date | None = None,
    horizon_years: float | None = 1,
) -> dict:
    """The fixed metric values (PRD 3.3, Issue #118, #119), computed with quant, tax and cost functions.

    Sector, country and single-name exposure look through ETF holdings (#173); the FX
    conversion cost is amortised over `horizon_years` in `all_in_cost` (#186 item 7).
    """
    w = weights.to_dict()
    conc = concentration(w, info, holdings_dir, as_of)
    usd_exp = usd_exposure(w, info)
    eff_sec = conc["effective_sectors"]
    stress = stress_2022(prices, w)
    tax_date = as_of or (prices.index[-1].date() if len(prices) else dt.date.today())
    tax_d = scenario_tax_drag(weights, account_type, tax_date, info)
    fee_d = calculate_fee_drag(weights, info)
    esg_s = calculate_esg_proxy_share(weights, holdings_dir=holdings_dir, as_of=tax_date)
    fx_c = fx_conversion_cost(usd_exp)
    return {
        "volatility_ann": volatility(prices, w),
        "max_drawdown": max_drawdown(prices, w),
        "stress_2022": stress["return"] if stress else None,
        "top_weight": conc["top_weight"],
        "sector_concentration_hhi": conc["sector_hhi"],
        "us_exposure": conc["us_exposure"],
        "tax_drag": tax_d,
        "fee_drag": fee_d,
        "esg_proxy_share": esg_s,
        "currency_usd_exposure": usd_exp,
        "effective_sectors": eff_sec,
        "canada_exposure": conc["canada_exposure"],
        "top_name_exposure": conc["top_name_exposure"],
        "top_name": conc["top_name"],
        "other_sector_share": conc["other_sector_share"],
        "fx_conversion_cost": fx_c,
        "all_in_cost": all_in_cost(fee_d, fx_c, tax_d, horizon_years)["value"],
    }


# --- node helpers -------------------------------------------------------------------------


def hhi_label(hhi: float | None, effective: float | None) -> str:
    """'0,38 ≈ 3 secteurs effectifs' (#173)."""
    if hhi is None or effective is None or not math.isfinite(effective):
        return "n.d."
    return f"{hhi:.2f}".replace(".", ",") + f" ≈ {max(1, round(effective))} secteurs effectifs"


def _metric_value(metric: str, scenario: str, values: dict, sector_assumption: str | None = None) -> dict:
    """The evidence value dict of a scenario metric; HHI carries its effective-sector reading."""
    val: dict = {"metric": metric, "scenario": scenario, "value": values.get(metric), "unit": "ratio"}
    if metric == "sector_concentration_hhi":
        eff = values.get("effective_sectors")
        val["effective_sectors"] = eff
        val["label"] = hhi_label(values.get(metric), eff)
        val["other_sector_share"] = values.get("other_sector_share")
        val["look_through"] = True
        if sector_assumption:
            val["assumption"] = sector_assumption
    return val


def _sector_assumption(reg: EvidenceRegistry, scenario: str, values: dict, as_of: dt.date) -> str | None:
    """Assumption cited by the HHI evidence: the undocumented ETF share is spread over the GICS sectors."""
    other = values.get("other_sector_share") or 0.0
    if other <= 0:
        return None
    return reg.add(
        f"Concentration sectorielle du scénario {scenario} : la part des FNB sans secteur documenté "
        f"({_pct(other)}) est supposée répartie également entre les {GICS_SECTORS} secteurs GICS ; "
        "un fonds indiciel large n'est pas un secteur à lui seul.",
        source="data/cache/holdings (titres hors univers sans secteur)",
        date=as_of,
        method=f"other_share^2 / {GICS_SECTORS} added to the HHI instead of other_share^2",
        confidence="assumption",
    )


def _r4(x) -> float | None:
    if x is None:
        return None
    x = float(x)
    return round(x, 4) if math.isfinite(x) else None


def _pct(v: float | None) -> str:
    return "n.d." if v is None else f"{v:.1%}"


def _caps_text(caps: dict) -> str:
    return (
        f"Action individuelle ≤ {caps['single_stock']:.0%}, FNB ≤ {caps['etf']:.0%}, "
        f"crypto ≤ {caps['crypto_total']:.0%}, actions entre {caps['equity_min']:.0%} "
        f"et {caps['equity_max']:.0%}."
    )


def _cited_tickers(objections: list[dict], evidence: dict) -> set[str]:
    out: set[str] = set()
    for o in objections:
        for eid in o.get("evidence") or []:
            ev = evidence.get(eid)
            v = ev.value if ev is not None else None
            if isinstance(v, dict):
                if isinstance(v.get("ticker"), str):
                    out.add(v["ticker"])
                out.update(t for t in v.get("tickers") or [] if isinstance(t, str))
    return out


def targeted_changes(
    objections: list[dict],
    evidence: dict,
    eligible: list[str],
    info: pd.DataFrame,
    caps: dict,
    requested: str | None,
) -> tuple[dict[str, float], list[str], list[str]]:
    """Map each blocking objection to a change on the lines it cites only (#116).

    overlap → the cited ETFs keep half of the ETF cap; concentration (sector, rates,
    currency) → the cited lines keep 80 % of their cap; exclusion, controversy or anything
    else → the cited lines are dropped. The requested idea is never touched here.
    Returns (per-ticker caps, dropped tickers, French descriptions of the changes)."""
    per_ticker: dict[str, float] = {}
    drop: set[str] = set()
    changes: list[str] = []
    base = {t: float(_asset_caps([t], info, caps)[0]) for t in eligible}
    for o in objections:
        cited = sorted((_cited_tickers([o], evidence) & set(eligible)) - {requested})
        if not cited:
            continue
        text = str(o.get("objection", "")).lower()
        metrics = {
            (evidence[e].value or {}).get("metric")
            for e in o.get("evidence") or []
            if e in evidence and isinstance(evidence[e].value, dict)
        }
        if "exclusion" in metrics or _DROP_RE.search(text):
            drop.update(cited)
            changes.append(f"retrait de {', '.join(cited)}")
        elif "etf_overlap" in metrics or _OVERLAP_RE.search(text):
            etfs = [t for t in cited if info.at[t, "asset_class"] not in ("equity", "crypto")]
            for t in etfs or cited:
                per_ticker[t] = min(per_ticker.get(t, 1.0), caps["etf"] * OVERLAP_ETF_SHARE)
            changes.append(f"plafond réduit pour {', '.join(etfs or cited)} (chevauchement)")
        elif _CONC_RE.search(text):
            for t in cited:
                per_ticker[t] = min(per_ticker.get(t, 1.0), base[t] * CONCENTRATION_SHARE)
            changes.append(f"plafond réduit de 20 % pour {', '.join(cited)} (concentration)")
        else:
            drop.update(cited)
            changes.append(f"retrait de {', '.join(cited)}")
    return per_ticker, sorted(drop), changes


def _template_notes(
    name,
    weights,
    values,
    ids,
    caps_eid,
    requested,
    flagged,
    account_type: str = "non_registered",
    language: str = "fr",
    asked_text: str | None = None,
) -> list[str]:
    is_en = language == "en"
    if is_en:
        risk = (
            f"Annualized volatility {_pct(values['volatility_ann'])} ({ids['volatility_ann']}), "
            f"historical maximum loss {_pct(values['max_drawdown'])} ({ids['max_drawdown']})."
        )
        if "sector_concentration_hhi" in ids and values.get("sector_concentration_hhi") is not None:
            label = hhi_label(values["sector_concentration_hhi"], values.get("effective_sectors"))
            label = label.replace(",", ".").replace("secteurs effectifs", "effective sectors")
            risk += f" Sector concentration HHI {label}, looking through ETF holdings ({ids['sector_concentration_hhi']})."
        if "tax_drag" in ids and values.get("tax_drag") is not None:
            risk += f" Estimated annual tax drag {_pct(values['tax_drag'])} ({ids['tax_drag']})."
        if "esg_proxy_share" in ids and values.get("esg_proxy_share") is not None:
            risk += f" ESG proxy share {_pct(values['esg_proxy_share'])} ({ids['esg_proxy_share']})."
        if name == "as_requested":
            if asked_text:
                head = f"Allocation as requested: {asked_text}; the remainder follows the stated preferences."
            elif requested in weights:
                head = (
                    f"Idea as requested: {weights[requested]:.0%} in {requested}, "
                    "the remainder according to the reference allocation."
                )
            else:
                head = (
                    f"Stated preferences taken as requested: equal weighting across "
                    f"{len(weights)} assets, without risk management."
                )
            notes = [head, risk]
            if flagged:
                notes.append(
                    "This asset is excluded by a profile constraint; it is included here for "
                    "comparison purposes only."
                )
        elif name == "capped":
            head = f"Same request brought within profile limits ({caps_eid})"
            head += f": {requested} at {weights.get(requested, 0.0):.0%}." if requested else "."
            notes = [head, risk]
        else:
            notes = [
                f"Minimum variance allocation under profile limits ({caps_eid}), "
                "without any return forecast.",
                risk,
            ]
    else:
        risk = (
            f"Volatilité annualisée {_pct(values['volatility_ann'])} ({ids['volatility_ann']}), "
            f"perte maximale historique {_pct(values['max_drawdown'])} ({ids['max_drawdown']})."
        )
        if "sector_concentration_hhi" in ids and values.get("sector_concentration_hhi") is not None:
            label = hhi_label(values["sector_concentration_hhi"], values.get("effective_sectors"))
            risk += f" Concentration sectorielle HHI {label}, en transparence des FNB ({ids['sector_concentration_hhi']})."
        if "tax_drag" in ids and values.get("tax_drag") is not None:
            risk += f" Friction fiscale annuelle estimée {_pct(values['tax_drag'])} ({ids['tax_drag']})."
        if "esg_proxy_share" in ids and values.get("esg_proxy_share") is not None:
            risk += f" Part du portefeuille dans des titres présents dans le fonds ESGV (indicateur indirect) : {_pct(values['esg_proxy_share'])} ({ids['esg_proxy_share']})."
        if name == "as_requested":
            if asked_text:
                head = f"Répartition telle que demandée : {asked_text} ; le reste suit les préférences déclarées."
            elif requested in weights:
                head = (
                    f"Idée telle que demandée : {weights[requested]:.0%} dans {requested}, "
                    "le reste selon l'allocation de référence."
                )
            else:
                head = (
                    f"Préférences déclarées prises telles quelles : pondération égale sur "
                    f"{len(weights)} actifs, sans gestion du risque."
                )
            notes = [head, risk]
            if flagged:
                notes.append(
                    "Cet actif est exclu par une contrainte du profil ; il figure ici uniquement "
                    "à titre de comparaison."
                )
        elif name == "capped":
            head = f"Même demande ramenée aux limites du profil ({caps_eid})"
            head += f" : {requested} à {weights.get(requested, 0.0):.0%}." if requested else "."
            notes = [head, risk]
        else:
            notes = [
                f"Allocation de variance minimale sous les limites du profil ({caps_eid}), "
                "sans aucune prévision de rendement.",
                risk,
            ]

    loc_note = asset_location_note(account_type)
    if loc_note and loc_note not in notes:
        notes.append(loc_note)
    if "esg_proxy_share" in ids:
        esg_limit_note = (
            "Share of the portfolio in assets held by the ESGV fund (indirect indicator): limited to U.S. equities; this is not a guarantee of sustainability nor an ESG score."
            if is_en
            else "Part du portefeuille dans des titres présents dans le fonds ESGV (indicateur indirect) : limitée aux actions américaines, ne constitue pas un score ESG ni une garantie de durabilité."
        )
        if esg_limit_note not in notes:
            notes.append(esg_limit_note)
    return notes


# --- node ---------------------------------------------------------------------------------


@traced("scenarios")
def scenarios_node(state: GraphState) -> dict:
    lang: str = getattr(state.profile, "language", None) or getattr(state, "language", "fr")
    reg = EvidenceRegistry("EP")
    profile = state.profile
    eligible = sorted(state.eligible_universe)
    if profile is None or not eligible:
        return {
            "scenarios": [],
            "evidence": reg.items(),
            "summary": "Aucun actif admissible : scénarios non construits.",
        }

    provider = get_provider()
    # An ingested asset (AF_DYNAMIC_INGESTION) is only known to the provider when asked for.
    asked_idea = (profile.requested_idea or {}).get("ticker")
    info = provider.asset_info(include_custom=sorted(set(eligible) | ({asked_idea} if asked_idea else set())))
    blocking = [o for o in state.objections if o.get("severity") == "blocking"]
    rounds = state.retries.get("red_team", 0) if blocking else 0
    request = translate_request(profile, info)
    requested = None
    if request and request["kind"] == "idea" and request["weights"]:
        requested = next(iter(request["weights"]))
    per_ticker, drop, changes = targeted_changes(
        blocking, state.evidence, eligible, info, caps_for(profile), requested
    )
    # Declared holdings: analysed part, not-analysed part and cash, never rescaled (#120, P0-2)
    current_weights: pd.Series | None = None
    proxies_used: dict[str, str] = {}
    unanalysed: dict[str, float] = dict(profile.holdings_unanalysed or {})
    cash_share = 0.0
    held = resolve_current(profile, info)
    if held:
        proxies_used, unanalysed, cash_share = held["proxies"], held["unanalysed"], held["cash"]
        if held["analysed"]:
            current_weights = pd.Series(held["analysed"], dtype=float)
    not_analysed = sorted(unanalysed)
    unanalysed_share = round(sum(unanalysed.values()), 4)
    analysed_share = round(float(current_weights.sum()), 4) if current_weights is not None else 0.0

    current_tickers = set(current_weights.index) if current_weights is not None else set()
    asked_tickers = set((request or {}).get("weights", {}))
    tickers = sorted(set(eligible) | asked_tickers | current_tickers)
    prices = provider.prices_cad(tickers, state.as_of_date)

    weights, caps = build_scenarios(
        profile,
        eligible,
        prices,
        info,
        rounds=rounds,
        drop=drop,
        per_ticker=per_ticker,
        current_weights=current_weights,
    )

    as_of = state.as_of_date
    level = effective_risk(profile.risk_tolerance, profile.risk_capacity)
    binding = (
        "la capacité de risque"
        if level != profile.risk_tolerance
        else "la tolérance au risque"
    )
    caps_eid = reg.add(
        {
            "metric": "caps",
            "tolerance": profile.risk_tolerance,
            "capacity": profile.risk_capacity,
            "effective": level,
            "value": f"{_caps_text(caps)} ; niveau retenu : {level}, fixé par {binding}",
        },
        source="PRD 5.7 caps table",
        date=as_of,
        method=f"caps for the lower of tolerance ({profile.risk_tolerance}) and capacity "
        f"({profile.risk_capacity}) = {level}",
        confidence="assumption",
    )
    if rounds:
        done = "; ".join(changes) if changes else "aucune ligne citée, scénarios inchangés"
        text = f"Scénarios révisés après objection (passage {rounds}) : {done}."
        reg.add(text, source="red team objections", date=as_of,
                method="scenario retry rule (PRD 5.8 loop contract)", confidence="assumption")
    flagged = requested is not None and requested not in eligible
    if flagged:
        reg.add(
            f"L'actif demandé ({requested}) est exclu par une contrainte du profil : il "
            "n'apparaît que dans le scénario demandé, à titre de comparaison.",
            source="screening", date=as_of, method="requested ticker kept for comparison",
            confidence="assumption",
        )
    if proxies_used:
        proxy_desc = ", ".join(f"{orig} → {proxy}" for orig, proxy in sorted(proxies_used.items()))
        reg.add(
            f"Actifs du portefeuille actuel représentés par procuration (proxy) : {proxy_desc}.",
            source="alphaforge.holdings proxy table",
            date=as_of,
            method="mapping of non-universe assets to closest 31-asset equivalent",
            confidence="assumption",
        )
    if not_analysed:
        lines = ", ".join(f"{t} ({_pct(unanalysed[t])})" for t in not_analysed)
        reg.add(
            f"Titres non analysés du portefeuille actuel ({_pct(unanalysed_share)}) : {lines}. "
            "Ils restent à leur poids déclaré : ils ne sont ni repondérés ni inclus dans les "
            "écarts de pondération.",
            source="screening",
            date=as_of,
            method="assets outside the 31-asset universe without proxy are kept at their declared "
            "weight and left out of the analysis",
            confidence="assumption",
        )

    end = prices.index[-1].date() if len(prices) else as_of
    window = f"{prices.index[0].date()}..{end}" if len(prices) else "no data"
    evidence_so_far = dict(state.evidence)

    # Compute metric values for all scenarios
    all_values: dict[str, dict] = {}
    scenario_ids: dict[str, dict] = {name: {} for name in SCENARIO_NAMES}
    for name in SCENARIO_NAMES:
        w = weights[name]
        all_values[name] = {
            k: _r4(v) if not isinstance(v, str) else v
            for k, v in scenario_metrics(
                w, prices, info, account_type=profile.account_type, as_of=as_of,
                horizon_years=profile.horizon_years,
            ).items()
        }

    # Pass 1: standard risk metrics (EP2..EP7, EP8..EP13, EP14..EP19)
    price_source = getattr(provider, "evidence_source", SOURCE)
    for name in SCENARIO_NAMES:
        if all_values[name].get("stress_2022") is not None:
            continue
        note = stress_2022_note(prices, weights[name].to_dict(), f"Scénario {name}")
        if note:
            reg.add(
                note,
                source=price_source,
                date=end,
                method="2022 stress window not usable for every line of the scenario (short history)",
                confidence="assumption",
            )
    base_metrics = [m for m in SCENARIO_METRICS if m not in ("tax_drag", "fee_drag")]
    for name in SCENARIO_NAMES:
        values = all_values[name]
        sector_eid = _sector_assumption(reg, name, values, as_of)
        for m in base_metrics:
            scenario_ids[name][m] = reg.add(
                _metric_value(m, name, values, sector_eid),
                source=price_source,
                date=end,
                method=f"{METHODS[m]}, historical backtest of fictional weights, {window}",
                confidence="fact" if values[m] is not None else "assumption",
            )

    # Pass 2a: tax drag metric per scenario (marked as an assumption)
    if "tax_drag" in SCENARIO_METRICS:
        for name in SCENARIO_NAMES:
            values = all_values[name]
            scenario_ids[name]["tax_drag"] = reg.add(
                {
                    "metric": "tax_drag",
                    "scenario": name,
                    "account_type": profile.account_type,
                    "value": values["tax_drag"],
                    "unit": "ratio",
                },
                source="Règles fiscales ARC et convention fiscale Canada-É.-U.",
                url="https://www.canada.ca/en/revenue-agency/services/tax/individuals/frequently-asked-questions-individuals/canadian-income-tax-rates-individuals-current-previous-years.html",
                date=end,
                method=f"{METHODS['tax_drag']}, compte {profile.account_type}",
                confidence="assumption",
            )

    # Pass 2b: fee drag metric per scenario (marked as an assumption)
    if "fee_drag" in SCENARIO_METRICS:
        for name in SCENARIO_NAMES:
            values = all_values[name]
            scenario_ids[name]["fee_drag"] = reg.add(
                {
                    "metric": "fee_drag",
                    "scenario": name,
                    "value": values["fee_drag"],
                    "unit": "ratio",
                },
                source="Ratios de dépenses de gestion (RFG/MER) des émetteurs de FNB",
                url="https://www.blackrock.com/ca/investors/en/products/product-list",
                date=end,
                method=f"{METHODS['fee_drag']}, moyenne pondérée des RFG de l'allocation",
                confidence="assumption",
            )

    # Pass 2c: ESG tilt proxy assumption evidence and scenario metric
    if "esg_tilt" in profile.preferences:
        esgv_doc = load_esgv(HOLDINGS_DIR, as_of=as_of)
        esgv_date_str = esgv_doc.get("as_of", "2026-09-30") if esgv_doc else "2026-09-30"
        try:
            esgv_date = dt.date.fromisoformat(esgv_date_str)
        except ValueError:
            esgv_date = as_of
        source_url = (
            esgv_doc.get("source_url")
            if esgv_doc
            else "https://investor.vanguard.com/investment-products/etfs/profile/esgv"
        )
        held_tickers = {h.get("ticker") for h in (esgv_doc or {}).get("holdings", [])} | {"ESGV"}
        eligible_proxy = sorted(set(eligible) & held_tickers)
        proxy_tickers_str = ", ".join(eligible_proxy)

        reg.add(
            f"Proxy ESG (préférence esg_tilt) : titres admissibles membres du fonds Vanguard ESGV ou le FNB lui-même ({proxy_tickers_str}) au {esgv_date_str}. "
            "Limites méthodologiques : actions américaines uniquement, l'appartenance n'est pas un score ESG continu, "
            "les actions canadiennes, obligations et or ne sont pas couverts par ce filtre.",
            source="Vanguard ESGV holdings",
            url=source_url,
            date=esgv_date,
            method=f"proxy ESG via composition ESGV au {esgv_date_str} : actions américaines uniquement, l'appartenance n'est pas un score, actions canadiennes/obligations/or non couvertes",
            confidence="assumption",
        )

        for name in SCENARIO_NAMES:
            values = all_values[name]
            scenario_ids[name]["esg_proxy_share"] = reg.add(
                {
                    "metric": "esg_proxy_share",
                    "scenario": name,
                    "value": values["esg_proxy_share"],
                    "unit": "ratio",
                },
                source="Vanguard ESGV holdings",
                url=source_url,
                date=esgv_date,
                method="part du portefeuille dans des titres présents dans le fonds ESGV (indicateur indirect)",
                confidence="assumption",
            )

    # Pass 3: Sourced tax rules evidence entries, plus the two limits of the estimate
    reg.add(
        "Estimation fiscale limitée à l'impôt fédéral (tranche de 20,5 %) : l'impôt provincial "
        "n'est pas inclus, la charge fiscale réelle est donc plus élevée dans un compte imposable.",
        source="hypothèse de calcul",
        date=as_of,
        method="scope of the tax-drag estimate",
        confidence="assumption",
    )
    if profile.persona in PERSONAS and profile.account_type == PERSONAS[profile.persona].get("account_type"):
        reg.add(
            f"Type de compte « {profile.account_type} » attribué par hypothèse au persona "
            f"{profile.persona} : le cas de l'atelier ne le précise pas.",
            source="hypothèse de persona",
            date=as_of,
            method="persona default account type",
            confidence="assumption",
        )
    for rule in tax_rules_evidence(as_of, profile.account_type):
        reg.add(
            rule["value"],
            source=rule["source"],
            url=rule["url"],
            date=rule["date"],
            method=rule["method"],
            confidence=rule["confidence"],
        )

    # Sourced ETF MER, FX conversion cost, and capital preservation bond rule assumption evidence
    for entry in etf_mer_evidence(as_of):
        reg.add(
            entry["value"],
            source=entry["source"],
            url=entry["url"],
            date=entry["date"],
            method=entry["method"],
            confidence=entry["confidence"],
        )

    for name in SCENARIO_NAMES:
        usd_share = all_values[name].get("currency_usd_exposure") or 0.0
        fx_ev = fx_conversion_evidence(as_of, usd_share, name)
        reg.add(
            fx_ev["value"],
            source=fx_ev["source"],
            url=fx_ev["url"],
            date=fx_ev["date"],
            method=fx_ev["method"],
            confidence=fx_ev["confidence"],
        )

    if profile.objective == "capital_preservation":
        fb_ev = capital_preservation_foreign_bond_evidence(as_of)
        reg.add(
            fb_ev["value"],
            source=fb_ev["source"],
            url=fb_ev["url"],
            date=fb_ev["date"],
            method=fb_ev["method"],
            confidence=fb_ev["confidence"],
        )

    from alphaforge.nodes.quant import rolling_returns_stats

    # Survivorship warning registered here so it can be cited next to the historical returns (#176)
    survivorship_eid = reg.add(
        SURVIVORSHIP_NOTE_FR,
        source="assets_universe.csv + prices_daily.csv",
        date=as_of,
        method="known limitation of the starter dataset: survivors only, prices from 2021-11",
        confidence="assumption",
    )
    index_hist = load_index_history(as_of)

    def add_long_proxy(sc_name: str, w: pd.Series, outcomes: dict) -> dict[str, str]:
        """Drawdown and stress companions on long index proxies (2000-02, 2008); ids by metric."""
        shares = proxy_shares(w.to_dict(), info)
        label = proxy_label(shares)
        ids_p: dict[str, str] = {}
        if index_hist.empty:
            return ids_p
        hist_window = f"{index_hist.index[0].date()}..{index_hist.index[-1].date()}"
        s_2000 = proxy_stress(index_hist, shares, "stress_2000_02")
        s_2008 = proxy_stress(index_hist, shares, "stress_2008")
        results = {
            "max_drawdown_long_proxy": (proxy_drawdown(index_hist, shares), None),
            "stress_2000_02_proxy": (s_2000["return"], s_2000["drawdown"]) if s_2000 else (None, None),
            "stress_2008_proxy": (s_2008["return"], s_2008["drawdown"]) if s_2008 else (None, None),
        }
        proxy_out: dict = {"shares": shares, "label": label, "window": hist_window}
        for m, (val, dd) in results.items():
            value: dict = {
                "metric": m, "scenario": sc_name, "value": _r4(val), "unit": "ratio",
                "proxy": label, "window": hist_window, "survivorship_note": survivorship_eid,
            }
            if dd is not None:
                value["drawdown"] = _r4(dd)
            ids_p[m] = reg.add(
                value,
                source="index_history/index_monthly.csv (Yahoo Finance, monthly closes)",
                url=INDEX_SOURCE_URL,
                date=index_hist.index[-1].date(),
                method=f"{METHODS[m]}; monthly closes, local currency (USD indexes, CAD for S&P/TSX), "
                f"AGG flat before 2003-09; rows <= {as_of} only; proxy = {label}",
                confidence="fact" if val is not None else "assumption",
            )
            proxy_out[m] = _r4(val)
            if dd is not None:
                proxy_out[f"{m}_drawdown"] = _r4(dd)
        outcomes["long_proxy"] = proxy_out
        outcomes["survivorship_evidence"] = survivorship_eid
        return ids_p

    def long_proxy_note(ids_p: dict[str, str], outcomes: dict, en: bool) -> str | None:
        lp = outcomes.get("long_proxy")
        if not lp or lp.get("max_drawdown_long_proxy") is None:
            return None
        if en:
            txt = (
                f"On long index proxies ({lp['label']}; {lp['window']}): largest historical loss "
                f"{_pct(lp['max_drawdown_long_proxy'])} ({ids_p['max_drawdown_long_proxy']})"
            )
            if lp.get("stress_2000_02_proxy") is not None:
                txt += f", 2000-02 episode {_pct(lp['stress_2000_02_proxy'])} ({ids_p['stress_2000_02_proxy']})"
            if lp.get("stress_2008_proxy") is not None:
                txt += f", 2008 episode {_pct(lp['stress_2008_proxy'])} ({ids_p['stress_2008_proxy']})"
            return txt + f". Survivorship caveat: {survivorship_eid} (historical, not a forecast)."
        txt = (
            f"Sur des indices de référence à long historique ({lp['label']} ; {lp['window']}) : perte "
            f"maximale historique {_pct(lp['max_drawdown_long_proxy'])} ({ids_p['max_drawdown_long_proxy']})"
        )
        if lp.get("stress_2000_02_proxy") is not None:
            txt += f", épisode 2000-02 {_pct(lp['stress_2000_02_proxy'])} ({ids_p['stress_2000_02_proxy']})"
        if lp.get("stress_2008_proxy") is not None:
            txt += f", épisode 2008 {_pct(lp['stress_2008_proxy'])} ({ids_p['stress_2008_proxy']})"
        return txt + f". Biais du survivant : {survivorship_eid} (historique, pas une prévision)."

    asked_text = None
    if request and request["kind"] == "allocation" and request["groups"]:
        asked_text = ", ".join(f"{wt:.0%} {label}" for label, _, wt in request["groups"])
    scenarios = []
    for name in SCENARIO_NAMES:
        w = weights[name]
        values = all_values[name]
        ids = scenario_ids[name]
        sc = Scenario(name=name, weights=w.to_dict(), metrics=ids)
        if current_weights is not None:
            trades, turnover = weight_gaps(
                current_weights.to_dict(), cash_share, w.to_dict(), profile.budget_cad
            )
            sc.trades = trades
            sc.turnover = turnover
            reg.add(
                {"metric": "turnover", "scenario": name, "value": turnover, "unit": "ratio"},
                source="current holdings vs scenario weights",
                date=end,
                method="0.5 * (sum(abs(target_weight - current_weight)) + cash used), on the "
                "analysed holdings and cash only; illustrative weight differences, not orders",
                confidence="fact",
            )
        # Rolling returns over 1-year and 3-year windows (A-13 / #122)
        stats_1y = rolling_returns_stats(prices, w, window_years=1)
        stats_3y = rolling_returns_stats(prices, w, window_years=3)

        outcomes = {
            "disclaimer": "historique, pas une prévision",
            "horizon_years": profile.horizon_years,
            "horizon_covered": profile.horizon_years <= 3,
        }

        if stats_1y:
            outcomes["1y"] = stats_1y
            for metric_k in ("worst", "median", "best", "loss_share"):
                reg.add(
                    {
                        "metric": f"rolling_1y_{metric_k}",
                        "scenario": name,
                        "value": _r4(stats_1y[metric_k]),
                        "unit": "ratio",
                        "disclaimer": "historique, pas une prévision",
                        "survivorship_note": survivorship_eid,
                    },
                    source=price_source,
                    date=end,
                    method=f"Rolling 1-year historical window ({stats_1y['windows_count']} windows), CAD. Historique, pas une prévision.",
                    confidence="fact",
                )
        if stats_3y:
            outcomes["3y"] = stats_3y
            for metric_k in ("worst", "median", "best", "loss_share"):
                reg.add(
                    {
                        "metric": f"rolling_3y_{metric_k}",
                        "scenario": name,
                        "value": _r4(stats_3y[metric_k]),
                        "unit": "ratio",
                        "disclaimer": "historique, pas une prévision",
                        "survivorship_note": survivorship_eid,
                    },
                    source=price_source,
                    date=end,
                    method=f"Rolling 3-year historical window ({stats_3y['windows_count']} windows), CAD. Historique, pas une prévision.",
                    confidence="fact",
                )

        sc.historical_outcomes = outcomes
        notes = _template_notes(
            name,
            w,
            values,
            ids,
            caps_eid,
            requested,
            flagged,
            account_type=profile.account_type,
            language=lang,
            asked_text=asked_text,
        )
        if stats_1y:
            notes.append(
                f"Rolling 1-year historical returns (historical, not a forecast): "
                f"worst {_pct(stats_1y['worst'])}, median {_pct(stats_1y['median'])}, "
                f"best {_pct(stats_1y['best'])}, loss periods share {_pct(stats_1y['loss_share'])}. "
                f"Survivorship caveat: {survivorship_eid}."
                if lang == "en"
                else
                f"Rendements historiques glissants sur 1 an (historique, pas une prévision) : "
                f"pire {_pct(stats_1y['worst'])}, médiane {_pct(stats_1y['median'])}, "
                f"meilleur {_pct(stats_1y['best'])}, part des périodes en perte {_pct(stats_1y['loss_share'])}. "
                f"Biais du survivant : {survivorship_eid}."
            )
        if stats_3y:
            notes.append(
                f"Rolling 3-year historical returns (historical, not a forecast): "
                f"worst {_pct(stats_3y['worst'])}, median {_pct(stats_3y['median'])}, "
                f"best {_pct(stats_3y['best'])}, loss periods share {_pct(stats_3y['loss_share'])}. "
                f"Survivorship caveat: {survivorship_eid}."
                if lang == "en"
                else
                f"Rendements historiques glissants sur 3 ans (historique, pas une prévision) : "
                f"pire {_pct(stats_3y['worst'])}, médiane {_pct(stats_3y['median'])}, "
                f"meilleur {_pct(stats_3y['best'])}, part des périodes en perte {_pct(stats_3y['loss_share'])}. "
                f"Biais du survivant : {survivorship_eid}."
            )
        proxy_ids = add_long_proxy(name, w, outcomes)
        proxy_note = long_proxy_note(proxy_ids, outcomes, lang == "en")
        if proxy_note:
            notes.append(proxy_note)
        if profile.horizon_years > 3:
            notes.append(
                f"Available historical window (5 years) covers 1-year and 3-year windows; "
                f"stated horizon of {profile.horizon_years} years is not fully covered by data "
                "(historical, not a forecast)."
                if lang == "en"
                else
                f"L'historique disponible (5 ans) permet de calculer les fenêtres de 1 an et 3 ans ; "
                f"l'horizon déclaré de {profile.horizon_years} ans n'est pas couvert par les données "
                "(historique, pas une prévision)."
            )
        if draft_notes is not None:
            try:
                notes = list(draft_notes(sc, evidence_so_far | reg.items(), profile=state.profile)) or notes
            except Exception:
                pass  # the LLM is optional here; templated notes are always valid
        if profile.hard_gate_notes:
            notes = list(profile.hard_gate_notes) + notes
        sc.notes = notes
        scenarios.append(sc)

    # Fourth reference column: client's current portfolio (#120)
    if current_weights is not None:
        w_curr = weights["current"]  # declared weights; may sum to less than 1
        w_part = w_curr / w_curr.sum()  # the analysed part on its own, for the metrics only
        partial = analysed_share < 1.0 - 1e-4
        part_note = (
            f", computed on the analysed part only ({analysed_share:.1%} of the declared "
            "portfolio, taken as 100 %)" if partial else ""
        )
        values_curr = {
            k: _r4(v) if not isinstance(v, str) else v
            for k, v in scenario_metrics(
                w_part, prices, info, account_type=profile.account_type, as_of=as_of,
                horizon_years=profile.horizon_years,
            ).items()
        }
        ids_curr = {}
        sector_eid_curr = _sector_assumption(reg, "current", values_curr, as_of)
        for m in SCENARIO_METRICS:
            if m == "tax_drag":
                ids_curr[m] = reg.add(
                    {
                        "metric": "tax_drag",
                        "scenario": "current",
                        "account_type": profile.account_type,
                        "value": values_curr["tax_drag"],
                        "unit": "ratio",
                    },
                    source="Règles fiscales ARC et convention fiscale Canada-É.-U.",
                    url="https://www.canada.ca/en/revenue-agency/services/tax/individuals/frequently-asked-questions-individuals/canadian-income-tax-rates-individuals-current-previous-years.html",
                    date=end,
                    method=f"{METHODS['tax_drag']}, compte {profile.account_type}{part_note}",
                    confidence="assumption",
                )
            elif m == "fee_drag":
                ids_curr[m] = reg.add(
                    {
                        "metric": "fee_drag",
                        "scenario": "current",
                        "value": values_curr["fee_drag"],
                        "unit": "ratio",
                    },
                    source="Ratios de dépenses de gestion (RFG/MER) des émetteurs de FNB",
                    url="https://www.blackrock.com/ca/investors/en/products/product-list",
                    date=end,
                    method=f"{METHODS['fee_drag']}, moyenne pondérée des RFG du portefeuille actuel{part_note}",
                    confidence="assumption",
                )
            else:
                ids_curr[m] = reg.add(
                    _metric_value(m, "current", values_curr, sector_eid_curr),
                    source=SOURCE,
                    date=end,
                    method=f"{METHODS[m]}, historical backtest of client's current holdings, {window}{part_note}",
                    confidence="fact" if values_curr[m] is not None else "assumption",
                )
        if "esg_tilt" in profile.preferences:
            ids_curr["esg_proxy_share"] = reg.add(
                {
                    "metric": "esg_proxy_share",
                    "scenario": "current",
                    "value": values_curr["esg_proxy_share"],
                    "unit": "ratio",
                },
                source="Vanguard ESGV holdings",
                url=source_url,
                date=esgv_date,
                method="part du portefeuille dans des titres présents dans le fonds ESGV (indicateur indirect), portefeuille actuel",
                confidence="assumption",
            )
        stats_1y_curr = rolling_returns_stats(prices, w_part, window_years=1)
        stats_3y_curr = rolling_returns_stats(prices, w_part, window_years=3)
        outcomes_curr = {
            "disclaimer": "historique, pas une prévision",
            "horizon_years": profile.horizon_years,
            "horizon_covered": profile.horizon_years <= 3,
        }
        if stats_1y_curr:
            outcomes_curr["1y"] = stats_1y_curr
        if stats_3y_curr:
            outcomes_curr["3y"] = stats_3y_curr
        proxy_ids_curr = add_long_proxy("current", w_part, outcomes_curr)

        en = lang == "en"
        notes_curr = [
            f"Client's current portfolio: {len(w_curr)} analysed asset(s), {_pct(analysed_share)} of the declared portfolio."
            if en
            else f"Portefeuille actuel du client : {len(w_curr)} actif(s) analysé(s), soit {_pct(analysed_share)} du portefeuille déclaré.",
            f"Annualized volatility {_pct(values_curr['volatility_ann'])} ({ids_curr['volatility_ann']}), "
            f"historical maximum loss {_pct(values_curr['max_drawdown'])} ({ids_curr['max_drawdown']})."
            if en
            else f"Volatilité annualisée {_pct(values_curr['volatility_ann'])} ({ids_curr['volatility_ann']}), "
            f"perte maximale historique {_pct(values_curr['max_drawdown'])} ({ids_curr['max_drawdown']}).",
        ]
        if partial:
            notes_curr.append(
                "These metrics describe the analysed part only; weights are the declared ones, not rescaled."
                if en
                else "Ces mesures portent sur la partie analysée seulement ; les poids sont ceux déclarés, sans repondération."
            )
        if proxies_used:
            notes_curr.append(
                f"{'Assets with proxy' if en else 'Actifs avec proxy'}{'' if en else ' '}: {', '.join(proxies_used.keys())}."
            )
        if not_analysed:
            notes_curr.append(
                f"Not analysed, kept as declared ({_pct(unanalysed_share)}): {', '.join(not_analysed)}."
                if en
                else f"Non analysé, conservé tel que déclaré ({_pct(unanalysed_share)}) : {', '.join(not_analysed)}."
            )
        if cash_share > 1e-4:
            notes_curr.append(
                f"Undeclared remainder treated as cash: {_pct(cash_share)}."
                if en
                else f"Reste non déclaré traité comme des liquidités : {_pct(cash_share)}."
            )
        proxy_note_curr = long_proxy_note(proxy_ids_curr, outcomes_curr, en)
        if proxy_note_curr:
            notes_curr.append(proxy_note_curr)
        sc_curr = Scenario(
            name="current",
            weights=w_curr.to_dict(),
            metrics=ids_curr,
            notes=notes_curr,
            historical_outcomes=outcomes_curr,
        )
        scenarios.append(sc_curr)

    # --- appended after every existing entry so that earlier evidence ids do not move -------
    # New scenario metrics: USD currency exposure, effective sectors, all-in cost (P1 c)
    def add_extra(sc: Scenario, values: dict, note: str = "") -> None:
        ids_x: dict[str, str] = {}
        for m in EXTRA_METRICS:
            val: dict = {"metric": m, "scenario": sc.name, "value": values.get(m), "unit": EXTRA_UNITS[m]}
            if m == "all_in_cost":
                val["components"] = all_in_cost(
                    values.get("fee_drag"), values.get("fx_conversion_cost"), values.get("tax_drag"),
                    profile.horizon_years,
                )["components"]
            elif m == "top_name_exposure":
                val["name"] = values.get("top_name")
            elif m == "effective_sectors":
                val["label"] = hhi_label(values.get("sector_concentration_hhi"), values.get(m))
            method = METHODS[m]
            if m == "all_in_cost":
                method += f"; FX cost / {max(float(profile.horizon_years or 1), 1.0):.0f} years"
            ids_x[m] = reg.add(
                val,
                source=price_source if m != "all_in_cost" else "RFG des émetteurs, grille de change des courtiers, règles fiscales ARC",
                date=end,
                method=f"{method}{note}",
                confidence="assumption" if m == "all_in_cost" or values.get(m) is None else "fact",
            )
        # Evidence items for extra metrics are registered in evidence registry;
        # sc.metrics keeps only the frozen SCENARIO_METRICS keys (and esg_proxy_share if active).

    for sc in scenarios:
        if sc.name == "current":
            add_extra(sc, values_curr, part_note)
        else:
            add_extra(sc, all_values[sc.name])

    # How the question was translated into weights, and whether it is all there (P0-1)
    gaps = request_gaps(weights["as_requested"], request)
    if request:
        if request["groups"]:
            asked_desc = "; ".join(
                f"{label} {wt:.1%}" + (f" (réparti également entre {', '.join(ts)})" if len(ts) > 1 else "")
                for label, ts, wt in request["groups"]
            )
        else:
            asked_desc = "aucun poids associé à un actif analysé"
        rest = max(1.0 - sum(request["weights"].values()), 0.0)
        fill = (
            "les préférences déclarées du profil" if request["kind"] == "allocation"
            else "le portefeuille actuel ou l'allocation de référence"
        )
        text = f"Demande traduite en pondérations pour le scénario demandé : {asked_desc}."
        if rest > REQUEST_TOL:
            text += f" Le reste ({rest:.1%}) suit {fill}."
        if profile.requested_vehicle:
            text += (
                f" Le véhicule nommé dans la question ({profile.requested_vehicle}) est hors de "
                "l'univers analysé : il est représenté par l'actif analysé correspondant."
            )
        reg.add(text, source="question de l'utilisateur (profil analysé)", date=as_of,
                method="requested_allocation / requested_idea mapped to universe tickers; a class "
                "weight is split equally across the universe assets of that class",
                confidence="assumption")
    if gaps:
        reg.add(
            "Je n'ai pas pu traduire votre demande en portefeuille : " + " ; ".join(gaps) + ".",
            source="contrôle du scénario demandé", date=as_of,
            method="check that every requested asset and weight is present in as_requested",
            confidence="assumption",
        )
    calib = growth_calibration(profile)
    if calib:
        reg.add(
            f"Profil de croissance à risque élevé : la table des plafonds prévoit 80 % à 100 % "
            f"d'actions ; l'allocation de référence vise au moins {calib['equity_min']:.0%} d'actions "
            f"et ne détient pas d'obligations à très court terme ({calib['excluded']}), qui "
            "tiennent lieu de liquidités.",
            source="PRD 5.7 caps table", date=as_of,
            method="baseline calibration for a high-risk growth profile (middle of the equity band)",
            confidence="assumption",
        )
    lines_rule = (
        f"Lignes des scénarios plafonné et de référence : au plus {MAX_LINES} lignes et aucune sous "
        f"{MIN_LINE:.0%} (sauf l'idée demandée, gardée à son poids plafonné)."
    )
    if profile.objective == "capital_preservation":
        lines_rule += (
            " Cette règle n'est pas appliquée aux profils de préservation du capital : leurs scénarios "
            "gardent toutes les lignes de l'optimisation, y compris celles sous "
            f"{MIN_LINE:.0%}, pour ne pas concentrer le volet obligataire."
        )
    reg.add(
        lines_rule,
        source="règle de construction AlphaForge", date=as_of,
        method="largest lines kept, then closest portfolio under the same caps with a minimum line size"
        + ("; rule skipped for capital_preservation" if profile.objective == "capital_preservation" else ""),
        confidence="assumption",
    )
    if current_weights is not None:
        reg.add(
            {
                "metric": "current_analysed_share",
                "scenario": "current",
                "value": analysed_share,
                "unit": "ratio",
                "unanalysed_share": unanalysed_share,
                "cash_share": round(cash_share, 4),
                "note": "Les mesures du portefeuille actuel sont calculées sur la partie analysée "
                "seulement ; les titres non analysés restent à leur poids déclaré et les écarts "
                "de pondération (illustratifs) ne portent que sur la partie analysée et les liquidités.",
            },
            source="portefeuille déclaré", date=as_of,
            method="declared weights, never rescaled: analysed part, not-analysed part, cash remainder",
            confidence="assumption",
        )

    if lang == "en":
        summary = (
            "Four scenarios built: requested, capped, reference, and current portfolio."
            if current_weights is not None
            else "Three scenarios built: requested, capped, reference."
        )
        if rounds:
            summary += " Revised after objections: " + ("; ".join(changes) or "no changes") + "."
    else:
        summary = (
            "Quatre scénarios construits : demandé, plafonné, référence, et portefeuille actuel."
            if current_weights is not None
            else "Trois scénarios construits : demandé, plafonné, référence."
        )
        if rounds:
            summary += " Révisés après objections : " + ("; ".join(changes) or "aucun changement") + "."
    if gaps:
        summary += (
            " The request could not be fully translated into a portfolio: "
            if lang == "en"
            else " Je n'ai pas pu traduire entièrement votre demande en portefeuille : "
        ) + " ; ".join(gaps) + "."
    from alphaforge.guardrails import check_guardrails

    guardrails = check_guardrails(profile, scenarios, {**state.evidence, **reg.items()})
    return {"scenarios": scenarios, "evidence": reg.items(), "summary": summary, "guardrails": guardrails}
