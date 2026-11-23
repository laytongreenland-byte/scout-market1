#!/usr/bin/env python3
"""Bounded live connection probe. No market records, orders, ML or personal data."""
from __future__ import annotations
import json
import os
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from market_catalog import NZX_FULL, fetch_apac, parse_nzx
from apac_data import fetch_nzx, fetch_asx, extract_rows, valid_price
OUT=ROOT/'data'/'regional_canary.json'
NOW=datetime.now(timezone.utc)

def status_error(exc):
    if isinstance(exc,urllib.error.HTTPError):
        return 'HTTP_'+str(exc.code)
    if isinstance(exc,urllib.error.URLError):
        return 'CONNECTION_ERROR'
    if isinstance(exc,(ValueError,KeyError,TypeError)):
        return 'INVALID_RESPONSE'
    return 'PROVIDER_FAILURE'

def run():
    result={'checked_at':NOW.isoformat(),'research_only':True,
            'note':'One sampled provider request only; this is not full price coverage.',
            'NZX':{},'ASX':{}}
    nzkey=os.environ.get('NZXPLORER_API_KEY','').strip()
    if not nzkey:
        result['NZX']={'directory':'NO_API_KEY','sample_price':'NO_API_KEY'}
    else:
        try:
            names=parse_nzx(fetch_apac(NZX_FULL,nzkey))
            result['NZX']['directory']='OK' if 80<=len(names)<=350 else 'INCOMPLETE'
            result['NZX']['listings_seen']=len(names)
        except Exception as exc:
            result['NZX']['directory']=status_error(exc)
            result['NZX']['listings_seen']=0
        try:
            info=fetch_nzx('AIR',nzkey)
            q=valid_price(extract_rows(info),'NZX','AIR',NOW)
            result['NZX']['sample_price']='OK' if q else 'NO_VERIFIED_EOD_BAR'
        except Exception as exc:
            result['NZX']['sample_price']=status_error(exc)
    asxkey=os.environ.get('SEABEE_API_KEY','').strip()
    if not asxkey:
        result['ASX']={'sample_price':'NO_API_KEY'}
    else:
        try:
            info=fetch_asx('BHP',asxkey)
            q=valid_price(extract_rows(info),'ASX','BHP',NOW)
            result['ASX']={'sample_price':'OK' if q else 'NO_VERIFIED_EOD_BAR'}
        except Exception as exc:
            result['ASX']={'sample_price':status_error(exc)}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result,indent=2)+'\n')
    print('Regional provider probe (no prices stored):',result['NZX'],result['ASX'])

if __name__=='__main__':
    run()
