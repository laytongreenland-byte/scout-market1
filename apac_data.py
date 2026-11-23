#!/usr/bin/env python3
"""Rate-limited, read-only APAC research snapshots. NEVER emits buy/sell signals.

Public site displays historical closes only when a verified date and market match.
Missing/ambiguous provider data is not a price. No broker or trading integration.
"""
from __future__ import annotations
import json, os, re, urllib.request, urllib.parse, urllib.error, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
CATALOG=ROOT/'data'/'market_catalog.json'
OUT=ROOT/'data'/'apac.json'
NZX_ROOT='https://nzxplorer.co.nz/api/v1/'
ASX_ROOT='https://marketdata.seabee.me/api.php'
MAX_BYTES=1_500_000
TZ=timezone.utc

def iso(now):
    return now.astimezone(TZ).isoformat(timespec='seconds').replace('+00:00','Z')

def load(path,default):
    try: return json.loads(path.read_text())
    except (OSError,ValueError): return default

def request(url,key):
    if not (url.startswith(NZX_ROOT) or url.startswith(ASX_ROOT+'?')):
        raise ValueError('Unsupported APAC source')
    if not key: raise ValueError('Provider key unavailable')
    if url.startswith(NZX_ROOT):
        time.sleep(7)  # 10 requests/minute account-wide, including directory calls
    req=urllib.request.Request(url,headers={
        'X-API-Key':key,
        'User-Agent':'Mozilla/5.0 (compatible; ScoutMarketResearch/1.0)',
        'Accept':'application/json'
    })
    with urllib.request.urlopen(req,timeout=14) as response:
        buf=response.read(MAX_BYTES+1)
    if len(buf)>MAX_BYTES: raise ValueError('Oversize provider response')
    obj=json.loads(buf)
    if not isinstance(obj,(list,dict)) or (isinstance(obj,dict) and (
            obj.get('success') is False or obj.get('error') or
            (isinstance(obj.get('meta'),dict) and
             obj['meta'].get('availability_status','ok')!='ok'))):
        raise ValueError('Provider error or non-JSON payload')
    return obj

def extract_rows(obj):
    """Providers may wrap rows; never read arbitrary numeric fields as prices."""
    if isinstance(obj,list): return obj
    if not isinstance(obj,dict): return []
    obj=obj.get('data',obj)
    if isinstance(obj,list): return obj
    if not isinstance(obj,dict): return []
    for key in ('prices','bars','history','results','items','daily','data'):
        part=obj.get(key)
        if isinstance(part,list): return part
        if isinstance(part,dict):
            for k in ('prices','bars','history','results','items','daily'):
                if isinstance(part.get(k),list): return part[k]
    return []

def valid_price(rows,market,symbol,now):
    clean=[]
    for row in rows:
        if not isinstance(row,dict): continue
        dt=str(row.get('date') or row.get('price_date') or row.get('trading_date') or '')[:10]
        try: day=datetime.strptime(dt,'%Y-%m-%d').date()
        except ValueError: continue
        px=row.get('close')
        if px is None: px=row.get('closing_price')
        if not isinstance(px,(float,int)) or isinstance(px,bool) or not 0<float(px)<1_000_000:
            continue
        # Reject future dates and old data. Calendar age deliberately errs on caution.
        exchange_day=now.astimezone(ZoneInfo('Pacific/Auckland' if market=='NZX' else 'Australia/Sydney')).date()
        if not 0<=(exchange_day-day).days<=7: continue
        clean.append((day,float(px)))
    if not clean: return None
    day,px=max(clean)
    return {'symbol':symbol,'market':market,'currency':'NZD' if market=='NZX' else 'AUD',
            'close':round(px,6),'date':day.isoformat(),'price_type':'EOD',
            'source':'NZXplorer' if market=='NZX' else 'SeaBee',
            'research_only':True}

def fetch_nzx(symbol,key):
    params=urllib.parse.urlencode({'days':14,'limit':15})
    return request(NZX_ROOT+'prices/'+symbol+'?'+params,key)

def fetch_asx(symbol,key):
    params=urllib.parse.urlencode({'action':'price_bars','ticker':symbol,
        'market':'AU','interval':'1D',
        'from':(datetime.now(TZ).date()-timedelta(days=30)).isoformat(),
        'limit':50})
    return request(ASX_ROOT+'?'+params,key)

def build(now=None,catalog=None,previous=None,fetchers=None):
    now=now or datetime.now(TZ)
    today=now.date().isoformat()
    catalog=catalog if catalog is not None else load(CATALOG,{})
    previous=previous if previous is not None else load(OUT,{})
    secrets={'NZX':os.environ.get('NZXPLORER_API_KEY'),
             'ASX':os.environ.get('SEABEE_API_KEY')}
    fetchers=fetchers or {'NZX':fetch_nzx,'ASX':fetch_asx}
    previous_quotes=previous.get('quotes',[]) if isinstance(previous,dict) else []
    quotes={}
    for q in previous_quotes:
        if isinstance(q,dict) and q.get('market') in secrets and q.get('symbol'):
            quotes[(q['market'],q['symbol'])]=q
    markets={}
    errors={}
    items=catalog.get('items',[])
    for market in ('NZX','ASX'):
        key=secrets[market]
        symbols=sorted({x.get('symbol') for x in items
                        if isinstance(x,dict) and x.get('market')==market and
                           re.fullmatch(r'[A-Z0-9]{2,6}',str(x.get('symbol','')))})
        if not key or not symbols:
            markets[market]={'status':'NO_API_KEY' if not key else 'NO_VALID_DIRECTORY',
                             'attempted':0,'valid':0,'directory_symbols':len(symbols),
                             'recent_prices':0}
            continue
        # Once daily; bounded per-provider calls. Stable rotation through catalog.
        # NZX free account: 250 req/day; avoid hourly depletion.
        prior_day=previous.get('fetched_days',{}).get(market)
        retry_after=previous.get('retry_after',{}).get(market)
        attempts=0;valid=0
        stopped_reason=None
        # Avoid retrying dead APIs on every hourly run, while allowing
        # transient failures to recover before the next calendar day.
        retry_dt=None
        try:
            if retry_after: retry_dt=datetime.fromisoformat(retry_after.replace('Z','+00:00'))
        except (ValueError,TypeError): pass
        can_retry=retry_dt is None or now>=retry_dt
        if prior_day!=today and can_retry:
            # NZX roughly fits a 20/day rolling EOD scan without exceeding
            # its documented free 250/day limit; ASX remains quota-cautious.
            default_limit=20 if market=='NZX' else 10
            upper_limit=25 if market=='NZX' else 30
            setting='SCOUT_'+market+'_PRICE_DAILY_LIMIT'
            try: requested=int(os.environ.get(setting,str(default_limit)))
            except ValueError: requested=default_limit
            count=min(max(1,requested),upper_limit,len(symbols))
            cycle=(now.date().toordinal()*count)%len(symbols)
            selected=[symbols[(cycle+i)%len(symbols)] for i in range(count)]
            for symbol in selected:
                attempts+=1
                try:
                    rows=extract_rows(fetchers[market](symbol,key))
                    record=valid_price(rows,market,symbol,now)
                    if record:
                        quotes[(market,symbol)]=record
                        valid+=1
                    else:
                        errors[market]='One or more price responses were unrecognised or stale'
                except urllib.error.HTTPError as exc:
                    errors[market]='Price provider HTTP '+str(exc.code)
                    if exc.code in (401,403):
                        stopped_reason='AUTH_FAILED'
                        break
                    if exc.code==429:
                        stopped_reason='RATE_LIMITED'
                        break
                except Exception:
                    errors[market]='One or more provider requests failed'
        retained=sum(1 for (m,s),q in quotes.items() if m==market and
                     valid_price([{'date':q.get('date'),'close':q.get('close')}],m,s,now))
        status=('PRICE_RESEARCH' if retained else
                stopped_reason or ('PROVIDER_ERROR' if attempts and errors.get(market)
                                   else 'NO_VALID_PRICES'))
        markets[market]={'status':status,
                         'attempted':attempts,'valid_this_run':valid,
                         'recent_prices':retained,
                         'directory_symbols':len(symbols),
                         'daily_request_limit':count if attempts else 0,
                         'source':'NZXplorer' if market=='NZX' else 'SeaBee'}
    final_quotes=[]
    for (market,symbol),q in sorted(quotes.items()):
        if valid_price([{'date':q.get('date'),'close':q.get('close')}],market,symbol,now):
            final_quotes.append(q)
    days=dict(previous.get('fetched_days',{}))
    retries=dict(previous.get('retry_after',{}))
    for market in ('NZX','ASX'):
        if not secrets[market]: continue
        if markets[market].get('valid_this_run'):
            days[market]=today
            retries.pop(market,None)
        elif markets[market].get('attempted'):
            # A bad attempt is not a successful daily refresh.
            # Retry in 6 hours; auth/rate-limit errors wait a full day.
            hours=24 if markets[market]['status'] in ('AUTH_FAILED','RATE_LIMITED') else 6
            retries[market]=iso(now+timedelta(hours=hours))
    return {'schema_version':1,'generated_at':iso(now),
            'description':'Research-only verified daily closes. Not live quotes, forecasts, or trades.',
            'markets':markets,'fetched_days':days,'retry_after':retries,'quotes':final_quotes,
            'provider_warnings':errors,
            'limitations':['ASX needs SEABEE_API_KEY; NZX uses NZXPLORER_API_KEY.',
              'Data is EOD, provider-dependent, and may lack corporate-action adjustments.',
              'Neither market contributes to buy/sell scoring or paper-trading outcomes.',
              'Do not interpret a missing symbol as an unlisted or uninvestable security.']}

def main():
    if os.environ.get('SCOUT_OFFLINE')=='1':
        print('APAC prices: offline mode')
        return 0
    result=build()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result,separators=(',',':'))+'\n')
    print('APAC price snapshot:',{k:v for k,v in result['markets'].items()})
    return 0

if __name__=='__main__':
    raise SystemExit(main())
