#!/usr/bin/env python3
"""Small, source-attributed NZX company research feed for educational paper trades.

Fetches only a bounded daily sample of company metrics from the user's authorised
API key. No machine learning, trading execution or access to US research history.
Company financial values are not interpreted as if fetched_at is a filing date.
"""
from __future__ import annotations
import json, math, os, re, urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from apac_data import NZX_ROOT, request

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'data'/'nzx_fundamentals.json'
CATALOG=ROOT/'data'/'market_catalog.json'
APAC=ROOT/'data'/'apac.json'
NZ=ZoneInfo('Pacific/Auckland')
FIELDS={'valuation':('pe_ratio',), 'live_valuation':('pe_ratio','price_52w_high','price_52w_low'),
        'profitability':('roe','net_margin'),
        'leverage':('debt_to_equity',), 'growth':('revenue_growth',),
        'price_performance':('price_52w_high','price_52w_low')}

def number(v):
    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):
        return None
    return float(v)

def unpack(record, sym, now):
    data=record.get('data',record) if isinstance(record,dict) else {}
    if not isinstance(data,dict):return None
    ticker=str(data.get('ticker','')).upper()
    if ticker!=sym:return None
    yr=data.get('fiscal_year')
    try: year=int(yr)
    except (ValueError,TypeError):year=None
    # The accounting period must be known, not just the API retrieval time.
    period=str(data.get('period_type') or '').upper()[:16]
    sector=str(data.get('sector') or '')[:75]
    entries={}
    for group,names in FIELDS.items():
        row=data.get(group)
        if not isinstance(row,dict):continue
        for key in names:
            v=number(row.get(key))
            if v is not None and key not in entries:
                entries[key]=v
    v=entries.get('pe_ratio')
    if v is not None and not 0<v<200:entries.pop('pe_ratio',None)
    for key in ('roe','net_margin','revenue_growth'):
        v=entries.get(key)
        if v is not None and not -200<v<200:entries.pop(key,None)
    de=entries.get('debt_to_equity')
    if de is not None and not 0<=de<100:entries.pop('debt_to_equity',None)
    lo=entries.get('price_52w_low')
    hi=entries.get('price_52w_high')
    if lo is not None and hi is not None and (lo<=0 or hi<lo):
        entries.pop('price_52w_low',None);entries.pop('price_52w_high',None)
    # Provider ratios may be fractions or percentages. Ambiguous ratios cannot
    # be used for automatic paper-trade quality gates until unit is documented.
    return {'symbol':sym,'market':'NZX','source':'NZXplorer',
            'source_url':'https://nzxplorer.co.nz/companies/'+sym.lower(),
            'primary_filing_url':'https://www.nzx.com/instruments/'+sym,
            'retrieved_at':now.astimezone(timezone.utc).isoformat().replace('+00:00','Z'),
            'fiscal_year':year,'period_type':period,'sector':sector,
            'metrics':entries, 'ratio_units_verified':False,
            'quality':'METRICS_UNVERIFIED_UNITS'}

def build(previous,catalog,apac,fetcher=None,now=None,limit=4,key=None,filing_fetcher=None):
    from nzx_filings import fetch_for, parse as parse_filings
    now=now or datetime.now(timezone.utc)
    today=now.astimezone(NZ).date()
    previous=previous if isinstance(previous,dict) else {}
    items={x.get('symbol'):x for x in catalog.get('items',[])
           if isinstance(x,dict) and x.get('market')=='NZX' and x.get('type')!='ETF'}
    tickers=sorted({q.get('symbol') for q in apac.get('quotes',[]) if
                    isinstance(q,dict) and q.get('market')=='NZX' and
                    q.get('currency')=='NZD' and q.get('symbol') in items})
    stored={k:v for k,v in previous.get('companies',{}).items()
            if k in items and isinstance(v,dict)}
    status={'attempted':0,'valid_this_scan':0,'available':len(stored),
            'filing_requests':0,'filings_with_official_links':0,
            'status':'NO_KEY' if not key else 'NO_PRICED_COMPANIES' if not tickers else 'OK',
            'errors':[]}
    fetched_day=previous.get('fetched_day')
    filings_day=previous.get('filings_checked_day')
    if not key or not tickers:
        return {'generated_at':now.isoformat(),'companies':stored,
                'fetched_day':fetched_day,'filings_checked_day':filings_day,
                'status':status}
    fetcher=fetcher or (lambda sym,k:request(NZX_ROOT+'metrics/'+sym,k))
    filing_fetcher=filing_fetcher or fetch_for
    def age(item):
        try:return datetime.fromisoformat(item.get('retrieved_at','').replace('Z','+00:00'))
        except (ValueError,TypeError):return datetime(1970,1,1,tzinfo=timezone.utc)
    if fetched_day!=today.isoformat():
        queue=sorted(tickers,key=lambda sym:age(stored.get(sym,{})))
        for sym in queue[:max(0,min(limit,8))]:
            status['attempted']+=1
            try:
                record=unpack(fetcher(sym,key),sym,now)
                if record and record['metrics']:
                    # Preserve separately verified primary issuer links.
                    record['announcements']=stored.get(sym,{}).get('announcements',[])
                    stored[sym]=record
                    status['valid_this_scan']+=1
                else:status['errors'].append(sym+': INVALID_METRICS')
            except urllib.error.HTTPError as ex:
                status['errors'].append(sym+': HTTP_'+str(ex.code))
                if ex.code in (401,403,429):break
            except Exception:status['errors'].append(sym+': PROVIDER_ERROR')
        if status['attempted']:fetched_day=today.isoformat()
    if filings_day!=today.isoformat() and stored:
        # Only lookup issuers already screened. This is NOT a bulk feed.
        queue=sorted(stored,key=lambda sym:(bool(stored[sym].get('announcements')),
                                           age(stored[sym])))
        for sym in queue[:min(4,max(0,limit))]:
            status['filing_requests']+=1
            try:
                meta=parse_filings(filing_fetcher(sym,key),today)
                if meta:
                    stored[sym]['announcements']=meta
                    status['filings_with_official_links']+=1
                else:status['errors'].append(sym+': NO_OFFICIAL_FILING_LINK')
            except urllib.error.HTTPError as ex:
                status['errors'].append(sym+': FILING_HTTP_'+str(ex.code))
                if ex.code in (401,403,429):break
            except Exception:status['errors'].append(sym+': FILINGS_UNAVAILABLE')
        if status['filing_requests']:filings_day=today.isoformat()
    status['available']=len(stored)
    status['status']=('OK' if status['valid_this_scan'] or
                     status['filings_with_official_links'] else
                     'ALREADY_CHECKED' if not status['attempted'] and not status['filing_requests'] else
                     'PARTIAL' if stored else 'PROVIDER_ERROR')
    return {'generated_at':now.isoformat(),'companies':stored,
            'fetched_day':fetched_day,'filings_checked_day':filings_day,
            'status':status}

def main():
    if os.environ.get('SCOUT_OFFLINE')=='1':return
    def read(p):
        try:return json.loads(p.read_text())
        except (OSError,ValueError):return {}
    result=build(read(OUT),read(CATALOG),read(APAC),
                 key=os.environ.get('NZXPLORER_API_KEY',''),
                 limit=int(os.environ.get('SCOUT_NZX_FINANCIAL_DAILY_LIMIT','4')))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result,indent=2)+'\n')
    print('NZX financial research: ',result['status'])

if __name__=='__main__':main()
