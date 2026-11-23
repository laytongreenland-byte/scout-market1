#!/usr/bin/env python3
"""NZX research integrated with Scout's UI, isolated from US research and ML.

No backfilled recommendations, guessed fair value, NZX-vs-SPY comparisons, or
machine learning using NZXplorer-derived data. Price observations are EOD NZD.
This module never opens trades or updates US history, cache, scoring or model.
"""
from __future__ import annotations

import json
import re
from nzx_paper import score_financials, plan, new_calls, settle, summary as paper_summary
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
CATALOG=ROOT/'data'/'market_catalog.json'
APAC=ROOT/'data'/'apac.json'
LATEST=ROOT/'data'/'latest.json'
HISTORY=ROOT/'data'/'nzx_history.json'
OUT=ROOT/'data'/'nzx_research.json'
NZ=ZoneInfo('Pacific/Auckland')
MAX_HISTORY=20000

def read(path):
    try:
        data=json.loads(path.read_text())
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):
        return {}

def stamp(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')

def parse_date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError,ValueError):
        return None

def time_value(value):
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return d if d.tzinfo else None
    except (ValueError,TypeError):
        return None

def valid_quote(row,today):
    if not isinstance(row,dict) or row.get('market')!='NZX' or row.get('currency')!='NZD':
        return False
    if row.get('price_type')!='EOD' or row.get('research_only') is not True:
        return False
    d=parse_date(row.get('date'))
    px=row.get('close')
    return bool(d and 0<=(today-d).days<=7 and isinstance(px,(float,int)) and
                not isinstance(px,bool) and 0<float(px)<1_000_000)

def build(catalog,apac,latest,history=None,now=None,fundamentals=None):
    now=now or datetime.now(timezone.utc)
    today=now.astimezone(NZ).date()
    history=history if isinstance(history,dict) else {}
    fundamental_data=(fundamentals or {}).get('companies',{})
    listing={x['symbol']:x for x in catalog.get('items',[])
             if isinstance(x,dict) and x.get('market')=='NZX' and
             isinstance(x.get('symbol'),str) and x.get('symbol') and x.get('name')}
    quotes={q['symbol']:q for q in apac.get('quotes',[])
            if valid_quote(q,today) and q.get('symbol') in listing}
    news={}
    for e in latest.get('events',[]):
        if not isinstance(e,dict) or e.get('type')!='NZX': continue
        sym=e.get('ticker')
        # The existing NZXplorer RSS feed often omits structured tickers
        # despite the headline beginning with [AIR], [FPH], etc.
        if not sym:
            match=re.match(r'^\[([A-Z0-9]{2,6})\]',str(e.get('title','')))
            sym=match.group(1) if match else None
        if not isinstance(sym,str) or sym not in listing: continue
        if not e.get('url') or not e.get('published_at'): continue
        if sym not in news or e['published_at']>news[sym]['published_at']:
            news[sym]=e
    candidates=[]
    for sym,row in sorted(listing.items()):
        q=quotes.get(sym)
        is_etf=row.get('type')=='ETF'
        item=news.get(sym)
        px=q.get('close') if q else None
        qday=q.get('date') if q else None
        financial=score_financials(fundamental_data.get(sym),today) if not is_etf else {'score':None,'status':'ETF WATCH'}
        change=q.get('change_pct') if q else None
        why=(
            (f'Verified NZD exchange close for {qday}; review the fund factsheet, fees and holdings.'
             if is_etf else
             f'Verified NZD exchange close for {qday}; issuer accounting metrics are not yet independently verified.')
            if q else ('NZX-listed ETF; no recent verified closing price.'
                       if is_etf else 'NZX-listed issuer; no recent validated closing price in Scout.')
        )
        if isinstance(change,(int,float)):
            why+=f' Previous-session price movement {change:+.2f}% (not adjusted for corporate actions).'
        evidence=[{'label':'Official NZX issuer disclosures','url':f'https://www.nzx.com/instruments/{sym}'}]
        if financial.get('score') is not None and financial.get('source_url'):
            evidence.append({'label':'Dated company financial ratios ('+str(financial.get('financial_period') or 'reported')+')',
                             'url':financial['source_url'],
                             'timestamp':financial.get('fundamentals_at')})
        if item:
            evidence.append({'label':'Issuer-linked announcement feed (third-party)','url':item['url'],
                             'timestamp':item['published_at']})
        frozen_plan=(plan(q,financial, bool(item)) if q and not is_etf else None)
        if frozen_plan:
            why+=' Financial screen: '+financial['why']+'. Price levels below are a mechanical paper-trading experiment, not certified fair value.'
        candidates.append({
            'symbol':sym,'name':row['name'],'market':'NZX','currency':'NZD',
            'type':'ETF' if is_etf else 'SHARE',
            'status':('ETF WATCH' if is_etf else
                      financial['status'] if q else 'INSUFFICIENT DATA'),
            'score':financial.get('score') if q else None,
            'financially_scored':bool(q and financial.get('score') is not None),
            'price':px,'price_date':qday,
            'filing_url':item.get('url') if item else None,
            'fundamentals_at':financial.get('fundamentals_at'),
            'financial_period':financial.get('financial_period'),
            'change_pct':change,'five_session_change_pct':q.get('five_session_change_pct') if q else None,
            'as_of':None,'industry':'Fund' if is_etf else financial.get('sector') or 'Unverified',
            'why':why,
            'risks':(['ETF holdings, tracking difference and trading spreads require independent verification',
                      'Fund fees, distributions and tax are not included in price-only history']
                     if is_etf else
                     ['NZX trading can be illiquid; price-only signals do not establish business value',
                      'Dividends, stock splits, fees and tax are not included']),
            'evidence':evidence,'last_issuer_news':item,
            'price_plan':frozen_plan or {'signal':'NO RELIABLE PRICE RANGE','currency':'NZD',
                          'entry_ceiling':None,'entry_floor':None,'exit_review_low':None,
                          'exit_review_high':None,'bear_case':None,'as_of':None,
                          'reason':('ETF funds need holdings, costs and suitable NAV/benchmark analysis; no single-company P/E targets.'
                                    if is_etf else
                                    'NZX fundamental valuation and dependable buy/sell levels are not verified. Price data alone is not sufficient.')},
        })
    observations={}
    for row in history.get('observations',[]):
        if isinstance(row,dict) and row.get('symbol') in listing and parse_date(row.get('date')):
            key=(row['symbol'],row['date'])
            observations[key]=row
    for sym,q in quotes.items():
        key=(sym,q['date'])
        if key not in observations:
            observations[key]={'symbol':sym,'date':q['date'],'price':q['close'],
                               'currency':'NZD','first_seen_at':stamp(now)}
    # Store only once-observed daily closes, not retroactive provider price history.
    observations=dict(sorted(observations.items(),key=lambda pair:(pair[0][1],pair[0][0]))[-MAX_HISTORY:])
    frozen=list(history.get('calls',[]))
    existing={(c.get('week'),c.get('symbol')) for c in frozen if isinstance(c,dict)}
    week=today-timedelta(days=today.weekday())
    week_key=week.isoformat()
    # A weekly watch is not a simulated purchase. It is archived before later
    # outcomes, including losses; no fabricated targets or returns.
    for c in candidates:
        if c['price'] is None or (week_key,c['symbol']) in existing: continue
        frozen.append({'id':f'{week_key}|NZX|{c["symbol"]}|WATCH',
                       'week':week_key,'symbol':c['symbol'],'name':c['name'],
                       'market':'NZX','currency':'NZD','signal':'PRICE WATCH ONLY',
                       'decision_at':stamp(now),'original_date':c['price_date'],
                       'reference_price':c['price'],'reason':c['why'],
                       'price_targets':None})
    frozen=frozen[-2000:]
    observed=list(observations.values())
    for call in frozen:
        if not isinstance(call,dict) or call.get('market')!='NZX':continue
        ref=call.get('reference_price')
        entry_date=parse_date(call.get('original_date'))
        if not isinstance(ref,(int,float)) or ref<=0 or not entry_date:continue
        for days in (7,30):
            field=f'change_{days}d_pct'
            if field in call:continue
            candidates_after=[q for q in observed if q['symbol']==call['symbol'] and
                              entry_date+timedelta(days=days)<=parse_date(q['date'])<=
                              entry_date+timedelta(days=days+10)]
            if not candidates_after:continue
            outcome=min(candidates_after,key=lambda q:q['date'])
            delta=(outcome['price']/ref-1)*100
            if abs(delta)>60:
                call[f'{field}_status']='UNVERIFIED_CORPORATE_ACTION'
            else:
                call[field]=round(delta,2)
                call[f'{field}_observed_on']=outcome['date']
    frozen.sort(key=lambda row:row.get('decision_at',''),reverse=True)
    ideas=[c for c in candidates if c.get('price_plan',{}).get('signal')=='PAPER ENTRY CANDIDATE']
    paper_calls=new_calls(ideas,history,today,week_key)
    paper_calls=settle(paper_calls,list(observations.values()),today)
    paper_calls.sort(key=lambda row:row.get('decision_at',''),reverse=True)
    trade_summary=paper_summary(paper_calls)
    verified=[c for c in candidates if c['price'] is not None]
    # NZX watch notes, not a valuation-ranked buy shortlist.
    verified.sort(key=lambda c:(1 if c['last_issuer_news'] else 0,
                              abs(c.get('change_pct') or 0),c['price_date'] or ''),reverse=True)
    mover_alerts=[]
    for c in verified:
        ch=c.get('change_pct')
        if not isinstance(ch,(int,float)) or abs(ch)<8:continue
        mover_alerts.append({'symbol':c['symbol'],'market':'NZX',
                             'headline':f'{c["name"]}: verified close moved {ch:+.1f}%',
                             'why':'Price-movement research trigger only; check announcements, liquidity and possible corporate actions before drawing conclusions.',
                             'risk':'This is not an issuer-confirmed catalyst, an entry price, or a buy instruction.',
                             'published_at':apac.get('generated_at'),
                             'source_url':f'https://www.nzx.com/instruments/{c["symbol"]}',
                             'currency':'NZD','price_date':c['price_date']})
    matured=[c for c in frozen if isinstance(c.get('change_30d_pct'),(int,float))]
    out={
        'schema_version':1,'generated_at':stamp(now),'market':'NZX','currency':'NZD',
        'coverage':{'listed':len(listing),
                    'companies':sum(c['type']=='SHARE' for c in candidates),
                    'etfs':sum(c['type']=='ETF' for c in candidates),
                    'verified_eod':len(verified),
                    'without_recent_eod':len(listing)-len(verified),
                    'financially_scored':sum(c.get('financially_scored') is True for c in candidates),
                    'notice':'Verified closes, not complete financial screening or confirmed Sharesies eligibility'},
        'candidates':candidates,
        'weekly':{'week_start':week_key,'generated_at':stamp(now),
                  'shortlist':sorted((c for c in verified if c['type']=='SHARE'),
                                      key=lambda c:(c.get('score') or 0),reverse=True)[:5],
                  'etf_watch':[next(c for c in candidates if c['symbol']==sym)
                               for sym in ('FNZ','NZG','USF','TWF','DIV')
                               if sym in listing],
                  'verdict':'NZX company screens and mechanical paper-trade levels require documented ratios, issuer-linked news and later verified closes; no guaranteed gains'},
        'alerts':mover_alerts[:15],
        'paper':{'method':'forward-only-educational-paper-v1','benchmark':None,
                 'benchmark_status':'No verified NZX benchmark; NZD paper returns are never compared with US SPY',
                 'summary':dict(trade_summary, watch_records=len(frozen),
                                 matured_7d=sum(isinstance(c.get('change_7d_pct'),(int,float)) for c in frozen),
                                 matured_30d=len(matured),
                                 paper_trades=trade_summary['opened']),
                 'records':paper_calls[:80],
                 'watch_records':frozen[:40],
                 'estimated_round_trip_fee_pct':2.0},
        'learning':{'status':'NOT AUTHORISED','model_active':False,
                    'reason':'NZXplorer terms prohibit training ML models on its data without express written permission. No NZX training or NZX/US outcome mixing.'},
        'limitations':['NZX education paper trades require screened accounting metrics and issuer-linked disclosures. Price levels are mechanical scenarios, not intrinsic value.',
                       'Paper positions enter only at subsequent observed closes. Results include estimated fees, but not dividends, spreads, splits, NZ tax or liquidity.',
                       'Provider usage and redistribution require appropriate permissions; NZXplorer financial data are not used for ML training.'],
    }
    new_history={'schema_version':1,'market':'NZX','currency':'NZD',
                 'observations':list(observations.values()),'calls':frozen,
                 'paper_trades':paper_calls}
    return out,new_history

def main():
    catalog=read(CATALOG)
    apac=read(APAC)
    latest=read(LATEST)
    result,hist=build(catalog,apac,latest,read(HISTORY),
                      fundamentals=read(ROOT/'data'/'nzx_fundamentals.json'))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
    HISTORY.write_text(json.dumps(hist,ensure_ascii=False,indent=2)+'\n')
    print('NZX research',result['coverage'],result['paper']['summary'],
          'US research/cache and ML untouched')

if __name__=='__main__':
    main()
