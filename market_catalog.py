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
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'data'/'market_catalog.json'
NOW=datetime.now(timezone.utc)
FRESH_DAYS=7
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

def build(fetcher=fetch_source,now=None):
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
    items.sort(key=lambda row:row['symbol'])
    status='READY' if all(s['ok'] for s in source_status.values()) else 'PARTIAL' if items else 'UNAVAILABLE'
    return {
        'schema_version':1,
        'generated_at':stamp(now),
        'status':status,
        'platform':'Sharesies NZ (target only, availability NOT verified)',
        'sharesies_availability_verified':False,
        'prices_collected':False,
        'valuation_done':False,
        'markets':{
            'US':{'status':'DISCOVERED' if items else 'UNAVAILABLE',
                  'listed_in_directory':len(items),
                  'notes':'US securities listed on covered exchanges; actual Sharesies availability unknown'},
            'ASX':{'status':'NOT_CONNECTED','listed_in_directory':0,
                   'notes':'Reliable licensed/reference directory and usable price feed not connected'},
            'NZX':{'status':'NOT_CONNECTED','listed_in_directory':0,
                   'notes':'Reliable complete current instrument directory and usable price feed not connected'},
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
            'US listings are not the entire Sharesies catalogue; ASX and NZX remain unconnected.',
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
    if os.environ.get('SCOUT_DISCOVERY_FORCE')!='1' and old and old.get('status')=='READY':
        at=parse_date(old.get('generated_at'))
        if at and timedelta(0)<=NOW-at<timedelta(days=FRESH_DAYS):
            print('Exchange catalogue is recent; keeping verified existing file')
            return 0
    result=build()
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
