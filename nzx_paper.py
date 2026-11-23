"""Forward-only educational NZX paper trading.

An idea is frozen on the day the financial screen runs, a simulated entry
needs a LATER OBSERVED exchange-session close, and an exit needs a still later
observed close. No intraday fills, real orders, backfills, NZX/SPY comparisons,
model training, or claims of an investable strategy.
"""
from __future__ import annotations
from datetime import date, timedelta
from math import floor, isfinite

ROUND_TRIP_FEE_PCT=2.0  # illustrative: 1% per side, excludes spread/dividends/tax
BUDGET_NZD=100.0
ENTRY_WINDOW_DAYS=14
HOLD_DAYS=30
MAX_EXIT_LOOKAHEAD_DAYS=12
MAX_WEEKLY_IDEAS=4

def numeric(x):
    return isinstance(x,(int,float)) and not isinstance(x,bool) and isfinite(x)

def day(s):
    try: return date.fromisoformat(str(s)[:10])
    except (TypeError,ValueError): return None

def fraction_sign(x):
    return numeric(x) and x>0

def score_financials(item,now):
    """Conservative, sector-agnostic educational screen, NOT fair-value analysis.
    
    Unit-ambiguous ratios are used for sign/completeness only, never mapped to
    fabricated 'percent' values. Banks, insurers, REITs and ETFs abstain.
    """
    if not isinstance(item,dict):
        return {'score':None,'status':'INSUFFICIENT DATA','why':'No verified company financial ratios'}
    retrieved=day(item.get('retrieved_at'))
    if not retrieved or (now-retrieved).days>45 or (now-retrieved).days<0:
        return {'score':None,'status':'INSUFFICIENT DATA','why':'Financial metrics are missing or older than 45 days'}
    yr=item.get('fiscal_year')
    if not isinstance(yr,int) or not now.year-2<=yr<=now.year:
        return {'score':None,'status':'INSUFFICIENT DATA','why':'Financial accounting period is not sufficiently recent or documented'}
    sector=str(item.get('sector') or '').lower()
    excluded=('bank','insurance','real estate','reit','investment fund','fund management','biotech')
    if any(x in sector for x in excluded):
        return {'score':None,'status':'SECTOR-SPECIFIC VALUATION NEEDED',
                'why':'A general P/E model is unsuitable for this sector'}
    metrics=item.get('metrics') if isinstance(item.get('metrics'),dict) else {}
    pe=metrics.get('pe_ratio')
    roe=metrics.get('roe')
    profit=metrics.get('net_margin')
    growth=metrics.get('revenue_growth')
    de=metrics.get('debt_to_equity')
    needed=(pe,roe,profit,growth,de)
    if sum(numeric(x) for x in needed)<4 or not numeric(pe) or not numeric(profit) or not numeric(roe):
        return {'score':None,'status':'INSUFFICIENT DATA',
                'why':'Financial evidence needs P/E, profitability, equity return and a fourth ratio'}
    if not 0<pe<=60 or profit<=0 or roe<=0:
        return {'score':None,'status':'QUALITY GATE NOT MET',
                'why':'Weak or unsuitable observed profits, equity return, or earnings multiple'}
    score=15 + (25 if pe<=18 else 18 if pe<=28 else 5)
    score+=15 if fraction_sign(profit) else 0
    score+=15 if fraction_sign(roe) else 0
    score+=12 if fraction_sign(growth) else 0
    score+=8 if numeric(de) and 0<=de<=4 else 0
    score=min(100,score)
    reasons=[f'trailing P/E {pe:.1f}×','reported net profit margin positive',
             'reported return on equity positive']
    if fraction_sign(growth):reasons.append('reported revenue growth positive')
    if numeric(de) and 0<=de<=4:reasons.append('debt/equity metric is available')
    return {'score':score,'status':'INVESTIGATE' if score>=75 else 'WATCH',
            'why':'; '.join(reasons)+'; financial data may be unaudited or dated',
            'fundamentals_at':item.get('retrieved_at'),
            'financial_period':f'{item.get("period_type","")} {yr}',
            'sector':item.get('sector'),'source_url':item.get('source_url'),
            'evidence_metrics_count':sum(numeric(x) for x in needed)}

def plan(quote,screen,has_issuer_filing=False):
    """Testable mechanical entry/exit rule, NOT intrinsic valuation.

    Buy on a subsequent observed close <= 101% of original close,
    review taking profit at +12% from actual simulated entry, otherwise
    close at first observed close on/after day 30. Never sell at unobserved
    prices. The plan is frozen; no re-fitting after seeing outcomes.
    """
    if not quote or not numeric(quote.get('close')) or quote['close']<=0 or        screen.get('status')!='INVESTIGATE' or screen.get('score',0)<75:
        return None
    if quote.get('movement_warning'):return None
    if has_issuer_filing is not True:return None
    price=quote['close']
    return {'method':'financial-screen-plus-primary-filing-v1',
            'signal':'PAPER ENTRY CANDIDATE',
            'entry_ceiling':round(price*1.01,6),
            'exit_multiple':1.12,
            'risk_reference':round(price*0.82,6),
            'budget_nzd':BUDGET_NZD,
            'fee_each_way_pct':ROUND_TRIP_FEE_PCT/2,
            'horizon_days':HOLD_DAYS,
            'currency':'NZD',
            'caution':'Mechanical educational scenario, not fair value or a real buy/sell recommendation.'}

def new_calls(ideas,history,now,week):
    calls=list(history.get('paper_trades',[]))
    existing={(x.get('week'),x.get('symbol')) for x in calls}
    count=sum(x.get('week')==week for x in calls)
    for idea in sorted(ideas,key=lambda x:x.get('score',0),reverse=True):
        if count>=MAX_WEEKLY_IDEAS:break
        symbol=idea.get('symbol')
        if (week,symbol) in existing or not idea.get('price_plan'):continue
        qdate=day(idea.get('price_date'))
        if not qdate or (now-qdate).days>4:continue
        p=idea['price_plan']
        calls.append({'id':f'{week}|NZX|{symbol}|PAPER_V1',
                      'market':'NZX','currency':'NZD','symbol':symbol,
                      'name':idea.get('name'), 'week':week,
                      'signal':'PAPER ENTRY CANDIDATE','decision_at':now.isoformat(),
                      'original_date':idea['price_date'],'original_price':idea['price'],
                      'entry_ceiling':p['entry_ceiling'],'exit_multiple':p['exit_multiple'],
                      'risk_reference':p['risk_reference'],'budget_nzd':p['budget_nzd'],
                      'fee_each_way_pct':p['fee_each_way_pct'],
                      'score':idea['score'],'why':idea.get('why'),
                      'filing_url':idea.get('filing_url'), 'financials_at':idea.get('fundamentals_at'),
                      'financial_period':idea.get('financial_period'),
                      'result':{'status':'WAITING_TO_BUY','reason':'Entry needs a later observed market-session close'}})
        existing.add((week,symbol));count+=1
    return calls

def settle(calls,observations,now):
    bysym={}
    for o in observations:
        if not isinstance(o,dict) or not numeric(o.get('price')) or o['price']<=0:
            continue
        d=day(o.get('date'))
        if not d or d>now:continue
        bysym.setdefault(o.get('symbol'),[]).append(o)
    for rows in bysym.values():
        rows.sort(key=lambda x:x['date'])
    for call in calls:
        if call.get('market')!='NZX' or call.get('signal')!='PAPER ENTRY CANDIDATE':
            continue
        result=call.setdefault('result',{'status':'WAITING_TO_BUY'})
        if result.get('status') in ('TARGET_REACHED','CLOSED_GAIN','CLOSED_LOSS','NO_ENTRY','UNVERIFIED'):
            continue
        signal_day=day(call.get('original_date'))
        if not signal_day:continue
        rows=bysym.get(call['symbol'],[])
        entry=result.get('entry')
        if not isinstance(entry,dict):
            eligible=[o for o in rows if signal_day<day(o['date'])<=signal_day+timedelta(days=ENTRY_WINDOW_DAYS)]
            fill=next((o for o in eligible if o['price']<=call['entry_ceiling']),None)
            if fill:
                shares=floor(call['budget_nzd']/fill['price'])
                if shares<1:
                    result.update(status='UNVERIFIED',reason='Illustrative NZ$100 budget cannot buy one whole share')
                    continue
                entry={'date':fill['date'],'price':fill['price'],'shares':shares}
                result={'status':'OPEN','entry':entry,'reason':'Entered at later observed EOD close, not a live or intraday fill'}
                call['result']=result
            elif now>signal_day+timedelta(days=ENTRY_WINDOW_DAYS):
                result.update(status='NO_ENTRY',reason='Entry ceiling not seen in 14-day observation window')
                continue
            else:
                result.update(status='WAITING_TO_BUY',reason='No subsequent observed close has met frozen entry ceiling')
                continue
        buy_day=day(entry['date'])
        following=[o for o in rows if day(o['date'])>buy_day]
        target=entry['price']*call['exit_multiple']
        take=next((o for o in following if o['price']>=target and
                   day(o['date'])<=buy_day+timedelta(days=HOLD_DAYS)),None)
        horizon=next((o for o in following if
                      buy_day+timedelta(days=HOLD_DAYS)<=day(o['date'])<=
                      buy_day+timedelta(days=HOLD_DAYS+MAX_EXIT_LOOKAHEAD_DAYS)),None)
        finish=take or horizon
        if finish is None:
            if now>buy_day+timedelta(days=HOLD_DAYS+MAX_EXIT_LOOKAHEAD_DAYS):
                result.update(status='UNVERIFIED',reason='No verified exit close within required observation window')
            continue
        # Ignore improbable unadjusted prices until split/merger/dividend data exists.
        if abs(finish['price']/entry['price']-1)>0.60:
            result.update(status='UNVERIFIED',reason='Extreme unadjusted return requires corporate-action review')
            continue
        shares=entry['shares']
        buy=entry['price']*shares
        sell=finish['price']*shares
        buy_fee=buy*call['fee_each_way_pct']/100
        sell_fee=sell*call['fee_each_way_pct']/100
        net=(sell-sell_fee-buy-buy_fee)/(buy+buy_fee)*100
        gross=(sell/buy-1)*100
        state='TARGET_REACHED' if take else 'CLOSED_GAIN' if net>0 else 'CLOSED_LOSS'
        result.update(status=state,exit_date=finish['date'],exit_price=finish['price'],
                      gross_return_pct=round(gross,3),
                      net_return_pct=round(net,3),
                      fees_nzd=round(buy_fee+sell_fee,4),
                      notional_nzd=round(buy,4),
                      reason='Closed at later observed NZX EOD price; fees illustrative, dividends/tax excluded')
    return calls

def summary(calls):
    counts={k:0 for k in ('recorded','opened','closed','positive','negative','waiting',
                          'no_entry','unverified','target_reached')}
    counts['recorded']=len(calls)
    for c in calls:
        state=c.get('result',{}).get('status')
        if state in ('OPEN','TARGET_REACHED','CLOSED_GAIN','CLOSED_LOSS'):counts['opened']+=1
        if state in ('TARGET_REACHED','CLOSED_GAIN','CLOSED_LOSS'):
            counts['closed']+=1
            if c['result'].get('net_return_pct',0)>0:counts['positive']+=1
            else:counts['negative']+=1
        if state=='WAITING_TO_BUY':counts['waiting']+=1
        if state=='NO_ENTRY':counts['no_entry']+=1
        if state=='UNVERIFIED':counts['unverified']+=1
        if state=='TARGET_REACHED':counts['target_reached']+=1
    return counts
