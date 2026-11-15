"""Guardrail check: every declared limit against every scenario (final report, fix 3).

Contract (orchestrator-owned signature, called at the end of scenarios_node):

    check_guardrails(profile, scenarios, evidence) -> list[dict]

Each entry:
    {
      "limit": "max_loss_12m" | "crypto_target_min" | "sector_cap" | "currency_pref"
               | "crypto_cap" | "single_stock_cap" | "account_eligibility" | "tfsa_room" | ...,
      "label_fr": str, "label_en": str,          # what the limit is, in plain words
      "scenario": "as_requested" | "capped" | "profile_baseline" | "current" | None,
      "declared": float | str | None,            # the user's limit
      "observed": float | str | None,            # the scenario's value
      "status": "ok" | "breach" | "unknown",
      "evidence": [evidence ids],                # ids of the figures compared
      "message_fr": str, "message_en": str,      # one plain sentence, no advice wording
    }
"""

from __future__ import annotations

import csv
from functools import lru_cache

from alphaforge import config
from alphaforge.state import Evidence, Profile, Scenario, effective_risk
from alphaforge.tax import (
    ACCOUNT_LABEL_EN,
    ACCOUNT_LABEL_FR,
    REGISTERED_ACCOUNTS,
    en_money,
    fr_money,
    listed_crypto_vehicles,
    tfsa_room_check,
    tfsa_room_for_band,
    tfsa_room_sentences,
)

EPS = 5e-4  # half of the last printed decimal (0,1 %)
# Reading of the currency answer, stated in the label of the check (assumptions).
MIXED_MAX_US = 0.70  # "mixed CAD/USD": at most 70 % on one side
CAD_MAX_US = 0.50  # "CAD first": at most half outside Canada
# Metric keys that may carry the currency exposure, most precise first.
_US_METRICS = ("usd_exposure", "currency_exposure_usd", "currency_usd", "us_exposure")

VERSION_FR = {
    "as_requested": "la version demandée",
    "capped": "la version ajustée",
    "profile_baseline": "la version de référence du profil",
    "current": "le portefeuille actuel",
}
VERSION_EN = {
    "as_requested": "the version as requested",
    "capped": "the adjusted version",
    "profile_baseline": "the profile reference version",
    "current": "the current portfolio",
}


@lru_cache(maxsize=1)
def _universe() -> dict[str, dict]:
    with open(config.STARTER_DIR / "assets_universe.csv", newline="") as f:
        return {r["ticker"]: r for r in csv.DictReader(f)}


def fr_pct(x: float, decimals: int = 1) -> str:
    """0.26 -> "26,0 %" (French decimal comma, as the evidence prints ratios)."""
    return f"{x * 100:.{decimals}f}".replace(".", ",") + " %"


def en_pct(x: float, decimals: int = 1) -> str:
    return f"{x * 100:.{decimals}f}%"


def _limit_fr(x: float) -> str:
    """A declared limit: "25 %" when whole, "12,5 %" otherwise."""
    return fr_pct(x, 0 if abs(x * 100 - round(x * 100)) < 1e-9 else 1)


def _limit_en(x: float) -> str:
    return en_pct(x, 0 if abs(x * 100 - round(x * 100)) < 1e-9 else 1)


def _number(ev: Evidence | None) -> float | None:
    if ev is None:
        return None
    v = ev.value
    if isinstance(v, dict):
        v = v.get("value")
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _metric(sc: Scenario, evidence: dict[str, Evidence], key: str) -> tuple[float | None, list[str]]:
    eid = sc.metrics.get(key)
    if not eid:
        return None, []
    return _number(evidence.get(eid)), [eid]


def _find_evidence(evidence: dict[str, Evidence], prefix: str, test) -> list[str]:
    def order(eid: str) -> tuple[str, int]:
        digits = "".join(c for c in eid if c.isdigit())
        return eid[:2], int(digits or 0)

    return sorted((k for k, e in evidence.items() if k.startswith(prefix) and test(e)), key=order)


def _caps_evidence(evidence: dict[str, Evidence]) -> list[str]:
    return _find_evidence(
        evidence, "EP", lambda e: isinstance(e.value, dict) and e.value.get("metric") == "caps"
    )[:1]


def crypto_weight(weights: dict[str, float]) -> float:
    u = _universe()
    return float(sum(w for t, w in weights.items() if u.get(t, {}).get("asset_class") == "crypto"))


def sector_weights(weights: dict[str, float]) -> dict[str, float]:
    """Scenario weight per universe sector label (funds keep their own label)."""
    u = _universe()
    out: dict[str, float] = {}
    for t, w in weights.items():
        if w <= 0:
            continue
        sector = u.get(t, {}).get("sector") or "Autre"
        out[sector] = out.get(sector, 0.0) + float(w)
    return out


def profile_crypto_cap(profile: Profile) -> float:
    """Crypto cap of the profile: 0 with `no_crypto`, else the caps table for the risk level."""
    if "no_crypto" in profile.constraints:
        return 0.0
    from alphaforge.nodes.scenarios import CAPS  # lazy: scenarios imports this module

    level = effective_risk(profile.risk_tolerance, profile.risk_capacity)
    return float(CAPS.get(level, CAPS["moderate"])["crypto_total"])


def _entry(limit, label_fr, label_en, scenario, declared, observed, status, evidence, fr, en, **extra):
    return {
        "limit": limit,
        "label_fr": label_fr,
        "label_en": label_en,
        "scenario": scenario,
        "declared": declared,
        "observed": observed,
        "status": status,
        "evidence": list(evidence),
        "message_fr": fr,
        "message_en": en,
        **extra,
    }


def _cap(text: str) -> str:
    return text[0].upper() + text[1:]


def _loss_entries(profile: Profile, sc: Scenario, evidence: dict[str, Evidence]) -> list[dict]:
    limit = profile.max_loss_12m
    v_fr, v_en = VERSION_FR.get(sc.name, sc.name), VERSION_EN.get(sc.name, sc.name)
    out = []
    specs = (
        (
            "stress_2022",
            "En 2022, {v} aurait perdu {obs}",
            "In 2022, {v} would have lost {obs}",
            "En 2022, {v} n'aurait pas perdu de valeur",
            "In 2022, {v} would not have lost value",
        ),
        (
            "max_drawdown",
            "Dans sa pire baisse historique, {v} aurait perdu {obs}",
            "In its worst historical fall, {v} would have lost {obs}",
            "{v} n'a pas connu de baisse historique",
            "{v} has no historical fall",
        ),
    )
    for key, fr_t, en_t, fr_none, en_none in specs:
        value, eids = _metric(sc, evidence, key)
        label_fr = "Perte maximale tolérée sur 12 mois"
        label_en = "Maximum tolerated 12-month loss"
        if value is None:
            out.append(_entry(
                "max_loss_12m", label_fr, label_en, sc.name, limit, None, "unknown", eids,
                _cap(f"{v_fr} : la perte historique n'a pas pu être comparée aux "
                     f"{_limit_fr(limit)} déclarés comme perte maximale tolérée."),
                _cap(f"{v_en}: the historical loss could not be compared with the "
                     f"{_limit_en(limit)} stated as the maximum tolerated loss."),
                metric=key,
            ))
            continue
        loss = max(0.0, -value)
        breach = loss > limit + EPS
        if loss <= 0:
            fr = _cap(fr_none.format(v=v_fr)) + f" ; la perte maximale tolérée déclarée est de {_limit_fr(limit)}."
            en = _cap(en_none.format(v=v_en)) + f"; the stated maximum tolerated loss is {_limit_en(limit)}."
        elif breach:
            fr = (_cap(fr_t.format(v=v_fr, obs=fr_pct(loss)))
                  + f", plus que les {_limit_fr(limit)} déclarés comme perte maximale tolérée.")
            en = (_cap(en_t.format(v=v_en, obs=en_pct(loss)))
                  + f", more than the {_limit_en(limit)} stated as the maximum tolerated loss.")
        else:
            fr = (_cap(fr_t.format(v=v_fr, obs=fr_pct(loss)))
                  + f", sans dépasser les {_limit_fr(limit)} déclarés comme perte maximale tolérée.")
            en = (_cap(en_t.format(v=v_en, obs=en_pct(loss)))
                  + f", within the {_limit_en(limit)} stated as the maximum tolerated loss.")
        out.append(_entry(
            "max_loss_12m", label_fr, label_en, sc.name, limit, round(-loss, 6),
            "breach" if breach else "ok", eids, fr, en, metric=key,
        ))
    return out


def _crypto_entries(profile: Profile, sc: Scenario, evidence: dict[str, Evidence]) -> list[dict]:
    v_fr, v_en = VERSION_FR.get(sc.name, sc.name), VERSION_EN.get(sc.name, sc.name)
    held = crypto_weight(sc.weights)
    caps_eids = _caps_evidence(evidence)
    cap = profile_crypto_cap(profile)
    out = []
    target = profile.crypto_target_min
    if target is not None and target > 0:
        breach = held < target - EPS
        fr = _cap(
            f"{v_fr} contient {fr_pct(held)} de cryptoactifs, "
            + (f"moins que les {_limit_fr(target)} et plus souhaités." if breach
               else f"au moins les {_limit_fr(target)} souhaités.")
        )
        en = _cap(
            f"{v_en} holds {en_pct(held)} in cryptoassets, "
            + (f"less than the {_limit_en(target)} or more that was wished for." if breach
               else f"at least the {_limit_en(target)} wished for.")
        )
        out.append(_entry(
            "crypto_target_min", "Part de cryptoactifs souhaitée (minimum)",
            "Wished cryptoasset share (minimum)", sc.name, target, round(held, 6),
            "breach" if breach else "ok", caps_eids, fr, en,
        ))
    breach = held > cap + EPS
    fr = _cap(
        f"{v_fr} contient {fr_pct(held)} de cryptoactifs, "
        + (f"plus que le plafond de {_limit_fr(cap)} retenu pour ce profil." if breach
           else f"dans le plafond de {_limit_fr(cap)} retenu pour ce profil.")
    )
    en = _cap(
        f"{v_en} holds {en_pct(held)} in cryptoassets, "
        + (f"more than the {_limit_en(cap)} ceiling used for this profile." if breach
           else f"within the {_limit_en(cap)} ceiling used for this profile.")
    )
    out.append(_entry(
        "crypto_cap", "Plafond de cryptoactifs du profil", "Profile cryptoasset ceiling",
        sc.name, cap, round(held, 6), "breach" if breach else "ok", caps_eids, fr, en,
    ))
    return out


def _sector_entry(profile: Profile, sc: Scenario, evidence: dict[str, Evidence]) -> dict:
    v_fr, v_en = VERSION_FR.get(sc.name, sc.name), VERSION_EN.get(sc.name, sc.name)
    cap = profile.sector_cap
    eid = sc.metrics.get("sector_concentration_hhi")
    eids = [eid] if eid else []
    by_sector = sector_weights(sc.weights)
    if not by_sector:
        return _entry(
            "sector_cap", "Part maximale par secteur", "Maximum share per sector", sc.name, cap,
            None, "unknown", eids,
            _cap(f"{v_fr} : la répartition par secteur n'a pas pu être calculée."),
            _cap(f"{v_en}: the sector breakdown could not be computed."),
        )
    sector, top = max(sorted(by_sector.items()), key=lambda kv: kv[1])
    breach = top > cap + EPS
    fr = _cap(
        f"{v_fr} place {fr_pct(top)} dans un même secteur ({sector}), "
        + (f"plus que le maximum de {_limit_fr(cap)} par secteur déclaré." if breach
           else f"sans dépasser le maximum de {_limit_fr(cap)} par secteur déclaré.")
    )
    en = _cap(
        f"{v_en} puts {en_pct(top)} in a single sector ({sector}), "
        + (f"more than the stated maximum of {_limit_en(cap)} per sector." if breach
           else f"within the stated maximum of {_limit_en(cap)} per sector.")
    )
    return _entry(
        "sector_cap", "Part maximale par secteur", "Maximum share per sector", sc.name, cap,
        round(top, 6), "breach" if breach else "ok", eids, fr, en, sector=sector,
    )


def _currency_entry(profile: Profile, sc: Scenario, evidence: dict[str, Evidence]) -> dict | None:
    pref = (profile.currency_pref or "").lower()
    if pref not in ("mixed", "cad"):
        return None
    v_fr, v_en = VERSION_FR.get(sc.name, sc.name), VERSION_EN.get(sc.name, sc.name)
    limit = MIXED_MAX_US if pref == "mixed" else CAD_MAX_US
    if pref == "mixed":
        label_fr = f"Devises : mixte CAD / USD (lu comme au plus {_limit_fr(limit)} d'un même côté)"
        label_en = f"Currencies: mixed CAD / USD (read as at most {_limit_en(limit)} on one side)"
        wish_fr, wish_en = "une répartition mixte entre dollar canadien et dollar américain",             "a mix of Canadian and US dollars"
    else:
        label_fr = f"Devises : priorité au dollar canadien (lu comme au plus {_limit_fr(limit)} hors Canada)"
        label_en = f"Currencies: Canadian dollar first (read as at most {_limit_en(limit)} outside Canada)"
        wish_fr, wish_en = "une priorité au dollar canadien", "a Canadian-dollar priority"
    value, eids = None, []
    for key in _US_METRICS:
        value, eids = _metric(sc, evidence, key)
        if value is not None:
            break
    if value is None:
        return _entry(
            "currency_pref", label_fr, label_en, sc.name, pref, None, "unknown", eids,
            _cap(f"{v_fr} : la part américaine n'a pas pu être comparée à la préférence de devise déclarée."),
            _cap(f"{v_en}: the US share could not be compared with the stated currency preference."),
        )
    breach = value > limit + EPS or (pref == "mixed" and value < 1 - limit - EPS)
    if breach and value > limit:
        fr = _cap(f"{v_fr} place {fr_pct(value)} dans des actifs américains, alors que {wish_fr} est déclarée.")
        en = _cap(f"{v_en} puts {en_pct(value)} in US assets, while {wish_en} is stated.")
    elif breach:
        fr = _cap(f"{v_fr} ne place que {fr_pct(value)} dans des actifs américains, alors que {wish_fr} est déclarée.")
        en = _cap(f"{v_en} puts only {en_pct(value)} in US assets, while {wish_en} is stated.")
    else:
        fr = _cap(f"{v_fr} place {fr_pct(value)} dans des actifs américains, ce qui reste cohérent avec {wish_fr}.")
        en = _cap(f"{v_en} puts {en_pct(value)} in US assets, which is consistent with {wish_en}.")
    return _entry(
        "currency_pref", label_fr, label_en, sc.name, pref, round(value, 6),
        "breach" if breach else "ok", eids, fr, en,
    )


def _single_stock_entry(profile: Profile, sc: Scenario, evidence: dict[str, Evidence]) -> dict | None:
    from alphaforge.nodes.scenarios import CAPS  # lazy: scenarios imports this module

    u = _universe()
    stocks = {t: float(w) for t, w in sc.weights.items() if u.get(t, {}).get("asset_class") == "equity"}
    if not stocks:
        return None
    level = effective_risk(profile.risk_tolerance, profile.risk_capacity)
    cap = float(CAPS.get(level, CAPS["moderate"])["single_stock"])
    ticker, top = max(sorted(stocks.items()), key=lambda kv: kv[1])
    v_fr, v_en = VERSION_FR.get(sc.name, sc.name), VERSION_EN.get(sc.name, sc.name)
    breach = top > cap + EPS
    eids = _caps_evidence(evidence)
    top_eid = sc.metrics.get("top_weight")
    top_value = _number(evidence.get(top_eid)) if top_eid else None
    if top_eid and top_value is not None and abs(top_value - top) < EPS:
        eids = [top_eid, *eids]
    fr = _cap(
        f"{v_fr} place {fr_pct(top)} dans une seule action ({ticker}), "
        + (f"plus que le plafond de {_limit_fr(cap)} par action retenu pour ce profil." if breach
           else f"dans le plafond de {_limit_fr(cap)} par action retenu pour ce profil.")
    )
    en = _cap(
        f"{v_en} puts {en_pct(top)} in a single stock ({ticker}), "
        + (f"more than the {_limit_en(cap)} per-stock ceiling used for this profile." if breach
           else f"within the {_limit_en(cap)} per-stock ceiling used for this profile.")
    )
    return _entry(
        "single_stock_cap", "Plafond par action du profil", "Profile per-stock ceiling", sc.name,
        cap, round(top, 6), "breach" if breach else "ok", eids, fr, en, ticker=ticker,
    )


def _eligibility_entry(profile: Profile, sc: Scenario, evidence: dict[str, Evidence]) -> dict | None:
    account = (profile.account_type or "").lower()
    if account not in REGISTERED_ACCOUNTS:
        return None
    u = _universe()
    # Crypto held or asked for through a listed ETF is analysed through its spot proxy but
    # is a qualified investment (#186, item 2): only the spot part counts.
    vehicles = listed_crypto_vehicles(profile.current_holdings, profile.requested_vehicle)
    crypto = sorted(t for t, w in sc.weights.items() if w > EPS and u.get(t, {}).get("asset_class") == "crypto")
    spot = [t for t in crypto if t not in vehicles]
    via_etf = {t: vehicles[t] for t in crypto if t in vehicles}
    held = sum(float(sc.weights[t]) for t in spot)
    eids = _find_evidence(
        evidence, "ES", lambda e: (e.method or "").startswith("account eligibility")
    )
    acc_fr, acc_en = ACCOUNT_LABEL_FR[account], ACCOUNT_LABEL_EN[account]
    v_fr, v_en = VERSION_FR.get(sc.name, sc.name), VERSION_EN.get(sc.name, sc.name)
    label_fr = f"Placements admissibles dans un {acc_fr}"
    label_en = f"Qualified investments in a {acc_en}"
    if spot:
        fr = _cap(
            f"{v_fr} contient {fr_pct(held)} de cryptoactifs détenus directement "
            f"({', '.join(spot)}), ce qui n'est pas admissible dans un {acc_fr} ; seuls des FNB "
            "de cryptoactifs cotés le sont, et ils sont hors de l'univers analysé."
        )
        en = _cap(
            f"{v_en} holds {en_pct(held)} in directly held cryptoassets ({', '.join(spot)}), "
            f"which is not a qualified investment in a {acc_en}; only listed cryptoasset ETFs "
            "are, and they are outside the analysed universe."
        )
        return _entry("account_eligibility", label_fr, label_en, sc.name, account,
                      round(held, 6), "breach", eids, fr, en, tickers=spot)
    if via_etf:
        etf_share = sum(float(sc.weights[t]) for t in via_etf)
        desc = ", ".join(f"{', '.join(etfs)} → {t}" for t, etfs in sorted(via_etf.items()))
        fr = _cap(
            f"{v_fr} contient {fr_pct(etf_share)} de cryptoactifs via un FNB coté ({desc}), "
            f"placement admissible dans un {acc_fr} ; le FNB est analysé à travers son "
            "sous-jacent (hypothèse). Aucun cryptoactif détenu directement."
        )
        en = _cap(
            f"{v_en} holds {en_pct(etf_share)} in cryptoassets through a listed ETF ({desc}), "
            f"a qualified investment in a {acc_en}; the ETF is analysed through its "
            "underlying (assumption). No directly held cryptoasset."
        )
        return _entry("account_eligibility", label_fr, label_en, sc.name, account, 0.0, "ok",
                      eids, fr, en, via_etf=via_etf)
    fr = _cap(f"{v_fr} ne contient aucun cryptoactif détenu directement, non admissible dans un {acc_fr}.")
    en = _cap(f"{v_en} holds no directly held cryptoasset, which a {acc_en} cannot hold.")
    return _entry("account_eligibility", label_fr, label_en, sc.name, account, 0.0, "ok", eids, fr, en)


def tfsa_room_entry(profile: Profile, evidence: dict[str, Evidence]) -> dict | None:
    """One entry (scenario None) comparing a STATED TFSA budget with the age band's maximum room.

    A budget inferred from the dollar total of the holdings is a balance, which can exceed
    the cumulative room through growth: it is never compared (#186, item 3).
    """
    if (profile.account_type or "").lower() != "tfsa" or not profile.budget_cad:
        return None
    if profile.budget_inferred:
        return None
    room = tfsa_room_for_band(profile.age_band)
    if room is None:
        return None
    eids = _find_evidence(
        evidence, "EK", lambda e: isinstance(e.value, dict) and e.value.get("metric") == "tfsa_room"
    )
    label_fr = "Droits de cotisation CELI cumulés (maximum selon la tranche d'âge)"
    label_en = "Cumulative TFSA room (maximum for the age band)"
    check = tfsa_room_check(profile.account_type, profile.budget_cad, profile.age_band)
    if check:
        fr, en = tfsa_room_sentences(check)
        return _entry("tfsa_room", label_fr, label_en, None, float(room),
                      float(profile.budget_cad), "breach", eids, fr, en)
    fr = (
        f"Le montant déclaré de {fr_money(profile.budget_cad)} ne dépasse pas les droits de "
        f"cotisation CELI cumulés maximaux de {fr_money(room)} pour la tranche d'âge {profile.age_band}."
    )
    en = (
        f"The stated amount of {en_money(profile.budget_cad)} is within the maximum cumulative "
        f"TFSA room of {en_money(room)} for the {profile.age_band} age band."
    )
    return _entry("tfsa_room", label_fr, label_en, None, float(room), float(profile.budget_cad),
                  "ok", eids, fr, en)


def check_guardrails(
    profile: Profile | None,
    scenarios: list[Scenario],
    evidence: dict[str, Evidence],
) -> list[dict]:
    """Every declared limit against every scenario, in a stable order.

    A limit the user did not declare produces no entry; a figure that cannot be read from
    the evidence gives status "unknown" rather than a guess. Never raises on missing data.
    """
    if profile is None:
        return []
    evidence = evidence or {}
    out: list[dict] = []
    room = tfsa_room_entry(profile, evidence)
    if room:
        out.append(room)
    for sc in scenarios or []:
        if profile.max_loss_12m is not None:
            out += _loss_entries(profile, sc, evidence)
        out += _crypto_entries(profile, sc, evidence)
        if profile.sector_cap is not None:
            out.append(_sector_entry(profile, sc, evidence))
        for entry in (
            _currency_entry(profile, sc, evidence),
            _single_stock_entry(profile, sc, evidence),
            _eligibility_entry(profile, sc, evidence),
        ):
            if entry:
                out.append(entry)
    return out
