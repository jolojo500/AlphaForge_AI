"""Build full ETF holdings caches for ESGV and QQQ from public sources.

Sources:
- Vanguard ESGV: Vanguard public portfolio-holding API endpoint (1,206 holdings as of 2026-09-30).
- Invesco QQQ: SEC EDGAR Form NPORT-P filings (CIK 0001067839) with OpenFIGI CUSIP resolution.

Saves both flat (<ETF>.json) and dated snapshot (<ETF>/<DATE>.json) structures.
"""

from __future__ import annotations

import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOLDINGS_DIR = ROOT / "data" / "cache" / "holdings"

SEC_HEADERS = {"User-Agent": "AlphaForgeAI research@polyfinances.ca"}
BROWSER_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

QQQ_OVERRIDES = {
    "G25839104": ("CCEP", "Coca-Cola Europacific Partners PLC"),
    "G7997R103": ("STX", "Seagate Technology Holdings PLC"),
    "N6596X109": ("NXPI", "NXP Semiconductors N.V."),
    "G54950103": ("LIN", "Linde PLC"),
    "N97284108": ("NBIS", "Nebius Group N.V."),
    "N07059210": ("ASML", "ASML Holding N.V."),
    "G34503107": ("FER", "Ferrovial SE"),
}


def build_esgv() -> dict:
    url = "https://investor.vanguard.com/vmf/api/ESGV/portfolio-holding/stock.json?start=1&count=4000"
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        vg_data = json.loads(resp.read().decode("utf-8"))

    entities = vg_data.get("fund", {}).get("entity", [])
    as_of = vg_data.get("asOfDate", "2026-09-30")[:10]
    total_mv = sum(float(e.get("marketValue", 0)) for e in entities)

    holdings = []
    for e in entities:
        t = e.get("ticker")
        name = e.get("longName") or e.get("shortName")
        mv = float(e.get("marketValue", 0))
        if t and mv > 0:
            w = round(mv / total_mv, 6)
            holdings.append({"ticker": t, "name": name, "weight": w})

    holdings.sort(key=lambda x: x["weight"], reverse=True)
    cov = round(sum(h["weight"] for h in holdings), 4)

    return {
        "ticker": "ESGV",
        "as_of": as_of,
        "source_url": "https://investor.vanguard.com/investment-products/etfs/profile/esgv",
        "source_name": "Vanguard, Vanguard ESG U.S. Stock ETF portfolio holdings API",
        "retrieved_at": "2026-11-15",
        "complete": True,
        "total_holdings": len(holdings),
        "coverage_weight": cov,
        "holdings": holdings,
    }


def parse_qqq_nport(xml_url: str, as_of: str) -> dict:
    req = urllib.request.Request(xml_url, headers=SEC_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        tree = ET.fromstring(resp.read())

    for elem in tree.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]

    holdings_elems = tree.findall(".//invstOrSec")
    total_val = sum(float(h.findtext("valUSD", "0")) for h in holdings_elems)

    reqs, valid_elems = [], []
    for h in holdings_elems:
        name = h.findtext("name", "")
        cusip = h.findtext("cusip", "")
        if any(cash in name for cash in ("Private Government", "Private Prime", "N/A")):
            continue
        if cusip in QQQ_OVERRIDES:
            reqs.append(None)
        else:
            reqs.append({"idType": "ID_CUSIP", "idValue": cusip})
        valid_elems.append(h)

    figi_results = []
    to_query = [r for r in reqs if r is not None]
    for i in range(0, len(to_query), 10):
        chunk = to_query[i:i + 10]
        figi_req = urllib.request.Request(
            "https://api.openfigi.com/v3/mapping",
            data=json.dumps(chunk).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(figi_req, timeout=15) as resp:
            figi_results.extend(json.loads(resp.read().decode("utf-8")))
        time.sleep(0.3)

    q_idx = 0
    holdings = []
    for _r, h in zip(reqs, valid_elems, strict=True):
        name = h.findtext("name", "")
        cusip = h.findtext("cusip", "")
        val = float(h.findtext("valUSD", "0"))
        if cusip in QQQ_OVERRIDES:
            ticker = QQQ_OVERRIDES[cusip][0]
        else:
            res = figi_results[q_idx]
            q_idx += 1
            ticker = None
            if "data" in res:
                for d in res["data"]:
                    if d.get("exchCode") in ("US", "UN", "UQ", "UA", "UW", "UR"):
                        ticker = d.get("ticker")
                        break
                if not ticker:
                    ticker = res["data"][0].get("ticker")
        if ticker and val > 0:
            holdings.append({
                "ticker": ticker,
                "name": name,
                "weight": round(val / total_val, 6),
            })

    holdings.sort(key=lambda x: x["weight"], reverse=True)
    cov = round(sum(h["weight"] for h in holdings), 4)

    return {
        "ticker": "QQQ",
        "as_of": as_of,
        "source_url": xml_url,
        "source_name": f"SEC EDGAR, Invesco QQQ Trust Form NPORT-P ({as_of})",
        "retrieved_at": "2026-11-15",
        "complete": True,
        "total_holdings": len(holdings),
        "coverage_weight": cov,
        "holdings": holdings,
    }


def main():
    HOLDINGS_DIR.mkdir(parents=True, exist_ok=True)
    (HOLDINGS_DIR / "ESGV").mkdir(exist_ok=True)
    (HOLDINGS_DIR / "QQQ").mkdir(exist_ok=True)

    print("Building ESGV holdings from Vanguard API...")
    esgv = build_esgv()
    esgv_date = esgv["as_of"]
    (HOLDINGS_DIR / "ESGV" / f"{esgv_date}.json").write_text(json.dumps(esgv, indent=2), encoding="utf-8")
    (HOLDINGS_DIR / "ESGV.json").write_text(json.dumps(esgv, indent=2), encoding="utf-8")
    print(f"  ESGV saved: {len(esgv['holdings'])} holdings (as of {esgv_date})")

    print("Building QQQ holdings from SEC EDGAR (2026-06-30)...")
    qqq_2026_06 = parse_qqq_nport(
        "https://www.sec.gov/Archives/edgar/data/1067839/000106783926000030/primary_doc.xml",
        "2026-06-30",
    )
    (HOLDINGS_DIR / "QQQ" / "2026-06-30.json").write_text(json.dumps(qqq_2026_06, indent=2), encoding="utf-8")
    (HOLDINGS_DIR / "QQQ.json").write_text(json.dumps(qqq_2026_06, indent=2), encoding="utf-8")
    print(f"  QQQ 2026-06-30 saved: {len(qqq_2026_06['holdings'])} holdings")

    print("Building QQQ holdings from SEC EDGAR (2026-03-31)...")
    qqq_2026_03 = parse_qqq_nport(
        "https://www.sec.gov/Archives/edgar/data/1067839/000106783926000024/primary_doc.xml",
        "2026-03-31",
    )
    (HOLDINGS_DIR / "QQQ" / "2026-03-31.json").write_text(json.dumps(qqq_2026_03, indent=2), encoding="utf-8")
    print(f"  QQQ 2026-03-31 saved: {len(qqq_2026_03['holdings'])} holdings")

    print("Done building ETF holdings!")


if __name__ == "__main__":
    main()
