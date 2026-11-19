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
SCHEMA = 2
HORIZON_DAYS = 30
BENCHMARK = 'SPY'
FEATURES = ['rules_score','pe','ps','profit_margin','roe','sales_growth',
            'eps_growth','below_high','day_change','debt_to_equity',
            'missing_pe','missing_ps','missing_margin','missing_roe',
            'missing_sales_growth','missing_eps_growth','missing_high',
            'missing_debt_to_equity']
# Independent validation: 30d labels overlap across nearby weekly cohorts.
# Six holdout weeks separated by five weeks, with six weeks purged before each.
MIN_TRAIN = 250
MIN_HOLDOUT_PER_WEEK = 20
MIN_TRAIN_WEEKS = 20
MIN_VALID_FOLDS = 6
PURGE_WEEKS = 6
HOLDOUT_SPACING_WEEKS = 5
MIN_SYMBOLS = 20
ROUND_TRIP_FRICTION_PCT = 1.0  # illustrative research-only estimate, not an executable fee quote


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
        *(1.0 if num(metrics.get(k)) is None else 0.0
          for k in ('peTTM','psTTM','netProfitMarginTTM','roeTTM',
                    'revenueGrowthTTMYoy','epsGrowthTTMYoy','52WeekHigh',
                    'totalDebt/totalEquityQuarterly')),
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
        # Missing split/dividend-adjusted history: reject extreme changes until
        # confirmed by corporate-action data. Never call a split a 90% loss.
        if abs(own)>60 or abs(market)>40:continue
        # Friction is illustrative; true fees, FX and tax vary by investor.
        net_excess=excess-ROUND_TRIP_FRICTION_PCT
        paired.append({'week':ep['week'],'symbol':ep['symbol'],'features':x,
                       'score':ep['score_at_signal'],'return_pct':round(own,4),
                       'benchmark_return_pct':round(market,4),
                       'excess_pct':round(excess,4),'net_excess_est_pct':round(net_excess,4),
                       'label':int(net_excess>1.0),
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
    """Purged, chronological walk-forward tests on disjoint market weeks.

    The training label of *every* example must be known before its validation
    week's first observation; future observations are never used to tune a past
    holdout. Five-week spacing reduces 30-day label overlap. Passing this test
    is only a limited experimental result, not statistical proof of an edge.
    """
    rows=outcomes(history,now)
    weeks=sorted({r['week'] for r in rows})
    observed=sorted({r['week'] for r in history.get('episodes',[])})
    week_now=(now.astimezone(NZ).date()-timedelta(days=now.astimezone(NZ).weekday())).isoformat()
    base={'checked_at':stamp(now),'last_review_week':week_now,
          'status':'COLLECTING','model_active':False,
          'recorded_signals':len(history.get('episodes',[])),
          'matured_outcomes':len(rows),'observed_weeks':len(observed),
          'matured_weeks':len(weeks),'horizon_days':HORIZON_DAYS,
          'benchmark':BENCHMARK,
          'method':'Frozen weekly fundamentals, 30d matched USD outcomes vs SPY, purged forward-only walk-forward, L2 logistic regression.',
          'validation':None,'reason':'Not enough independent forward results yet.',
          'warning':'Research-only. 1% illustrated round-trip friction, no dividends, FX movements or NZ tax; possible split/corporate-action gaps. No guaranteed predictive advantage.'}
    cold={'active':False,'feature_schema':SCHEMA,'features':FEATURES,'trained_at':None}
    required_weeks=MIN_TRAIN_WEEKS+PURGE_WEEKS+HOLDOUT_SPACING_WEEKS*(MIN_VALID_FOLDS-1)+1
    if len(weeks)<required_weeks:
        base['reason']=f'Need at least {required_weeks} matured weekly cohorts (currently {len(weeks)}) to obtain {MIN_VALID_FOLDS} separated forward tests.'
        return cold,base
    # Use latest six independent test weeks, never their labels to train models
    # used to score those same weeks.
    indexes=list(range(len(weeks)-1,MIN_TRAIN_WEEKS+PURGE_WEEKS-1,-HOLDOUT_SPACING_WEEKS))[:MIN_VALID_FOLDS]
    if len(indexes)<MIN_VALID_FOLDS:
        base['reason']='Not enough non-overlapping validation windows.'
        return cold,base
    fold_results=[]
    for idx in sorted(indexes):
        val_week=weeks[idx]
        # Purge six full weekly cohorts before the test week.
        train_end=weeks[idx-PURGE_WEEKS]
        val_rows=[dict(r) for r in rows if r['week']==val_week]
        cutoff=datetime.fromisoformat(val_week).replace(tzinfo=UTC)
        train=[r for r in rows if r['week']<train_end and
               (dt(r.get('end_at')) is not None and dt(r['end_at'])<cutoff)]
        if (len(train)<MIN_TRAIN or len(val_rows)<MIN_HOLDOUT_PER_WEEK or
            len({r['symbol'] for r in train})<MIN_SYMBOLS or
            len({r['label'] for r in train})<2):
            base['reason']=f'Insufficient point-in-time examples for walk-forward week {val_week}: {len(train)} train, {len(val_rows)} test.'
            base['validation']={'completed_folds':len(fold_results),'required_folds':MIN_VALID_FOLDS}
            return cold,base
        provisional=train_logistic(train)
        for r in val_rows:r['prediction']=predict(provisional,r['features'])
        ml_gross=weekly_top_excess(val_rows,lambda r:r['prediction'])
        rules_gross=weekly_top_excess(val_rows,lambda r:r['score'])
        fold_results.append({'week':val_week,'train_samples':len(train),'test_samples':len(val_rows),
                             'ml_excess_pct':round(ml_gross,4),
                             'rules_excess_pct':round(rules_gross,4),
                             'lift_pp':round(ml_gross-rules_gross,4)})
    lift=sum(f['lift_pp'] for f in fold_results)/len(fold_results)
    gross=sum(f['ml_excess_pct'] for f in fold_results)/len(fold_results)
    baseline=sum(f['rules_excess_pct'] for f in fold_results)/len(fold_results)
    wins=sum(f['lift_pp']>0 for f in fold_results)
    passes=lift>=1.0 and wins>=5 and gross-ROUND_TRIP_FRICTION_PCT>1.0
    base['validation']={'method':'Six chronologically separate, purged walk-forward test weeks; previous 6 weeks excluded from training',
                        'test_weeks':[f['week'] for f in fold_results],
                        'holdout_samples':sum(f['test_samples'] for f in fold_results),
                        'holdout_weeks':[f['week'] for f in fold_results],
                        'independent_test_weeks':len(fold_results),'fold_wins':wins,
                        'model_top20_excess_pct':round(gross,3),
                        'rules_top20_excess_pct':round(baseline,3),
                        'model_est_after_friction_excess_pct':round(gross-ROUND_TRIP_FRICTION_PCT,3),
                        'lift_percentage_points':round(lift,3),
                        'round_trip_friction_assumed_pct':ROUND_TRIP_FRICTION_PCT,
                        'passes_gate':passes,
                        'folds':fold_results}
    if not passes:
        base['status']='NO VALIDATED EDGE'
        base['reason']='The model has not demonstrated sufficiently stable excess performance across six separated, previously unseen weeks. Rules remain in control.'
        return cold,base
    final=train_logistic(rows)
    final.update({'active':True,'trained_at':stamp(now),'training_rows':len(rows),
                  'validated_lift_pp':round(lift,3),'holdout_weeks':[f['week'] for f in fold_results],
                  'notice':'Experimental research re-ranking only. Not a calibrated probability or buy signal.'})
    base['status']='EXPERIMENTAL VALIDATION';base['model_active']=True
    base['reason']='Six purged, separate forward tests passed strict gates. This is preliminary evidence only; future live performance can still fail.'
    return final,base


def rank_with_model(candidates,companies,quotes,model,now=None):
    """At most 10% weight to tested ML, retaining rules and all risk gates."""
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
        c['ranking_score']=round(.9*score+.1*ml,1)
        c['rank_method']='90% RULES / 10% TESTED ML'
    return candidates
