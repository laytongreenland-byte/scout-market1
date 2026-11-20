#!/usr/bin/env python3
"""Scout: public, best-effort research-feed collection; does NOT issue trade advice."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from research import generate_research

ROOT = Path(__file__).parent
DATA = ROOT / 'data' / 'latest.json'
CONFIG = ROOT / 'config' / 'watchlist.json'
CACHE = ROOT / 'data' / 'research_cache.json'
HISTORY = ROOT / 'data' / 'history.json'
WEEKLY = ROOT / 'data' / 'weekly.json'
MODEL = ROOT / 'data' / 'ml_model.json'
LEARNING = ROOT / 'data' / 'ml_report.json'
LAST_FINNHUB_CALL = None
UTC = timezone.utc
NOW = datetime.now(UTC)
NZX_FEED = 'https://nzxplorer.co.nz/rss/announcements'
FED_FEED = 'https://www.federalreserve.gov/feeds/press_all.xml'


def stamp(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z') if dt else None


def parse_date(raw: str | None, default_timezone=UTC) -> datetime | None:
    if not raw:
        return None
    try:
        d = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        try:
            d = parsedate_to_datetime(raw)
        except (ValueError, TypeError, IndexError):
            return None
    return d.replace(tzinfo=default_timezone).astimezone(UTC) if d.tzinfo is None else d.astimezone(UTC)


def fetch(url: str, *, sec=False) -> bytes:
    if os.environ.get('SCOUT_OFFLINE') == '1':
        raise RuntimeError('Offline test mode: network disabled')
    raw_ua = os.environ.get('SEC_USER_AGENT', '').strip() if sec else ''
    ua = ''
    if sec:
        # Rebuild a standards-safe User-Agent from the private contact address.
        # Pasted rich text can contain invalid control/unicode characters that
        # Python's HTTP client rejects. Never print or publish the email.
        match = re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}', raw_ua)
        if not match:
            raise RuntimeError('SEC_USER_AGENT requires a plain-text contact email')
        ua = 'ScoutMarketResearch/1.0 (' + match.group(0) + ')'
    # Free Finnhub access: pace all endpoint requests across the hourly scan.
    global LAST_FINNHUB_CALL
    if urllib.parse.urlsplit(url).hostname == 'finnhub.io':
        current = time.monotonic()
        if LAST_FINNHUB_CALL is not None:
            time.sleep(max(0.0, 1.1 - (current-LAST_FINNHUB_CALL)))
        LAST_FINNHUB_CALL = time.monotonic()
    req = urllib.request.Request(url, headers={
        'User-Agent': ua if sec else 'ScoutMarketResearch/1.0 (personal non-commercial research)',
        'Accept': 'application/json, application/atom+xml, application/rss+xml, */*',
    })
    with urllib.request.urlopen(req, timeout=22) as r:
        return r.read(4_000_000)


def feed_items(data: bytes) -> list[dict]:
    """Read common RSS 2 and Atom forms, failing rather than inventing dates."""
    root = ET.fromstring(data)
    items = []
    def child_text(node, wanted):
        for child in node:
            if child.tag.split('}')[-1].lower() in wanted and child.text:
                return child.text.strip()
        return ''
    for node in root.iter():
        if node.tag.split('}')[-1].lower() not in ('item', 'entry'):
            continue
        title = child_text(node, {'title'})
        if not title:
            continue
        link = child_text(node, {'link'})
        if not link:
            for c in node:
                if c.tag.split('}')[-1].lower() == 'link' and (c.attrib.get('rel', 'alternate') == 'alternate'):
                    link = c.attrib.get('href', '')
                    if link:
                        break
        date = child_text(node, {'pubdate', 'published', 'updated', 'date'})
        items.append({'title': title, 'url': link, 'published_at': stamp(parse_date(date))})
    return items


def make_id(kind: str, title: str, url: str) -> str:
    return hashlib.sha256((kind + '|' + url + '|' + title).encode('utf-8')).hexdigest()[:20]


def verified_url(url: str) -> bool:
    try:
        p = urllib.parse.urlsplit(url)
        return p.scheme == 'https' and bool(p.hostname)
    except ValueError:
        return False


def primary_site(url: str) -> bool:
    if not verified_url(url):
        return False
    host = (urllib.parse.urlsplit(url).hostname or '').lower()
    return host == 'sec.gov' or host.endswith('.sec.gov') or host == 'nzx.com' or host.endswith('.nzx.com') or host == 'federalreserve.gov' or host.endswith('.federalreserve.gov')


def sentiment(title: str) -> str:
    t = title.lower()
    if any(x in t for x in ('profit warning', 'guidance lowered', 'guidance cut', 'earnings downgrade', 'downgraded guidance', 'trading halt', 'insolvency', 'receivership', 'investigation', 'going concern')):
        return 'negative'
    if any(x in t for x in ('guidance raised', 'guidance upgraded', 'earnings upgrade', 'raised outlook', 'profit upgrade', 'record profit', 'contract awarded', 'material contract award')):
        return 'positive'
    return 'neutral'


def fetch_rss(url: str, name: str, type_: str, max_count=60):
    result = []
    for i in feed_items(fetch(url))[:max_count]:
        if not verified_url(i['url']):
            continue
        tick = None
        if type_ == 'NZX':
            # Only identify a symbol when clearly stated in the feed title.
            m = re.match(r'^([A-Z]{3,5})(?:\s*[:\-|])', i['title'])
            if m:
                tick = m.group(1)
        result.append({
            'id': make_id(type_, i['title'], i['url']), 'type': type_, 'ticker': tick,
            'title': i['title'], 'published_at': i['published_at'], 'url': i['url'],
            'source': name, 'primary': primary_site(i['url']), 'sentiment': sentiment(i['title'])
        })
    return result


def sec_submissions(symbol: str, cik: str) -> list[dict]:
    # Distinguish a rejected HTTP request from a non-JSON SEC response.
    # Never echo the configured private User-Agent in errors or public data.
    try:
        response = fetch(f'https://data.sec.gov/submissions/CIK{cik}.json', sec=True)
    except ValueError:
        raise RuntimeError('SEC HTTP request rejected; check User-Agent formatting') from None
    try:
        data = json.loads(response)
    except (ValueError, UnicodeError):
        raise RuntimeError('SEC endpoint returned invalid JSON') from None
    recent = data.get('filings', {}).get('recent', {})
    count = min(25, len(recent.get('accessionNumber', [])))
    oldest = NOW - timedelta(days=10)
    out = []
    forms = {'8-K', '10-Q', '10-K', '6-K', '20-F', 'S-1', '424B5'}
    for i in range(count):
        form = recent.get('form', [''] * count)[i]
        if form not in forms:
            continue
        accepted = (recent.get('acceptanceDateTime') or [None] * count)[i]
        filed = (recent.get('filingDate') or [None] * count)[i]
        date = parse_date(accepted, ZoneInfo('America/New_York')) or parse_date(filed)
        if date and date < oldest:
            continue
        accession = recent['accessionNumber'][i]
        primary = (recent.get('primaryDocument') or [''] * count)[i]
        if not primary:
            continue
        accession_no_dash = accession.replace('-', '')
        url = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_no_dash}/{urllib.parse.quote(primary)}'
        title = f'{symbol}: {form} filed with the SEC'
        out.append({'id': make_id('SEC', accession, url), 'type': 'SEC', 'ticker': symbol,
                    'title': title, 'url': url, 'source': 'SEC EDGAR', 'primary': True,
                    'published_at': stamp(date), 'sentiment': 'neutral', 'form': form})
    return out


def prices(symbols: list[str], api_key: str, previous_quotes: list[dict]) -> tuple[list[dict], int, list[str]]:
    old = {q.get('symbol'): q for q in previous_quotes}
    quotes, successes, errors = [], 0, []
    for sym in symbols:
        if not api_key:
            quotes.append({'symbol': sym, 'price': None, 'source': 'Finnhub', 'currency': 'USD'})
            continue
        try:
            url = 'https://finnhub.io/api/v1/quote?' + urllib.parse.urlencode({'symbol': sym, 'token': api_key})
            obj = json.loads(fetch(url))
            val = obj.get('c')
            pc = obj.get('pc')
            if not isinstance(val, (int, float)) or val <= 0:
                raise ValueError('No valid current price returned')
            # Finnhub t is the quote provider timestamp; never replace it with the scan time.
            epoch = obj.get('t')
            asof_dt = datetime.fromtimestamp(epoch, UTC) if isinstance(epoch, (int, float)) and epoch > 0 else None
            if not asof_dt or asof_dt>NOW+timedelta(minutes=10) or asof_dt<NOW-timedelta(hours=75):
                raise ValueError('Missing, stale or future-dated quote timestamp')
            asof=stamp(asof_dt)
            quotes.append({'symbol': sym, 'price': val, 'previous_close': pc if isinstance(pc, (int, float)) and pc > 0 else None,
                           'change_pct': round((val/pc - 1)*100, 3) if isinstance(pc, (int, float)) and pc > 0 else None,
                           'price_at': asof, 'source': 'Finnhub', 'currency': 'USD'})
            successes += 1
        except Exception as e:
            errors.append(f'{sym}: {type(e).__name__}')
            q = old.get(sym)
            if q and q.get('price'):
                q = dict(q)
                q['stale'] = True
                quotes.append(q)
            else:
                quotes.append({'symbol': sym, 'price': None, 'source': 'Finnhub', 'currency': 'USD'})
        time.sleep(.15)
    return quotes, successes, errors


def priority_events(events: list[dict]) -> list[dict]:
    """Conservative watch triggers, never a BUY recommendation."""
    out = []
    for e in events:
        date = parse_date(e.get('published_at'))
        if e.get('sentiment') != 'positive' or not e.get('primary') or not date or NOW-date > timedelta(hours=48):
            continue
        if not e.get('ticker'):
            continue
        obj = dict(e)
        obj['reason'] = 'A primary announcement appears material. Check financial statements, current valuation, market reaction, liquidity and downside before considering any trade.'
        out.append(obj)
    return out[:10]


def main() -> None:
    config = json.loads(CONFIG.read_text())
    previous = json.loads(DATA.read_text()) if DATA.exists() else {}
    # Bounded, verified watch universe; avoid silently ignoring most configured symbols.
    symbols = list(dict.fromkeys(config.get('us_symbols', [])))[:340]
    etfs = [s for s in config.get('etf_symbols', []) if s in symbols]
    sources, events = [], []
    def source(name, ok, count, error=''):
        sources.append({'name': name, 'ok': ok, 'count': count, 'checked_at': stamp(NOW), 'error': error})

    for name, url, type_ in [('NZX announcements (NZXplorer RSS)', NZX_FEED, 'NZX'),
                              ('Federal Reserve press releases', FED_FEED, 'MACRO')]:
        if type_ == 'NZX' and not config.get('nz_announcements', True):
            continue
        if type_ == 'MACRO' and not config.get('fed_announcements', True):
            continue
        try:
            results = fetch_rss(url, name, type_)
            events.extend(results)
            source(name, True, len(results))
        except Exception as e:
            source(name, False, 0, f'{type(e).__name__}: {str(e)[:110]}')

    sec_successes, sec_errors = 0, []
    agent=os.environ.get('SEC_USER_AGENT','').strip()
    if not agent or '@' not in agent:
        source('SEC EDGAR company submissions',False,0,
               'Not configured: SEC requires a descriptive application + contact email in the private SEC_USER_AGENT GitHub secret')
    else:
        for symbol, cik in config.get('sec_ciks', {}).items():
            try:
                results = sec_submissions(symbol, cik)
                events.extend(results)
                sec_successes += 1
            except Exception as e:
                # Only publish allowlisted diagnostics, never untrusted text or secrets.
                if isinstance(e, urllib.error.HTTPError):
                    reason = f'SEC HTTP {e.code}'
                elif isinstance(e, RuntimeError) and str(e) in (
                    'SEC HTTP request rejected; check User-Agent formatting',
                    'SEC endpoint returned invalid JSON',
                ):
                    reason = str(e)
                else:
                    reason = type(e).__name__
                sec_errors.append(f'{symbol}: {reason}')
            time.sleep(.28)
        source('SEC EDGAR company submissions', sec_successes > 0, sec_successes,
               f'{len(sec_errors)} unavailable: '+', '.join(sec_errors[:5]) if sec_errors else '')

    key = os.environ.get('FINNHUB_API_KEY', '').strip()
    quote_results, good_quotes, price_errors = prices(symbols, key, previous.get('quotes', []))
    source('Finnhub US share quotes', good_quotes > 0, good_quotes,
           'FINNHUB_API_KEY not configured' if not key else ', '.join(price_errors[:6]))

    # Retain recent, previously verified headlines across intermittent provider failures.
    old_events = previous.get('events', [])
    unique = {}
    for e in old_events + events:
        dt = parse_date(e.get('published_at'))
        if dt and NOW - dt > timedelta(days=10):
            continue
        if not verified_url(e.get('url') or ''):
            continue
        unique[e['id']] = e
    fresh = sorted(unique.values(), key=lambda e: e.get('published_at') or '', reverse=True)[:120]
    # Explainable opportunity research, rotation-limited to preserve free API limits.
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    history = json.loads(HISTORY.read_text()) if HISTORY.exists() else {}
    prior_weekly = json.loads(WEEKLY.read_text()) if WEEKLY.exists() else {}
    ml_model = json.loads(MODEL.read_text()) if MODEL.exists() else {}
    ml_report = json.loads(LEARNING.read_text()) if LEARNING.exists() else {}
    research, new_cache, new_history, new_weekly, problems = generate_research(
        symbols, quote_results, fresh, cache, history, prior_weekly,
        key, fetch, verified_url, NOW, ml_model, ml_report, etf_symbols=etfs)
    research['learning'] = dict(ml_report, recorded_signals=len(new_history.get('episodes', [])),
                                 observed_weeks=len({v.get('week') for v in new_history.get('episodes', [])}))
    source('Finnhub fundamentals and issuer news',
           research['updated_company_metrics_this_scan'] > 0,
           research['updated_company_metrics_this_scan'],
           ', '.join(problems[:4]))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(new_cache, ensure_ascii=False, indent=2)+'\n')
    HISTORY.write_text(json.dumps(new_history, ensure_ascii=False, indent=2)+'\n')
    WEEKLY.write_text(json.dumps(new_weekly, ensure_ascii=False, indent=2)+'\n')
    success_count = sum(bool(s['ok']) for s in sources)
    state = 'ok' if success_count == len(sources) else 'partial' if success_count else 'unavailable'
    data = {
        'generated_at': stamp(NOW), 'status': state,
        'coverage': {
            'configured_symbols':len(symbols), 'equity_symbols':len(symbols)-len(etfs),
            'etf_symbols':len(etfs), 'quotes_fresh_this_scan':good_quotes,
            'quotes_unavailable_or_unverified':len(symbols)-good_quotes,
            'financially_screened':research.get('screened_with_financials',0),
            'universe_note':config.get('universe_description','Curated sample, not the full market'),
            'nzx_prices_available':False,
        },
        'sources': sources, 'tracked_symbols': symbols,
        'quotes': quote_results, 'etf_symbols':etfs, 'events': fresh, 'research': research,
        'priorities': priority_events(fresh),
        'warnings': [
            'This scanner is best effort and does not monitor every market or source.',
            'Machine learning rankings remain disabled until sufficient real forward validation exists. No profit forecasts or trade recommendations.',
            'Prices are not NZD and may be delayed or unavailable. NZX prices are not currently supplied.',
        ],
    }
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print(f'[{stamp(NOW)}] sources {success_count}/{len(sources)}; headlines {len(fresh)}; prices {good_quotes}/{len(symbols)}; research triggers {len(data["priorities"])}')
    for s in sources:
        print(f'  {s["name"]}: {"OK" if s["ok"] else "FAIL"} ({s["count"]}) {s["error"]}')
    # An unavailable scanner does NOT silently count as a completed success.
    if success_count == 0:
        print('WARNING: all sources unavailable; dashboard explicitly reports the failure.', file=sys.stderr)

if __name__ == '__main__':
    main()
