#!/usr/bin/env python3
"""Scout exchange discovery.  Never changes its trading/valuation universe.

Downloads public US exchange *listing metadata*, not market prices, broker
availability, financial quality or buy signals.  This is a separate bounded
process so a provider failure cannot break the normal market scanner.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import urllib.request
import urllib.error
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'data'/'market_catalog.json'
NOW=datetime.now(timezone.utc)
FRESH_DAYS=7
ASX_DIRECTORY='https://www.asx.com.au/asx/research/ASXListedCompanies.csv'
NZX_ETF_FILE=ROOT/'data'/'nzx_etfs.json'
NZX_DIRECTORY='https://nzxplorer.co.nz/api/v1/companies'
# NZXplorer defaults to 50 rows. Limit 250 is within the documented 500 maximum.
NZX_FULL=NZX_DIRECTORY+'?limit=250'
NZX_PAGES=[NZX_DIRECTORY+'?limit=50&offset='+str(n) for n in (0,50,100,150)]
MAX_BYTES=4_000_000
SOURCES={
    'NASDAQ':'https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt',
    'OTHER_US':'https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt',
}
VENUES={'N':'NYSE','A':'NYSE American','P':'NYSE Arca','Z':'Cboe US'}
SYMBOL_PATTERN=re.compile(r'^[A-Z][A-Z0-9.$^/-]{0,11}$')
OTHER_PATTERN=re.compile(r'\b(warrants?|rights?|units?|preferred|depositary preferred|notes?|debentures?|certificate[s]?|contingent value rights)\b',re.IGNORECASE)

def stamp(d):
    return d.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')

def parse_date(value):
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except (ValueError,TypeError):
        return None

def fetch_source(url):
    if url not in SOURCES.values():
        raise ValueError('Unexpected source URL')
    req=urllib.request.Request(url,headers={
        'User-Agent':'ScoutMarketDiscovery/1.0 (public exchange symbol directory)'
    })
    with urllib.request.urlopen(req,timeout=12) as response:
        content=response.read(MAX_BYTES+1)
    if len(content)>MAX_BYTES:
        raise ValueError('Directory exceeds maximum safe size')
    return content

def parse_listing(source,payload):
    if source not in SOURCES:
        raise ValueError('Unknown exchange listing source')
    if len(payload)>MAX_BYTES:
        raise ValueError('Oversize listing data')
    data=payload.decode('utf-8-sig')
    table=csv.DictReader(io.StringIO(data),delimiter='|')
    expected=(
        {'Symbol','Security Name','ETF','Test Issue'} if source=='NASDAQ'
        else {'ACT Symbol','Security Name','Exchange','ETF','Test Issue'}
    )
    if not expected.issubset(set(table.fieldnames or [])):
        raise ValueError('Wrong directory columns')
    results=[]
    for r in table:
        if r.get('Test Issue')!='N':
            continue
        sym=str(r.get('Symbol' if source=='NASDAQ' else 'ACT Symbol') or '').strip().upper()
        if not SYMBOL_PATTERN.fullmatch(sym):
            continue
        name=str(r.get('Security Name') or '').strip()[:160]
        if not name:
            continue
        exchange='Nasdaq' if source=='NASDAQ' else VENUES.get(r.get('Exchange'))
        if not exchange:
            continue
        is_etf=(r.get('ETF')=='Y')
        kind='ETF' if is_etf else ('OTHER' if OTHER_PATTERN.search(name) else 'SHARE')
        results.append({
            'symbol':sym,'name':name,'exchange':exchange,
            'market':'US','type':kind,
        })
    if len(results)<2000 or len(results)>13000:
        raise ValueError('Directory returned an unexpected number of securities')
    # Disallow mass corruption / truncated files while preserving opaque
    # names for informational lookup (no valuation is done here).
    seen=set()
    unique=[]
    for item in results:
        if item['symbol'] in seen:
            continue
        seen.add(item['symbol'])
        unique.append(item)
    return unique


def fetch_apac(url,key=None):
    if url not in (ASX_DIRECTORY,NZX_DIRECTORY,NZX_FULL,*NZX_PAGES):
        raise ValueError('Unapproved exchange source')
    headers={'User-Agent':'Mozilla/5.0 (compatible; ScoutMarketDiscovery/1.0)', 'Accept':'application/json, text/csv;q=0.9, */*;q=0.1'}
    if key:
        headers['X-API-Key']=key
    # NZXplorer free tier is 10 requests/minute, shared across directory and prices.
    # Pacing here and in apac_data.py avoids a burst across process boundaries.
    if url.startswith(NZX_DIRECTORY):
        time.sleep(7)
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=18) as response:
        content=response.read(MAX_BYTES+1)
    if len(content)>MAX_BYTES:
        raise ValueError('APAC directory too large')
    return content

def parse_asx(payload):
    """ASX public listed-company CSV; discovery only, not current prices."""
    if len(payload)>MAX_BYTES:
        raise ValueError('ASX CSV too large')
    content=payload.decode('utf-8-sig')
    lines=content.splitlines()
    header=next((i for i,line in enumerate(lines[:12])
                 if 'ASX code' in line and 'Company name' in line),None)
    if header is None:
        raise ValueError('ASX CSV header missing')
    table=csv.DictReader(io.StringIO('\n'.join(lines[header:])))
    result=[]
    seen=set()
    for entry in table:
        code=str(entry.get('ASX code') or '').strip().upper()
        name=str(entry.get('Company name') or '').strip()[:160]
        if not re.fullmatch(r'[A-Z0-9]{2,6}',code) or not name or code in seen:
            continue
        seen.add(code)
        result.append({'symbol':code,'name':name,'exchange':'ASX','market':'ASX','type':'SHARE'})
    if not 900<=len(result)<=4000:
        raise ValueError('ASX directory count outside validation range')
    return sorted(result,key=lambda x:x['symbol'])

def parse_nzx(payload):
    """NZXplorer authenticated company list; reject partial/ambiguous responses."""
    if len(payload)>MAX_BYTES:
        raise ValueError('NZX response too large')
    document=json.loads(payload)
    data=document.get('data',document) if isinstance(document,dict) else document
    if isinstance(data,dict):
        # The endpoint may be an envelope, a list, or a keyed map.
        for field in ('companies','results','items'):
            if field in data:
                data=data[field]
                break
    # The documented v1 endpoint can deliver a full company list in one
    # response. Accept both array and ticker-keyed maps, never partial strings.
    if isinstance(data,dict):
        data=[dict(row, ticker=row.get('ticker') or row.get('symbol') or ticker)
              for ticker,row in data.items() if isinstance(row,dict)]
    if not isinstance(data,list):
        raise ValueError('Unexpected NZX company schema')
    output=[]
    seen=set()
    for entry in data:
        if not isinstance(entry,dict):
            continue
        ticker=str(entry.get('ticker') or entry.get('symbol') or '').strip().upper()
        name=str(entry.get('name') or entry.get('company_name') or '').strip()[:160]
        if not re.fullmatch(r'[A-Z0-9]{2,6}',ticker) or not name or ticker in seen:
            continue
        seen.add(ticker)
        output.append({'symbol':ticker,'name':name,'exchange':'NZX','market':'NZX','type':'SHARE'})
    if not 0<=len(output)<=350:
        raise ValueError('NZX response outside safe directory size')
    return sorted(output,key=lambda x:x['symbol'])

def apac_discovery(old=None):
    """Each region fails independently; retain previously validated per-market data."""
    old=old if isinstance(old,dict) else {}
    old_items=old.get('items',[])
    old_markets=old.get('markets',{})
    items=[]
    markets={}
    sources={}
    definitions=[
        ('ASX',ASX_DIRECTORY,None,parse_asx),
        ('NZX',NZX_DIRECTORY,os.environ.get('NZXPLORER_API_KEY'),parse_nzx),
    ]
    for market,url,key,parser in definitions:
        prior=[x for x in old_items if isinstance(x,dict) and x.get('market')==market]
        try:
            if market=='NZX' and not key:
                raise ValueError('NZXPLORER_API_KEY not configured')
            if market=='NZX':
                # Explicit full-page request: default GET /companies returns only
                # 50, which is not a complete NZX directory.
                # Only fall back to bounded smaller pages if needed.
                try:
                    fresh=parser(fetch_apac(NZX_FULL,key))
                    if not 80<=len(fresh)<=350:
                        raise ValueError('NZX full list incomplete')
                except (ValueError,urllib.error.HTTPError,urllib.error.URLError,TimeoutError):
                    pages=[parser(fetch_apac(page,key)) for page in NZX_PAGES]
                    fresh=list({record['symbol']:record for page in pages for record in page}.values())
                    if not 80<=len(fresh)<=350 or (
                            len(pages[0])==50 and len(pages[1])==50 and pages[0]==pages[1]):
                        raise ValueError('NZX directory incomplete or pagination ignored')
            else:
                fresh=parser(fetch_apac(url,key))
            chosen=fresh
            status='DISCOVERED'
            note='Company directory verified; prices and fundamentals NOT connected'
            sources[market]={'ok':True,'count':len(fresh),'url':url}
        except Exception as exc:
            chosen=prior
            status='STALE_DIRECTORY' if prior else 'NOT_CONNECTED'
            if isinstance(exc,urllib.error.HTTPError):
                reason='HTTP_'+str(exc.code)
            else:
                reason=type(exc).__name__
            note=reason+': directory unavailable; prices and fundamentals NOT connected'
            sources[market]={'ok':False,'count':len(prior),'url':url,'note':note}
        items.extend(chosen)
        markets[market]={'status':status,'listed_in_directory':len(chosen),
                         'notes':note,'last_attempt_at':stamp(NOW)}
    return items,markets,sources

def nzx_etf_list():
    """Dated issuer-backed NZX ETF discovery metadata. Never implies a price."""
    try:
        document=json.loads(NZX_ETF_FILE.read_text())
        records=document.get('items',[])
        if document.get('schema_version')!=1 or not 25<=len(records)<=80:
            return []
        found={}
        for x in records:
            if not isinstance(x,dict) or x.get('market')!='NZX' or x.get('type')!='ETF':
                return []
            symbol=x.get('symbol','')
            name=x.get('name','')
            if not re.fullmatch(r'[A-Z0-9]{2,6}',symbol) or not isinstance(name,str) or not name.startswith('Smart '):
                return []
            found[symbol]={'symbol':symbol,'name':name[:160],'exchange':'NZX',
                           'market':'NZX','type':'ETF',
                           'discovery_source':'Smart public ETF catalogue'}
        return list(found.values()) if len(found)==len(records) else []
    except (OSError,ValueError,TypeError):
        return []


def build(fetcher=fetch_source,now=None,old=None):
    now=now or NOW
    collected=[]
    source_status={}
    for source,url in SOURCES.items():
        try:
            items=parse_listing(source,fetcher(url))
            source_status[source]={
                'ok':True,'count':len(items),'url':url,
                'note':'Official US exchange-listed security directory, NOT a Sharesies instrument list',
            }
            collected.extend(items)
        except Exception as exc:
            source_status[source]={
                'ok':False,'count':0,'url':url,
                'note':type(exc).__name__+': source unavailable or failed validation',
            }
    seen=set()
    items=[]
    for row in collected:
        if row['symbol'] in seen:
            continue
        seen.add(row['symbol'])
        items.append(row)
    apac_items,apac_markets,apac_sources=apac_discovery(old)
    items.extend(apac_items)
    etf_rows=nzx_etf_list()
    seen_nzx={row['symbol'] for row in items if row['market']=='NZX'}
    etf_rows=[row for row in etf_rows if row['symbol'] not in seen_nzx]
    items.extend(etf_rows)
    if etf_rows:
        nz=apac_markets.get('NZX',{})
        nz['listed_in_directory']=int(nz.get('listed_in_directory',0))+len(etf_rows)
        nz['etf_listings_verified']=len(etf_rows)
        nz['notes']=(nz.get('notes','')+
                     '; includes dated Smart NZX-listed ETF symbols, not prices or broker availability')
        if nz.get('status')=='NOT_CONNECTED':
            nz['status']='PARTIAL_DISCOVERY'
        apac_markets['NZX']=nz
    source_status['SMART_NZX_ETFS']={'ok':bool(etf_rows),'count':len(etf_rows),
        'url':'https://www.smartinvest.co.nz/funds-and-performance/etfs',
        'note':'Public ETF listings only; NZXplorer company directory excludes ETFs'}
    source_status.update(apac_sources)
    items.sort(key=lambda row:(row['market'],row['symbol']))
    status='READY' if all(source_status[k]['ok'] for k in SOURCES) else 'PARTIAL' if items else 'UNAVAILABLE'
    return {
        'schema_version':2,
        'nzx_directory_strategy_version':4,
        'generated_at':stamp(now),
        'status':status,
        'platform':'Sharesies NZ (target only, availability NOT verified)',
        'sharesies_availability_verified':False,
        'prices_collected':False,
        'valuation_done':False,
        'markets':{
            'US':{'status':'DISCOVERED' if collected else 'UNAVAILABLE',
                  'listed_in_directory':len({row['symbol'] for row in collected}),
                  'notes':'US securities listed on covered exchanges; actual Sharesies availability unknown'},
            **apac_markets,
        },
        'sources':source_status,
        'counts':{
            'listed_total':len(items),
            'shares':sum(row['type']=='SHARE' for row in items),
            'etfs':sum(row['type']=='ETF' for row in items),
            'other':sum(row['type']=='OTHER' for row in items)
        },
        'items':items,
        'cautions':[
            'This is a market DISCOVERY catalogue only; it does not fetch prices or recommend anything.',
            'Exchange-listed does not mean available on Sharesies. Check broker availability before any purchase.',
            'Directory discovery is not the full Sharesies catalogue; APAC prices and financial screening remain unconnected.',
            'Not every listed security is an ordinary company share: many are ETFs, warrants, units or preferred stocks.',
            'No credentials, orders, Sharesies account access or existing trade history are affected.'
        ],
    }

def main():
    if os.environ.get('SCOUT_OFFLINE')=='1':
        print('Offline mode: market discovery skipped')
        return 0
    old=None
    if OUT.exists():
        try:
            old=json.loads(OUT.read_text())
        except (json.JSONDecodeError,OSError):
            old=None
    if (os.environ.get('SCOUT_DISCOVERY_FORCE')!='1' and old and
            old.get('schema_version')==2 and old.get('status')=='READY' and
            old.get('nzx_directory_strategy_version')==4):
        at=parse_date(old.get('generated_at'))
        if at and timedelta(0)<=NOW-at<timedelta(days=FRESH_DAYS):
            nz=old.get('markets',{}).get('NZX',{})
            nz_attempt=parse_date(nz.get('last_attempt_at'))
            nz_healthy=nz.get('status')=='DISCOVERED'
            key_missing=not os.environ.get('NZXPLORER_API_KEY')
            attempted_recently=nz_attempt and timedelta(0)<=NOW-nz_attempt<timedelta(days=1)
            if nz_healthy or key_missing or attempted_recently:
                print('Exchange catalogue recent; retaining validated list (NZX retries at most daily)')
                return 0
    result=build(old=old)
    if result['status']!='READY' and old and old.get('status')=='READY':
        print('WARN: Exchange directory refresh incomplete; preserving last complete catalogue',file=sys.stderr)
        return 0
    if result['status']=='UNAVAILABLE':
        print('WARN: US exchange directories unavailable; no change to existing market scanner',file=sys.stderr)
        return 0
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
    print('Exchange catalogue',result['status'],result['counts'],
          'Sharesies availability UNVERIFIED; scanner untouched')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
