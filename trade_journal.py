"""Scout's forward-only paper decision ledger.

Every opinion is frozen when FIRST observed. Later scans may evaluate it, never
rewrite its reasoning, buy level, exit-review level or timestamp. No simulated
fill is allowed on the same NY market session as the original signal.

This is deliberately a DAILY-CLOSE paper study, not executable order history:
quotes are not guaranteed adjusted for splits, dividends, spreads, FX, tax or
intraday touches. A target "hit" means a verified later recorded CLOSE >= target.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UTC=timezone.utc
NY=ZoneInfo('America/New_York')
ENTRY_WINDOW_DAYS=14
HOLD_DAYS=30
PRICE_FRICTION_PCT=1.0
MAX_SNAPSHOTS=12000
MAX_PUBLIC=120
ACTIVE={'ENTRY CANDIDATE','WAIT FOR ENTRY'}
FINAL={'TARGET_REACHED','CLOSED_GAIN','CLOSED_LOSS','NO_ENTRY','OBSERVED_AFTER_SKIP'}
DECISIONS=ACTIVE|{'QUALITY GATE NOT MET','ABOVE BASE CASE','POSSIBLE VALUE TRAP','NO RELIABLE PRICE RANGE'}
METHOD='daily-close-paper-v1'

def time_of(value):
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return d.astimezone(UTC) if d.tzinfo else None
    except (ValueError,TypeError,OverflowError):
        return None

def num(value):
    if isinstance(value,bool):
        return None
    try:
        v=float(value)
        return v if math.isfinite(v) else None
    except (ValueError,TypeError,OverflowError):
        return None

def stamp(d):
    return d.astimezone(UTC).isoformat(timespec='seconds').replace('+00:00','Z')

def week_of(now):
    local=now.astimezone(ZoneInfo('Pacific/Auckland')).date()
    return (local-timedelta(days=local.weekday())).isoformat()

def record_decisions(history,candidates,now):
    """Freeze each new ticker/verdict combination at most once per NZ week."""
    hist=dict(history or {})
    rows=list(hist.get('decisions') or [])
    existing={r.get('id') for r in rows}
    week=week_of(now)
    for c in candidates:
        signal=(c.get('price_plan') or {}).get('signal')
        if signal not in DECISIONS or c.get('status') not in ('INVESTIGATE','WATCH'):
            continue
        symbol=c.get('symbol')
        quoted=time_of(c.get('as_of'))
        price=num(c.get('price'))
        if not symbol or not quoted or not price or price<=0:
            continue
        if quoted>now+timedelta(minutes=10) or now-quoted>timedelta(hours=75):
            continue
        key=week+'|'+symbol+'|'+signal
        if key in existing:
            continue
        p=c.get('price_plan') or {}
        ceil=num(p.get('entry_ceiling'))
        exit_=num(p.get('exit_review_low'))
        if signal in ACTIVE and not (ceil and exit_ and 0<ceil<exit_):
            continue
        rows.append({
            'id':key,'week':week,'symbol':symbol,'name':str(c.get('name') or symbol)[:110],
            'signal':signal,'decision_at':stamp(now),'quote_at':stamp(quoted),
            'reference_price':round(price,4),'score':c.get('score'),
            'quality_status':c.get('status'),
            'buy_ceiling':round(ceil,4) if ceil and ceil>0 else None,
            'sell_review':round(exit_,4) if exit_ and exit_>0 else None,
            'bear_case':p.get('bear_case'),
            'why':str(c.get('why') or '')[:360],
            'risk':str((c.get('risks') or ['Business and market prices may change'])[0])[:220],
            'financials_retrieved_at':c.get('fundamentals_at'),
            'price_model_version':p.get('method_version'),
            'currency':'USD','method':METHOD,
        })
        existing.add(key)
    hist['decisions']=rows[-MAX_SNAPSHOTS:]
    return hist

def close_index(history,now):
    """Latest available positive price for each (symbol, NY session)."""
    grouped=defaultdict(dict)
    for row in history.get('daily',[]):
        date=time_of(row.get('price_at'))
        price=num(row.get('price'))
        symbol=row.get('symbol')
        if not date or date>now or not symbol or not price or price<=0:
            continue
        sess=date.astimezone(NY).date()
        old=grouped[symbol].get(sess)
        if old is None or date>old[0]:
            grouped[symbol][sess]=(date,price)
    return grouped

def result_of(decision,market,now):
    """Pure state from frozen prediction and subsequently observed closing prices."""
    signal=decision.get('signal')
    start=time_of(decision.get('quote_at'))
    when=time_of(decision.get('decision_at'))
    ref=num(decision.get('reference_price'))
    sym=decision.get('symbol')
    if not start or not when or not ref or ref<=0 or not sym:
        return {'status':'UNVERIFIED','reason':'Original quote or prediction timestamp unavailable'}
    first_session=start.astimezone(NY).date()
    pairs=[]
    for session,(timestamp,price) in market.get(sym,{}).items():
        spy=market.get('SPY',{}).get(session)
        if session<=first_session or not spy:
            continue
        spy_ts,spy_price=spy
        if abs((timestamp-spy_ts).total_seconds())>24*3600:
            continue
        pairs.append((session,timestamp,price,spy_price))
    pairs.sort(key=lambda r:r[0])
    def empty(status,reason):
        return {'status':status,'reason':reason}
    # Decisions to avoid a purchase are accountability observations, NOT wins.
    if signal not in ACTIVE:
        baseline=market.get('SPY',{}).get(first_session)
        if not baseline:
            return empty('UNVERIFIED','No same-session SPY baseline available; cannot grade the skip')
        if now<when+timedelta(days=HOLD_DAYS):
            return empty('OBSERVING_SKIP','No trade proposed. Checking whether avoiding the purchase was sensible after 30 days')
        after=[p for p in pairs if p[1]>=when+timedelta(days=HOLD_DAYS)
               and p[1]<=when+timedelta(days=HOLD_DAYS+10)]
        if not after:
            return empty('UNVERIFIED','30-day paired stock/SPY observation not yet available')
        day,t,price,spy_end=after[0]
        change=(price/ref-1)*100
        market_change=(spy_end/baseline[1]-1)*100
        if abs(change)>60 or abs(market_change)>40:
            return empty('UNVERIFIED','Unadjusted prices may reflect a split or bad quote')
        return {'status':'OBSERVED_AFTER_SKIP','reason':'Scout did not suggest a trade; this is only the subsequent stock performance, not a win',
                'observed_at':stamp(t),'observed_price':round(price,4),
                'stock_change_pct':round(change,2),'spy_change_pct':round(market_change,2)}
    ceiling=num(decision.get('buy_ceiling'))
    exit_target=num(decision.get('sell_review'))
    if not ceiling or not exit_target or exit_target<=ceiling:
        return empty('UNVERIFIED','Original buy or sell scenario was not frozen')
    last_entry_date=when.astimezone(NY).date()+timedelta(days=ENTRY_WINDOW_DAYS)
    entry=[p for p in pairs if p[0]<=last_entry_date and p[2]<=ceiling]
    if not entry:
        if now<when+timedelta(days=ENTRY_WINDOW_DAYS+1):
            return empty('WAITING_TO_BUY','No later observed daily close has met the original buy ceiling')
        observed=sum(1 for p in pairs if p[0]<=last_entry_date)
        if observed<3:
            return empty('UNVERIFIED','Too few paired daily closes to determine whether an entry was possible')
        return {'status':'NO_ENTRY','reason':'No observed closing price reached the buy ceiling within 14 days; no paper trade was opened',
                'entry_window_ended':last_entry_date.isoformat(),'session_count':observed}
    enter_day,enter_at,entry_price,spy_entry=entry[0]
    elapsed=enter_at+timedelta(days=HOLD_DAYS)
    post=[p for p in pairs if p[0]>enter_day]
    if not post:
        return {'status':'OPEN','reason':'Paper entry recorded; awaiting later closing prices',
                'entry_at':stamp(enter_at),'entry_price':round(entry_price,4),'spy_entry':round(spy_entry,4)}
    # If exit-review price is reached at a later close, the paper plan exits then.
    targets=[p for p in post if p[1]<=elapsed and p[2]>=exit_target]
    if targets:
        ending=targets[0]
        finish_status='TARGET_REACHED'
    else:
        eligible=[p for p in post if elapsed<=p[1]<=elapsed+timedelta(days=10)]
        if not eligible:
            latest=post[-1]
            return {'status':'OPEN' if now<elapsed+timedelta(days=10) else 'UNVERIFIED',
                    'reason':'Entry recorded; 30-day same-session closing price not yet available' if now<elapsed+timedelta(days=10) else 'Missing verified closing data around the end of the holding period',
                    'entry_at':stamp(enter_at),'entry_price':round(entry_price,4),
                    'latest_at':stamp(latest[1]),'latest_close':round(latest[2],4)}
        ending=eligible[0]
        finish_status=None
    exit_day,exit_at,exit_price,spy_exit=ending
    gross=(exit_price/entry_price-1)*100
    spy_return=(spy_exit/spy_entry-1)*100
    if abs(gross)>60 or abs(spy_return)>40:
        return empty('UNVERIFIED','An extreme unadjusted price move requires corporate-action verification')
    net=gross-PRICE_FRICTION_PCT
    if finish_status is None:
        finish_status='CLOSED_GAIN' if net>0 else 'CLOSED_LOSS'
    return {'status':finish_status,'reason':'Later recorded closing price reached the original sell-review threshold' if finish_status=='TARGET_REACHED' else 'Paper position closed at the first recorded close at least 30 days after entry',
            'entry_at':stamp(enter_at),'entry_price':round(entry_price,4),
            'exit_at':stamp(exit_at),'exit_price':round(exit_price,4),
            'gross_return_pct':round(gross,2),'net_return_pct':round(net,2),
            'spy_return_pct':round(spy_return,2),'excess_after_cost_pct':round(net-spy_return,2),
            'estimated_round_trip_friction_pct':PRICE_FRICTION_PCT,
            'target_hit':finish_status=='TARGET_REACHED'}

def update_results(history,now):
    """Seal completed observations. Never recalculate an already sealed outcome."""
    hist=dict(history or {})
    market=close_index(hist,now)
    for row in hist.get('decisions',[]):
        if row.get('sealed_result'):
            continue
        assessment=result_of(row,market,now)
        if assessment['status'] in FINAL:
            row['sealed_result']=assessment
    return hist

def public_results(history,now):
    market=close_index(history,now)
    rows=history.get('decisions',[])
    displayed=[]
    summary={'recorded':len(rows),'purchase_scenarios':0,'opened':0,'closed':0,
             'positive':0,'negative':0,'targets_reached':0,'not_triggered':0,
             'waiting':0,'unverified':0,'skipped':0,'benchmark_beaten':0}
    for r in rows:
        is_trade=r.get('signal') in ACTIVE
        a=r.get('sealed_result') or result_of(r,market,now)
        status=a.get('status')
        if is_trade:
            summary['purchase_scenarios']+=1
            if status in ('OPEN','TARGET_REACHED','CLOSED_GAIN','CLOSED_LOSS'):
                summary['opened']+=1
            if status in ('TARGET_REACHED','CLOSED_GAIN','CLOSED_LOSS'):
                summary['closed']+=1
                if (num(a.get('net_return_pct')) or 0)>0:summary['positive']+=1
                else:summary['negative']+=1
                if a.get('target_hit'):summary['targets_reached']+=1
                if (num(a.get('excess_after_cost_pct')) or 0)>0:summary['benchmark_beaten']+=1
            elif status=='NO_ENTRY':summary['not_triggered']+=1
            elif status=='UNVERIFIED':summary['unverified']+=1
            else:summary['waiting']+=1
        else:summary['skipped']+=1
        displayed.append({
            'id':r.get('id'),'symbol':r.get('symbol'),'name':r.get('name'),
            'signal':r.get('signal'),'decision_at':r.get('decision_at'),
            'quote_at':r.get('quote_at'),'reference_price':r.get('reference_price'),
            'buy_ceiling':r.get('buy_ceiling'),'sell_review':r.get('sell_review'),
            'risk':r.get('risk'),'why':r.get('why'),'score':r.get('score'),
            'result':a,'method':r.get('method'),'currency':'USD'
        })
    # The full evidence remains in the git-tracked historical dataset;
    # only a mobile-friendly window is published.
    shown=sorted(displayed,key=lambda r:r.get('decision_at') or '',reverse=True)[:MAX_PUBLIC]
    return {
        'generated_at':stamp(now),'method':METHOD,
        'summary':summary,'records':shown,'published_records':len(shown),
        'legacy_research_flags':len(history.get('calls',[])),
        'rules':{
            'entry':'First observed next-session daily CLOSE at or below frozen buy ceiling, within 14 calendar days',
            'exit':'First later daily CLOSE at or above frozen sell-review price, otherwise first observed close >=30 days after entry',
            'benchmark':'Same-session SPY closing-price return over the exact paper holding period',
            'friction_pct':PRICE_FRICTION_PCT,
            'limits':'Simulated closes, not real fills. Does not know intraday hits, bid/ask spreads, dividends, split adjustments, FX or NZ tax. Old research flags had no preserved buy/sell targets and cannot be back-scored.'
        }
    }
