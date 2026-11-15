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

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from alphaforge.data.provider import get_provider
from alphaforge.evidence import EvidenceRegistry
from alphaforge.nodes.quant import concentration, max_drawdown, stress_2022, volatility
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
DEFAULT_IDEA_WEIGHT = 0.20  # when a judge request names a ticker but no weight
OVERLAP_ETF_SHARE = 0.5  # an ETF cited for overlap keeps half of the ETF cap
CONCENTRATION_SHARE = 0.8  # a line cited for concentration keeps 80 % of its cap
_OVERLAP_RE = re.compile(r"chevauch|overlap|double emploi|détient déjà|deja|déjà")
_DROP_RE = re.compile(r"exclu|controvers|esg|contradi|interdit")
_CONC_RE = re.compile(r"concentr|taux|obligat|secteur|duration|devise|currency|rate|sensib")
SOURCE = "prices_daily.csv + fx_usdcad_daily.csv"
METHODS = {
    "volatility_ann": "annualised std of daily log returns of the scenario rebalanced daily, CAD",
    "max_drawdown": "largest peak-to-trough fall of the scenario value, CAD",
    "stress_2022": "total return of the scenario in CAD over 2022-01-03..2022-12-30",
    "top_weight": "largest single weight in the scenario",
    "sector_concentration_hhi": "Herfindahl index of the weights by universe sector label",
    "us_exposure": "weight in US-listed assets (crypto not counted)",
    "tax_drag": "estimated annual tax drag based on historical dividend/interest yields and account tax rules",
}


# --- caps ---------------------------------------------------------------------------------


def caps_for(profile: Profile, rounds: int = 0) -> dict[str, float]:
    """Profile caps for the lower of tolerance and capacity. `rounds` is kept for callers;
    objections no longer tighten every cap (#116), see `targeted_changes`."""
    return dict(CAPS.get(effective_risk(profile.risk_tolerance, profile.risk_capacity), CAPS["moderate"]))


def _asset_caps(tickers: list[str], info: pd.DataFrame, caps: dict) -> np.ndarray:
    out = []
    for t in tickers:
        cls = info.at[t, "asset_class"]
        if cls == "equity":
            cap = caps["single_stock"]
        elif cls == "crypto":
            cap = caps["crypto_total"]
        else:
            cap = caps["etf"]
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
) -> pd.Series:
    """Long-only weights under the caps (scipy SLSQP). No expected returns anywhere.

    target None: minimum variance. target given: closest portfolio to `target` (least squares).
    fixed: tickers pinned to a weight. If the solver fails, falls back to inverse-volatility
    (risk parity) weights water-filled under the per-asset caps.
    """
    tickers = list(cov.index)
    n = len(tickers)
    fixed = fixed or {}
    ub = _asset_caps(tickers, info, caps)
    lb = np.zeros(n)
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


# --- scenarios ----------------------------------------------------------------------------


def _preference_portfolio(profile: Profile, universe: list[str], info: pd.DataFrame) -> pd.Series:
    sectors = set().union(*(PREFERENCE_SECTORS.get(p, set()) for p in profile.preferences))
    picks = [t for t in universe if info.at[t, "sector"] in sectors] or list(universe)
    return pd.Series(1.0 / len(picks), index=picks)


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
    the requested idea in `capped` stays at the profile cap (#116)."""
    profile_caps = caps_for(profile, rounds)
    caps = {**profile_caps, "per_ticker": dict(per_ticker or {})}
    universe = [t for t in sorted(eligible) if t not in set(drop)] or sorted(eligible)
    cov = prices.pct_change(fill_method=None).dropna().cov().loc[universe, universe]
    baseline = optimize(cov, info, caps)

    idea = profile.requested_idea if profile.request_type == "judge" else None
    ticker = idea.get("ticker") if idea else None
    if ticker in prices.columns:
        w_req = min(max(float(idea.get("weight") or DEFAULT_IDEA_WEIGHT), 0.0), 1.0)
        if current_weights is not None:
            from alphaforge.holdings import build_as_requested_from_current

            as_req_dict = build_as_requested_from_current(current_weights.to_dict(), ticker, w_req)
            as_requested = pd.Series(as_req_dict)
        else:
            rest = baseline.drop(ticker, errors="ignore")
            as_requested = pd.concat([rest / rest.sum() * (1.0 - w_req), pd.Series({ticker: w_req})])
        if ticker in universe:
            w_cap = min(w_req, float(_asset_caps([ticker], info, profile_caps)[0]))
            capped = optimize(cov, info, caps, fixed={ticker: w_cap})
        else:
            capped = baseline.copy()  # excluded by a constraint: capped at zero
    else:
        as_requested = _preference_portfolio(profile, universe, info)
        capped = optimize(cov, info, caps, target=as_requested, equity_floor=False)

    weights = {"as_requested": _clean(as_requested), "capped": capped, "profile_baseline": baseline}
    if current_weights is not None:
        weights["current"] = _clean(current_weights)
    return weights, caps


def scenario_metrics(
    weights: pd.Series,
    prices: pd.DataFrame,
    info: pd.DataFrame,
    *,
    account_type: str = "non_registered",
    as_of: dt.date | None = None,
) -> dict:
    """The fixed metric values (PRD 3.3, Issue #118), computed with quant and tax functions."""
    w = weights.to_dict()
    conc = concentration(w, info)
    stress = stress_2022(prices, w)
    tax_date = as_of or (prices.index[-1].date() if len(prices) else dt.date.today())
    tax_d = scenario_tax_drag(weights, account_type, tax_date, info)
    return {
        "volatility_ann": volatility(prices, w),
        "max_drawdown": max_drawdown(prices, w),
        "stress_2022": stress["return"] if stress else None,
        "top_weight": conc["top_weight"],
        "sector_concentration_hhi": conc["sector_hhi"],
        "us_exposure": conc["us_exposure"],
        "tax_drag": tax_d,
    }


# --- node helpers -------------------------------------------------------------------------


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
    name, weights, values, ids, caps_eid, requested, flagged, account_type: str = "non_registered"
) -> list[str]:
    risk = (
        f"Volatilité annualisée {_pct(values['volatility_ann'])} ({ids['volatility_ann']}), "
        f"perte maximale historique {_pct(values['max_drawdown'])} ({ids['max_drawdown']})."
    )
    if "tax_drag" in ids and values.get("tax_drag") is not None:
        risk += f" Friction fiscale annuelle estimée {_pct(values['tax_drag'])} ({ids['tax_drag']})."
    if name == "as_requested":
        if requested in weights:
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
    return notes


# --- node ---------------------------------------------------------------------------------


@traced("scenarios")
def scenarios_node(state: GraphState) -> dict:
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
    info = provider.asset_info()
    blocking = [o for o in state.objections if o.get("severity") == "blocking"]
    rounds = state.retries.get("red_team", 0) if blocking else 0
    idea = profile.requested_idea if profile.request_type == "judge" else None
    requested = idea.get("ticker") if idea else None
    if requested not in info.index:
        requested = None
    per_ticker, drop, changes = targeted_changes(
        blocking, state.evidence, eligible, info, caps_for(profile), requested
    )
    # Resolve current holdings if provided (#120)
    current_weights: pd.Series | None = None
    proxies_used: dict[str, str] = {}
    not_analysed: list[str] = []
    unanalysed_share = 0.0
    if profile.current_holdings:
        from alphaforge.holdings import resolve_holdings

        mapped_w, proxies_used, not_analysed, unanalysed_share = resolve_holdings(
            profile.current_holdings, set(info.index)
        )
        if mapped_w:
            current_weights = pd.Series(mapped_w)

    current_tickers = set(current_weights.index) if current_weights is not None else set()
    tickers = sorted(set(eligible) | ({requested} if requested else set()) | current_tickers)
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
        reg.add(
            f"Titres non analysés du portefeuille actuel ({_pct(unanalysed_share)}) : {', '.join(sorted(not_analysed))}.",
            source="screening",
            date=as_of,
            method="assets outside the 31-asset universe without proxy excluded from analysis",
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
            k: _r4(v)
            for k, v in scenario_metrics(
                w, prices, info, account_type=profile.account_type, as_of=as_of
            ).items()
        }

    # Pass 1: standard risk metrics (EP2..EP7, EP8..EP13, EP14..EP19)
    base_metrics = [m for m in SCENARIO_METRICS if m != "tax_drag"]
    for name in SCENARIO_NAMES:
        values = all_values[name]
        for m in base_metrics:
            scenario_ids[name][m] = reg.add(
                {"metric": m, "scenario": name, "value": values[m], "unit": "ratio"},
                source=SOURCE,
                date=end,
                method=f"{METHODS[m]}, historical backtest of fictional weights, {window}",
                confidence="fact" if values[m] is not None else "assumption",
            )

    # Pass 2: tax drag metric per scenario (marked as an assumption)
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

    scenarios = []
    for name in SCENARIO_NAMES:
        w = weights[name]
        values = all_values[name]
        ids = scenario_ids[name]
        sc = Scenario(name=name, weights=w.to_dict(), metrics=ids)
        if current_weights is not None:
            from alphaforge.holdings import calculate_trades_and_turnover

            trades, turnover = calculate_trades_and_turnover(
                current_weights.to_dict(), w.to_dict(), profile.budget_cad
            )
            sc.trades = trades
            sc.turnover = turnover
            reg.add(
                {"metric": "turnover", "scenario": name, "value": turnover, "unit": "ratio"},
                source="current holdings vs scenario weights",
                date=end,
                method="0.5 * sum(abs(target_weight - current_weight))",
                confidence="fact",
            )
        notes = _template_notes(
            name, w, values, ids, caps_eid, requested, flagged, account_type=profile.account_type
        )
        if draft_notes is not None:
            try:
                notes = list(draft_notes(sc, evidence_so_far | reg.items())) or notes
            except Exception:
                pass  # the LLM is optional here; templated notes are always valid
        sc.notes = notes
        scenarios.append(sc)

    # Fourth reference column: client's current portfolio (#120)
    if current_weights is not None:
        w_curr = weights["current"]
        values_curr = {
            k: _r4(v)
            for k, v in scenario_metrics(
                w_curr, prices, info, account_type=profile.account_type, as_of=as_of
            ).items()
        }
        ids_curr = {}
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
                    method=f"{METHODS['tax_drag']}, compte {profile.account_type}",
                    confidence="assumption",
                )
            else:
                ids_curr[m] = reg.add(
                    {"metric": m, "scenario": "current", "value": values_curr[m], "unit": "ratio"},
                    source=SOURCE,
                    date=end,
                    method=f"{METHODS[m]}, historical backtest of client's current holdings, {window}",
                    confidence="fact" if values_curr[m] is not None else "assumption",
                )
        notes_curr = [
            f"Portefeuille actuel du client composé de {len(w_curr)} actif(s) analysé(s).",
            f"Volatilité annualisée {_pct(values_curr['volatility_ann'])} ({ids_curr['volatility_ann']}), "
            f"perte maximale historique {_pct(values_curr['max_drawdown'])} ({ids_curr['max_drawdown']}).",
        ]
        if proxies_used:
            notes_curr.append(f"Actifs avec proxy : {', '.join(proxies_used.keys())}.")
        if not_analysed:
            notes_curr.append(
                f"Actifs non analysés ({_pct(unanalysed_share)}) : {', '.join(not_analysed)}."
            )
        sc_curr = Scenario(name="current", weights=w_curr.to_dict(), metrics=ids_curr, notes=notes_curr)
        scenarios.append(sc_curr)

    if current_weights is not None:
        summary = "Quatre scénarios construits : demandé, plafonné, référence, et portefeuille actuel."
    else:
        summary = "Trois scénarios construits : demandé, plafonné, référence."
    if rounds:
        summary += " Révisés après objections : " + ("; ".join(changes) or "aucun changement") + "."
    return {"scenarios": scenarios, "evidence": reg.items(), "summary": summary}
