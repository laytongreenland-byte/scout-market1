#!/usr/bin/env python3
"""StocksDeepDive: optional, public, attribution-preserving research feed.

Separate from Scout's quotes, buy/sell decisions, ML and paper-trade history.
Uses only documented GET endpoints. Never bypasses authentication, fetches user
data, or treats a third-party score as a verified Scout investment signal.
"""
from __future__ import annotations
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "stocksdeepdive.json"
BASE = "https://stocksdeepdive.com/api/v1"
ATTR = "https://stocksdeepdive.com"
MAX_BYTES = 2_000_000
# Parent scans cover more securities; derived sector scans are still useful.
UNIVERSES = (
    "asx-200", "asx-300", "all-ordinaries", "asx-all-technology",
    "asx-small-ordinaries", "asx-a-reits", "asx-financials",
    "asx-materials-mining", "asx-health-care",
    "s-p-500", "nasdaq-100", "russell-2000"
)
MAX_DETAIL = 6
MAX_ROWS = 650
MAX_ERRORS = 15
MAX_TEXT = 180

def timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass
    return None

def asof(now):
    return now.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def text(value, limit=MAX_TEXT):
    return str(value).strip()[:limit] if isinstance(value, (str, int, float)) else ""

def num(value):
    if isinstance(value, bool): return None
    try:
        n = float(value)
        return round(n, 4) if n == n and abs(n) <= 1_000_000_000 else None
    except (ValueError, TypeError, OverflowError): return None

def get(path):
    """Only documented fixed endpoints and bounded ticker variants."""
    if path not in {"/research", "/blog"} and not (
        path.startswith("/scan/") and path[6:] in UNIVERSES
    ) and not re.fullmatch(r"/(?:deep-dive|history)/[A-Z0-9.-]{2,15}", path):
        raise ValueError("Endpoint not permitted")
    url = BASE + path
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "ScoutMarketResearch/1.0 (public read-only market research)"
    })
    with urllib.request.urlopen(req, timeout=12) as response:
        blob = response.read(MAX_BYTES + 1)
    if len(blob) > MAX_BYTES: raise ValueError("Provider response exceeds limit")
    data = json.loads(blob)
    if not isinstance(data, (dict, list)): raise ValueError("Invalid response")
    return data

def entries(value):
    if isinstance(value, list): return value
    if not isinstance(value, dict): return []
    for key in ("results", "rows", "stocks", "items", "rankings", "points", "data",
                "companies", "scan", "tickers"):
        sub = value.get(key)
        if isinstance(sub, list): return sub
        if isinstance(sub, dict):
            nested = entries(sub)
            if nested: return nested
    return []

def quote_ticker(row):
    if not isinstance(row, dict): return None
    ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{1,7}(?:\.AX)?", ticker): return None
    return ticker

def slim_scan(data, universe):
    # Preserve explicitly observed fields; never infer valuation from position.
    output = []
    for row in entries(data)[:MAX_ROWS]:
        ticker = quote_ticker(row)
        if not ticker: continue
        item = {"ticker": ticker, "universe": universe}
        for key in ("name", "company", "company_name", "sector", "industry", "as_of"):
            if row.get(key) is not None: item[key] = text(row[key])
        for key in ("value_score", "quality_score", "psychology_score",
                    "discovery_score", "moat_score", "overall_score",
                    "score", "rank", "price", "market_cap"):
            if row.get(key) is not None:
                n = num(row[key])
                if n is not None: item[key] = n
        output.append(item)
    return output

def slim_index(data):
    out = []
    for row in entries(data)[:150]:
        if not isinstance(row, dict): continue
        item = {k: text(row.get(k)) for k in
                ("ticker", "slug", "company_name", "title", "date", "last_updated")
                if row.get(k) is not None}
        if item: out.append(item)
    return out

def safe_detail(data, ticker):
    if not isinstance(data, dict): return None
    result = {"ticker":ticker, "source":ATTR + "/s/" + ticker}
    for key in ("ticker", "company_name", "name", "as_of", "disclaimer", "attribution", "link"):
        if key in data and data[key] is not None:
            result[key] = text(data[key], 350 if key in ("disclaimer", "attribution") else MAX_TEXT)
    # Aggregate scores only; large/nested provider text stays on linked source.
    for key in ("value_score", "quality_score", "psychology_score",
                "discovery_score", "moat_score", "overall_score", "score"):
        if key in data and num(data[key]) is not None: result[key] = num(data[key])
    return result

def slim_history(data, ticker):
    # History shape is provider-specific. Do not pretend an unknown shape is a price.
    if not isinstance(data, dict): return None
    rows = entries(data)
    prices = []
    for row in rows[-200:]:
        if not isinstance(row, dict): continue
        day = str(row.get("date") or row.get("day") or "")[:10]
        try: datetime.strptime(day, "%Y-%m-%d")
        except ValueError: continue
        close = num(row.get("close"))
        if close is None or close <= 0: continue
        prices.append({"date": day, "close": close})
    return {"ticker":ticker, "currency":text(data.get("currency")),
            "points":prices[-140:], "source":ATTR + "/s/" + ticker} if prices else None

def build(now=None, fetch=None, previous=None):
    now = now or datetime.now(timezone.utc)
    fetch = fetch or get
    if previous is None:
        try: previous = json.loads(OUT.read_text())
        except (OSError, ValueError): previous = {}
    previous = previous if isinstance(previous, dict) else {}
    report = {"schema_version":1, "generated_at":asof(now),
              "provider":"StocksDeepDive", "provider_url":ATTR,
              "attribution":"Research and scores: StocksDeepDive (stocksdeepdive.com)",
              "disclaimer":"Third-party research; not Scout buy/sell advice.",
              "recommendation_influence":False, "quotes_for_trading":False,
              "rate_limit":"60 requests/minute per provider documentation",
              "source_status":{}, "scans":{}, "deep_dives":[],
              "histories":[], "research_index":[], "blog_index":[],
              "errors":[], "observed_as_of":{}, "fresh_source_count":0}
    def try_get(key,path):
        try:
            data = fetch(path)
            if not isinstance(data, (list,dict)): raise ValueError("Invalid JSON shape")
            report["source_status"][key] = "OK"
            report["fresh_source_count"] += 1
            if isinstance(data,dict) and data.get("as_of"):
                report["observed_as_of"][key] = text(data["as_of"])
            return data
        except urllib.error.HTTPError as e:
            report["source_status"][key] = "HTTP_" + str(e.code)
        except (urllib.error.URLError, TimeoutError, OSError):
            report["source_status"][key] = "UNAVAILABLE"
        except (ValueError, TypeError, json.JSONDecodeError):
            report["source_status"][key] = "INVALID_RESPONSE"
        if len(report["errors"]) < MAX_ERRORS:
            report["errors"].append({"source":key,"status":report["source_status"][key]})
        return None

    # Daily small fixed set: no search scraping and no unbounded API loops.
    for universe in UNIVERSES:
        data = try_get("scan/" + universe, "/scan/" + universe)
        if data is not None:
            cleaned = slim_scan(data, universe)
            if cleaned:
                report["scans"][universe] = cleaned
            else:
                report["source_status"]["scan/" + universe] = "UNRECOGNISED_ROWS"

    for key in ("research","blog"):
        data = try_get(key, "/" + key)
        if data is not None: report[key + "_index"] = slim_index(data)

    # Detail/history for a very small ASX sample; no extra login, at most 12 calls.
    chosen = []
    for universe in ("asx-300","asx-200","all-ordinaries"):
        for entry in report["scans"].get(universe, []):
            t = entry["ticker"]
            if not t.endswith(".AX"): t += ".AX"
            if t not in chosen: chosen.append(t)
            if len(chosen)>=MAX_DETAIL: break
        if len(chosen)>=MAX_DETAIL: break
    for ticker in chosen:
        data = try_get("deep-dive/" + ticker, "/deep-dive/" + ticker)
        if data is not None:
            detail = safe_detail(data,ticker)
            if detail: report["deep_dives"].append(detail)
        data = try_get("history/" + ticker, "/history/" + ticker)
        if data is not None:
            history = slim_history(data,ticker)
            if history: report["histories"].append(history)

    # A failed API is never shown as current data; previous snapshot is archived
    # with explicit stale status and excluded from any research signal.
    if not report["scans"] and isinstance(previous.get("scans"),dict) and previous["scans"]:
        report["prior_snapshot"] = {
            "as_of":previous.get("generated_at"),
            "status":"STALE_DO_NOT_USE_FOR_SIGNALS",
            "universe_counts":{k:len(v) for k,v in previous["scans"].items()}}
    report["status"] = ("AVAILABLE" if report["scans"] else
                        "PARTIAL" if report["fresh_source_count"] else "UNAVAILABLE")
    return report

def main():
    if os.environ.get("SCOUT_OFFLINE") == "1":
        print("StocksDeepDive: offline mode, not refreshing")
        return 0
    old = {}
    try: old = json.loads(OUT.read_text())
    except (OSError,ValueError): pass
    if old and timestamp(old.get("generated_at")):
        age = datetime.now(timezone.utc) - timestamp(old["generated_at"])
        if timedelta(0) <= age < timedelta(hours=20) and os.environ.get("SCOUT_SDD_FORCE")!="1":
            print("StocksDeepDive: recent provider check retained")
            return 0
    report = build(previous=old)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,separators=(",",":"))+"\n")
    print("StocksDeepDive:",report["status"],"usable universes",list(report["scans"]),
          "endpoint errors",report["errors"][:5])
    return 0

if __name__=="__main__":
    raise SystemExit(main())
