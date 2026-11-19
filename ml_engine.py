"""Scout weekly supervised learning: frozen observations, benchmark-matched outcomes,
chronological holdout, and conservative deployment. Standard library only.

No historical financial data is backfilled with today's fundamentals. No model is
permitted to alter rankings until actual, independent forward outcomes exist.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
NY = ZoneInfo('America/New_York')
NZ = ZoneInfo('Pacific/Auckland')
SCHEMA = 1
HORIZON_DAYS = 30
BENCHMARK = 'SPY'
FEATURES = ['rules_score','pe','ps','profit_margin','roe','sales_growth',
            'eps_growth','below_high','day_change','debt_to_equity']
MIN_TRAIN = 120
MIN_VALID = 40
MIN_TRAIN_WEEKS = 6
MIN_VALID_WEEKS = 2
MIN_SYMBOLS = 20


def num(value):
    if isinstance(value, bool):
        return None
    try:
        val = float(value)
        return val if math.isfinite(val) else None
    except (ValueError, TypeError):
        return None


def dt(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return parsed.astimezone(UTC) if parsed.tzinfo else None
    except (ValueError, TypeError):
        return None


def stamp(when):
    return when.astimezone(UTC).isoformat(timespec='seconds').replace('+00:00','Z')


def clip(value, lo, hi, default=0):
    v = num(value)
    return max(lo, min(hi, v)) if v is not None else default


def features(candidate, cached, quote):
    """Freeze data as available when a candidate is considered, not later.
    All features have bounded, publicly documented transforms.
    """
    score = num(candidate.get('score'))
    price = num(quote.get('price'))
    metrics = (cached or {}).get('metrics',{})
    if score is None or not price or price<=0:
        return None
    high = num(metrics.get('52WeekHigh'))
    return [round(v, 6) for v in (
        clip(score / 100, 0, 1),
        clip(metrics.get('peTTM'), 0, 100)/100,
        clip(metrics.get('psTTM'), 0, 30)/30,
        clip(metrics.get('netProfitMarginTTM'), -30, 50)/50,
        clip(metrics.get('roeTTM'), -40, 100)/100,
        clip(metrics.get('revenueGrowthTTMYoy'), -60, 100)/100,
        clip(metrics.get('epsGrowthTTMYoy'), -100, 150)/150,
        clip((high-price)/high, -0.3, 0.8) if high and high>0 else 0,
        clip(quote.get('change_pct'), -15, 15)/15,
        clip(metrics.get('totalDebt/totalEquityQuarterly'), 0, 6)/6,
    )]


def add_weekly_observations(history, candidates, quotes, companies, now):
    """At most one immutable, evidence-qualified observation per stock/week.
    Save SPY at the same time. Never infer quotes/fundamentals later.
    """
    hist = history if isinstance(history, dict) else {}
    episodes = list(hist.get('episodes') or [])
    existing = {(r.get('week'),r.get('symbol')) for r in episodes}
    week = (now.astimezone(NZ).date()-timedelta(days=now.astimezone(NZ).weekday())).isoformat()
    qm = {q.get('symbol'):q for q in quotes}
    spy = qm.get(BENCHMARK) or {}
    bprice, bat = num(spy.get('price')), dt(spy.get('price_at'))
    if (not bprice or bprice<=0 or not bat or spy.get('stale') or
        abs((now-bat).total_seconds())>75*3600):
        hist['episodes'] = episodes
        return hist
    for c in candidates:
        sym = c.get('symbol')
        if not sym or (week,sym) in existing or sym==BENCHMARK:
            continue
        q = qm.get(sym) or {}
        price,at = num(q.get('price')),dt(q.get('price_at'))
        if (not price or price<=0 or not at or q.get('stale') or
            abs((now-at).total_seconds())>75*3600 or
            abs((at-bat).total_seconds())>24*3600):
            continue
        feature = features(c,companies.get(sym),q)
        if feature is None:continue
        episodes.append({'week':week,'symbol':sym,'observed_at':stamp(now),
                         'quote_at':stamp(at),'reference_price':price,
                         'benchmark_symbol':BENCHMARK,'benchmark_price':bprice,
                         'benchmark_quote_at':stamp(bat),'score_at_signal':c['score'],
                         'feature_schema':SCHEMA,'features':feature,
                         'quote_source':q.get('source') or 'Finnhub'})
        existing.add((week,sym))
    hist['episodes']=episodes[-11000:]
    return hist


def outcomes(history, now):
    """Calculate only matured 30-day returns using paired same-session USD quotes.
    First observed session 30-39 days after the ORIGINAL recorded entry price.
    Benchmark and stock must be from the exact same NY calendar session.
    """
    daily = defaultdict(dict)
    for row in history.get('daily',[]):
        ts=dt(row.get('price_at'))
        p=num(row.get('price'))
        if not ts or ts>now or not p or p<=0:continue
        day=ts.astimezone(NY).date().isoformat()
        symbol=row.get('symbol')
        if not symbol:continue
        prev=daily[symbol].get(day)
        if not prev or ts>prev[0]:daily[symbol][day]=(ts,p)
    paired=[]
    spy_by_day=daily.get(BENCHMARK,{})
    for ep in history.get('episodes',[]):
        if ep.get('feature_schema')!=SCHEMA or ep.get('benchmark_symbol')!=BENCHMARK:continue
        x=ep.get('features')
        if not isinstance(x,list) or len(x)!=len(FEATURES) or any(num(v) is None for v in x):continue
        start=dt(ep.get('quote_at')); bs=dt(ep.get('benchmark_quote_at'))
        price=num(ep.get('reference_price')); bprice=num(ep.get('benchmark_price'))
        if not start or not bs or not price or not bprice or price<=0 or bprice<=0:continue
        if abs((start-bs).total_seconds())>24*3600:continue
        target=start+timedelta(days=HORIZON_DAYS)
        if now<target:continue
        results=[]
        for day,(ended,end_price) in daily.get(ep['symbol'],{}).items():
            bm=spy_by_day.get(day)
            if not bm:continue
            bench_end,bench_price=bm
            if ended<target or ended>target+timedelta(days=10):continue
            if abs((bench_end-ended).total_seconds())>24*3600:continue
            results.append((ended,end_price,bench_price,day))
        if not results:continue
        end,end_price,bend,day=min(results,key=lambda row:row[0])
        own=(end_price/price-1)*100
        market=(bend/bprice-1)*100
        excess=own-market
        if not all(math.isfinite(v) for v in (own,market,excess)):continue
        # Do not advertise probability estimates from the classifier.
        paired.append({'week':ep['week'],'symbol':ep['symbol'],'features':x,
                       'score':ep['score_at_signal'],'return_pct':round(own,4),
                       'benchmark_return_pct':round(market,4),
                       'excess_pct':round(excess,4),'label':int(excess>1.0),
                       'end_at':stamp(end),'horizon_days':HORIZON_DAYS,
                       'entry_at':ep['quote_at']})
    return sorted(paired,key=lambda r:(r['week'],r['symbol']))


def sigmoid(z):
    z=max(-35.0,min(35.0,z))
    return 1.0/(1.0+math.exp(-z))


def train_logistic(rows):
    """Deterministic L2-regularised logistic regression, batch gradient descent.
    Built from Python stdlib to keep $0 GitHub Actions deployments reproducible.
    """
    n=len(rows)
    weights=[0.0]*len(FEATURES)
    prevalence=sum(r['label'] for r in rows)/n
    b=math.log(max(.025,min(.975,prevalence))/(1-max(.025,min(.975,prevalence))))
    lr=0.23
    for epoch in range(420):
        grad=[0.0]*len(weights)
        gb=0.0
        for row in rows:
            x=row['features']
            p=sigmoid(b+sum(a*v for a,v in zip(weights,x)))
            err=p-row['label']
            gb+=err
            for j,v in enumerate(x):grad[j]+=err*v
        # Conservative shrinkage avoids overfitting to sparse short histories.
        for j in range(len(weights)):
            weights[j]-=lr*(grad[j]/n+0.15*weights[j])
        b-=lr*gb/n
    return {'weights':[round(w,8) for w in weights],'intercept':round(b,8),
            'features':FEATURES,'feature_schema':SCHEMA,'algorithm':'L2 logistic regression (stdlib)',
            'target':'30d USD stock return > SPY return by 1 percentage point (gross, not net)' }


def predict(model,x):
    if model.get('feature_schema')!=SCHEMA or model.get('features')!=FEATURES:return None
    w=model.get('weights') or []
    if len(w)!=len(FEATURES) or len(x)!=len(FEATURES):return None
    b=num(model.get('intercept'))
    if b is None or any(num(v) is None for v in w):return None
    return sigmoid(b+sum(float(a)*float(v) for a,v in zip(w,x)))


def weekly_top_excess(rows, sort_key):
    """Equal-weight each distinct validation week, no pooled pseudo-replication."""
    weeks=defaultdict(list)
    for row in rows:weeks[row['week']].append(row)
    week_results=[]
    for entries in weeks.values():
        k=max(1,round(len(entries)*0.2))
        top=sorted(entries,key=sort_key,reverse=True)[:k]
        week_results.append(sum(r['excess_pct'] for r in top)/len(top))
    return sum(week_results)/len(week_results) if week_results else 0.0


def evaluate_training(history,now,previous=None):
    rows=outcomes(history,now)
    weeks=sorted({r['week'] for r in rows})
    observed=sorted({r['week'] for r in history.get('episodes',[])})
    base={'checked_at':stamp(now),'last_review_week':(now.astimezone(NZ).date()-timedelta(days=now.astimezone(NZ).weekday())).isoformat(),
          'status':'COLLECTING','model_active':False,'recorded_signals':len(history.get('episodes',[])),
          'matured_outcomes':len(rows),'observed_weeks':len(observed),
          'matured_weeks':len(weeks),'horizon_days':HORIZON_DAYS,
          'benchmark':BENCHMARK,'method':'Frozen weekly fundamentals; 30-day paired outcomes vs SPY; chronological holdout; regularized logistic regression.',
          'validation':None,'reason':'Not enough forward outcomes yet.',
          'warning':'Hypothetical USD gross price changes, excluding spreads, commissions, FX, tax and dividends; no guaranteed predictive advantage.'}
    cold={'active':False,'feature_schema':SCHEMA,'features':FEATURES,'trained_at':None}
    if len(weeks)<MIN_TRAIN_WEEKS+MIN_VALID_WEEKS:
        base['reason']=f'Waiting for at least {MIN_TRAIN_WEEKS+MIN_VALID_WEEKS} matured, separate weekly observation cohorts (currently {len(weeks)}).'
        return cold,base
    val_weeks=set(weeks[-MIN_VALID_WEEKS:]);train=[r for r in rows if r['week'] not in val_weeks]
    val=[r for r in rows if r['week'] in val_weeks]
    base['training_samples']=len(train);base['holdout_samples']=len(val)
    if len(train)<MIN_TRAIN or len(val)<MIN_VALID or len({r['symbol'] for r in train})<MIN_SYMBOLS:
        base['reason']=f'Need at least {MIN_TRAIN} training examples, {MIN_VALID} later holdout examples and {MIN_SYMBOLS} unique stocks; currently {len(train)} / {len(val)} / {len({r["symbol"] for r in train})}.'
        return cold,base
    if len({r['label'] for r in train})<2:
        base['reason']='Recorded historical outcomes lack both winners and non-winners; cannot fit a useful classifier.'
        return cold,base
    provisional=train_logistic(train)
    for r in val:r['prediction']=predict(provisional,r['features'])
    model_excess=weekly_top_excess(val,lambda r:r['prediction'])
    rules_excess=weekly_top_excess(val,lambda r:r['score'])
    uplift=model_excess-rules_excess
    base['validation']={'method':'Most recent 2 matured weekly cohorts, unseen during training',
                        'holdout_samples':len(val),'holdout_weeks':sorted(val_weeks),
                        'model_top20_excess_pct':round(model_excess,3),
                        'rules_top20_excess_pct':round(rules_excess,3),
                        'lift_percentage_points':round(uplift,3),
                        'passes_gate':bool(uplift>=0.5 and model_excess>0)}
    if not base['validation']['passes_gate']:
        base['status']='NO VALIDATED EDGE'
        base['reason']='On untouched later weeks, the model did not beat the rules by at least 0.5 percentage points while outperforming SPY. Rules remain in control.'
        return cold,base
    # Only after validation, fit a production model using all matured rows.
    model=train_logistic(rows)
    model.update({'active':True,'trained_at':stamp(now),'training_rows':len(rows),
                  'validated_lift_pp':round(uplift,3),'holdout_weeks':sorted(val_weeks),
                  'notice':'Ranking aid only; output is NOT a calibrated return probability.'})
    base['status']='VALIDATED (LIMITED)';base['model_active']=True
    base['reason']='Recent held-out outcomes cleared the minimum conservative gate; model may reorder research candidates, but not trigger buys.'
    return model,base


def rank_with_model(candidates,companies,quotes,model,now=None):
    """At most 20% weight to validated ML, retaining rules and all risk gates."""
    candidates=[dict(c) for c in candidates]
    if (not model or not model.get('active') or model.get('feature_schema')!=SCHEMA or
        (now is not None and (not dt(model.get('trained_at')) or
          abs((now-dt(model.get('trained_at'))).total_seconds())>20*86400))):
        for c in candidates:c['ranking_score']=c.get('score');c['rank_method']='FINANCIAL RULES'
        return candidates
    qm={q.get('symbol'):q for q in quotes}
    ranked=[]
    for c in candidates:
        if c.get('score') is None:continue
        x=features(c,companies.get(c.get('symbol')),qm.get(c.get('symbol'),{}))
        p=predict(model,x) if x else None
        if p is not None:ranked.append((c,p))
    if len(ranked)<5:
        for c in candidates:c['ranking_score']=c.get('score');c['rank_method']='FINANCIAL RULES'
        return candidates
    ordered=sorted(ranked,key=lambda c:c[1])
    denom=max(1,len(ordered)-1)
    mapping={c['symbol']:100*i/denom for i,(c,p) in enumerate(ordered)}
    for c in candidates:
        score=num(c.get('score'))
        if score is None:c['ranking_score']=None;c['rank_method']='INSUFFICIENT DATA';continue
        ml=mapping.get(c.get('symbol'))
        if ml is None:c['ranking_score']=score;c['rank_method']='FINANCIAL RULES';continue
        c['ml_relative_rank']=round(ml)
        c['ranking_score']=round(.8*score+.2*ml,1)
        c['rank_method']='80% RULES / 20% TESTED ML'
    return candidates
