"""Explainable, rules-based investment *research*; no LLM or trade execution.

Every score is derived from recorded quotes, Finnhub metrics and dated articles.
Missing/old data means no actionable classification. All public output is
research only, not a recommendation to buy or a forecast of returns.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from ml_engine import add_weekly_observations, rank_with_model
from price_plan import entry_plan

UTC = timezone.utc
MARKET_URL = 'https://finnhub.io/docs/api/stock-metrics'
QUOTE_URL = 'https://finnhub.io/docs/api/quote'


def numeric(v):
    if isinstance(v, bool):
        return None
    try:
        n = float(v)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def iso(now):
    return now.astimezone(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


def date_of(value):
    try:
        d = datetime.fromisoformat((value or '').replace('Z', '+00:00'))
        if d.tzinfo is None:
            return None
        return d.astimezone(UTC)
    except (ValueError, TypeError):
        return None


def hours_old(value, now):
    d = date_of(value)
    if not d or d>now+timedelta(minutes=10):
        return float('inf')
    return max(0.0, (now-d).total_seconds()/3600)


def fh_json(endpoint, params, token, fetch):
    if not token:
        raise RuntimeError('Free Finnhub key missing')
    args = dict(params)
    args['token'] = token
    url = 'https://finnhub.io/api/v1/' + endpoint + '?' + urllib.parse.urlencode(args)
    return json.loads(fetch(url))


def headline_relevant(headline, symbol, profile):
    """Cheap high-precision relevance check; better to omit a true story than
    attach a demonstrably unrelated article to an investment candidate."""
    name=str(profile.get('name') or '').strip()
    tokens=[w for w in re.findall(r'[A-Za-z]{4,}',name)
            if w.lower() not in ('incorporated','corporation','holdings',
                                  'company','limited','group','class','international','the')]
    lead=next(iter(tokens),None)
    ticker_match=bool(len(symbol)>=3 and re.search(r'(?<![A-Z0-9])'+re.escape(symbol)+r'(?![A-Z0-9])',headline.upper()))
    name_match=bool(lead and re.search(r'(?i)\b'+re.escape(lead)+r'\b',headline))
    return ticker_match or name_match


def get_news(obj, symbol, profile, now, verified_url):
    if not isinstance(obj, list):
        return []
    host = urllib.parse.urlsplit(str(profile.get('weburl') or '')).hostname or ''
    host = host.lower().removeprefix('www.')
    out=[]
    for n in obj:
        if not isinstance(n, dict):continue
        url=n.get('url')
        timestamp=numeric(n.get('datetime'))
        if not isinstance(url,str) or not verified_url(url) or not timestamp:continue
        when=datetime.fromtimestamp(timestamp,UTC)
        if when>now+timedelta(minutes=10) or now-when>timedelta(days=8):continue
        headline=str(n.get('headline') or '').strip()[:230]
        if not headline or not headline_relevant(headline,symbol,profile):continue
        src_host=(urllib.parse.urlsplit(url).hostname or '').lower().removeprefix('www.')
        primary=bool((host and len(host)>5 and (src_host==host or src_host.endswith('.'+host)))
                     or src_host=='sec.gov' or src_host.endswith('.sec.gov'))
        out.append({'headline':headline,'url':url,
                    'source':str(n.get('source') or 'Finnhub news')[:80],
                    'published_at':iso(when),'primary':primary,'symbol':symbol})
    out.sort(key=lambda n:n['published_at'],reverse=True)
    return out[:5]


def extract_metric(obj):
    if not isinstance(obj, dict):
        return {}
    m = obj.get('metric')
    if not isinstance(m, dict):
        return {}
    fields = ['52WeekHigh','52WeekLow','peTTM','psTTM','netProfitMarginTTM','roeTTM',
              'revenueGrowthTTMYoy','epsGrowthTTMYoy','currentRatioQuarterly',
              'totalDebt/totalEquityQuarterly','freeCashFlowTTM','marketCapitalization']
    return {k:numeric(m.get(k)) for k in fields if numeric(m.get(k)) is not None}


def evaluate(symbol, quote, cached, now):
    """Scores 0..100 only if meaningful metrics exist; never imply calibrated odds."""
    q = quote or {}
    price = numeric(q.get('price'))
    if not price or q.get('stale') or hours_old(q.get('price_at'),now)>75:
        return {'symbol':symbol,'status':'INSUFFICIENT DATA','score':None,
                'why':'Price unavailable or stale','risks':['No timely verified quote'], 'evidence':[], 'as_of':q.get('price_at')}
    metrics = (cached or {}).get('metrics',{})
    updated = (cached or {}).get('updated_at')
    needed = ['peTTM','netProfitMarginTTM','roeTTM','revenueGrowthTTMYoy','52WeekHigh']
    count = sum(numeric(metrics.get(k)) is not None for k in needed)
    if count<4 or hours_old(updated,now)>24*10:
        return {'symbol':symbol,'status':'INSUFFICIENT DATA','score':None,
                'why':'Awaiting sufficient up-to-date company financial metrics',
                'risks':['Financial data incomplete or older than 10 days'], 'evidence':[], 'as_of':q.get('price_at')}
    pe, ps = numeric(metrics.get('peTTM')), numeric(metrics.get('psTTM'))
    margin, roe = numeric(metrics.get('netProfitMarginTTM')),numeric(metrics.get('roeTTM'))
    growth,eps = numeric(metrics.get('revenueGrowthTTMYoy')), numeric(metrics.get('epsGrowthTTMYoy'))
    high = numeric(metrics.get('52WeekHigh'))
    low = numeric(metrics.get('52WeekLow'))
    change=numeric(q.get('change_pct'))
    score = 0
    reasons = []
    risks = []
    industry=(cached or {}).get('profile',{}).get('industry') or 'Unclassified'
    cap=numeric(metrics.get('marketCapitalization'))
    if industry=='Unclassified':
        risks.append('Industry not independently classified; cross-sector scores are not directly comparable')
    if cap is not None and cap<2000: # Finnhub market-cap value is in USD millions
        risks.append('Smaller listed company: liquidity and volatility require extra review')
    if margin is not None:
        score += 12 if margin>=15 else 8 if margin>=8 else 3 if margin>0 else 0
        reasons.append(f'Net profit margin {margin:.1f}% (TTM)')
        if margin <= 0: risks.append('Unprofitable on trailing net margin')
    if roe is not None:
        score += 10 if roe>=15 else 6 if roe>=8 else 2 if roe>0 else 0
        reasons.append(f'Return on equity {roe:.1f}% (TTM)')
    if pe is not None:
        score += 16 if 5<=pe<=24 else 10 if 24<pe<=35 else 4 if 35<pe<=50 else 0
        reasons.append(f'Trailing P/E {pe:.1f}×')
        if pe>40: risks.append('High trailing earnings valuation')
        if pe<=0:risks.append('P/E not meaningful or earnings weak')
    if ps is not None:
        score += 6 if 0<ps<=5 else 3 if ps<=10 else 0
        if ps>12: risks.append('High sales multiple')
    if growth is not None:
        score += 15 if growth>=12 else 11 if growth>=5 else 5 if growth>=0 else 0
        reasons.append(f'TTM revenue growth {growth:.1f}% YoY')
        if growth<0: risks.append('Revenue contracting year on year')
    if eps is not None:
        score += 8 if eps>=15 else 5 if eps>=5 else 2 if eps>=0 else 0
        if eps < -10: risks.append('Earnings per share declining')
    if high and high>price:
        distance=(high-price)/high*100
        score += 12 if 8<=distance<=30 else 8 if distance<8 or 30<distance<=45 else 2
        reasons.append(f'{distance:.1f}% below reported 52-week high')
        if distance>45:risks.append('Large drawdown: recovery is not assured')
    elif high:
        score += 4
        risks.append('At or above reported 52-week high')
    if low and low>0 and price<low*1.05:
        risks.append('Price near reported 52-week low')
    if change is not None:
        score += 7 if -2 <= change <=3 else 4 if -5<=change<=5 else 0
        if abs(change)>=6: risks.append(f'Large one-session price move ({change:+.1f}%)')
    # Score deliberately never incorporates news keyword sentiment as an assurance of value.
    score = max(0,min(100,round(score)))
    if pe is None or growth is None or margin is None or high is None:
        status='WATCH'
        risks.append('Important valuation or growth evidence missing')
    elif score>=76 and not (pe>40 or margin<=0 or growth<0 or (cap is not None and cap<2000) or (change is not None and abs(change)>=8)):
        status='INVESTIGATE'
    elif score>=58:
        status='WATCH'
    else:
        status='LOW PRIORITY'
    if not risks:
        risks=['Company-specific, sector and market drawdowns remain possible']
    evidence = [{'label':'Quote (USD)', 'value':f'${price:.2f}', 'timestamp':q.get('price_at'),'url':QUOTE_URL},
                {'label':'Finnhub financial metrics','value':f'{count}/5 fields; retrieval time, not accounting period',
                 'timestamp':updated,'url':MARKET_URL}]
    if cached and cached.get('news'):
        n=cached['news'][0]
        evidence.append({'label':'Latest company-related article','value':n['headline'],
                         'timestamp':n['published_at'],'url':n['url']})
    return {'symbol':symbol,'name':(cached or {}).get('name') or symbol,'status':status,
            'score':score,'industry':industry,'why':'; '.join(reasons[:4]),'risks':risks[:4],
            'evidence':evidence,'as_of':q.get('price_at'),'fundamentals_at':updated,
            'price':price,'currency':'USD', 'change_pct':change, 'news':(cached or {}).get('news',[])[:2],
            'data_quality':'Partial' if count<5 else 'Measured 5/5 core fields',
            'limitations':'Rules-based ranking; financial metrics may refer to older accounting periods; retrieved time is not filing date. Cross-sector scores are imperfect; no intrinsic-value estimate.'}


def primary_catalysts(candidate, now):
    # An independently dated issuer-originating article with very specific good news.
    words=('raises guidance','raised guidance','raises outlook','raised outlook',
           'upgrades guidance','increases guidance','wins major contract',
           'awarded major contract','secures major contract')
    return [n for n in candidate.get('news',[])
            if n.get('primary') and hours_old(n.get('published_at'),now)<=36
            and any(w in n.get('headline','').lower() for w in words)]


def urgent_alerts(candidates, quotes, now, previous_ids):
    """Narrow attention alerts, NOT buy alerts. Avoid chasing news spikes."""
    result=[]
    old=set(previous_ids or [])
    qmap={q.get('symbol'):q for q in quotes}
    for c in candidates:
        if c.get('status')!='INVESTIGATE' or c.get('score',0)<80:
            continue
        q=qmap.get(c['symbol'],{})
        move=numeric(q.get('change_pct'))
        if move is None or not -3<=move<=5 or hours_old(q.get('price_at'),now)>15:
            continue
        for n in primary_catalysts(c,now):
            ident=hashlib.sha256((c['symbol']+'|'+n['url']).encode()).hexdigest()[:18]
            if ident in old:
                continue
            result.append({'id':ident,'symbol':c['symbol'],'headline':n['headline'],
                           'published_at':n['published_at'],'score':c['score'],'status':'URGENT RESEARCH',
                           'source_url':n['url'],'quote_time':q.get('price_at'),'price':c['price'],
                           'currency':'USD', 'change_pct':move,
                           'why':'Issuer-originated specific catalyst plus strong screened fundamentals; check valuation and filing details immediately.',
                           'risk':'Not a buy signal. Price may already reflect news; verify issuer announcement, liquidity and execution price.'})
    return result[:5]


def update_history(history, candidates, quotes, now, companies=None):
    """Archive verified NY session quotes and freeze full-universe weekly features.

    Saved observations support later forward evaluation; they cannot be backfilled
    with today's fundamental information.
    """
    hist = dict(history) if isinstance(history,dict) else {}
    days=list(hist.get('daily',[]))
    calls=list(hist.get('calls',[]))
    qm={q.get('symbol'):q for q in quotes}
    for sym,q in qm.items():
        p=numeric(q.get('price'))
        at=date_of(q.get('price_at'))
        if not p or p<=0 or not at or q.get('stale') or hours_old(q.get('price_at'),now)>75:
            continue
        date=at.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        # The newest quote for the same source market-session replaces an older
        # observation, rather than counting repeated hourly scans as new cases.
        matching=next((i for i,d in enumerate(days) if d.get('symbol')==sym and
                       (date_of(d.get('price_at')).astimezone(ZoneInfo('America/New_York')).date().isoformat()
                        if date_of(d.get('price_at')) else d.get('date'))==date),None)
        row={'date':date,'symbol':sym,'price':p,'price_at':iso(at),'currency':'USD'}
        if matching is None:days.append(row)
        elif not date_of(days[matching].get('price_at')) or at>=date_of(days[matching].get('price_at')):
            days[matching]=row
    days=[d for d in days if (now.date()-date_of(d.get('price_at')).date()).days<=440
          if date_of(d.get('price_at'))]
    week=(now.astimezone(ZoneInfo('Pacific/Auckland')).date()-timedelta(days=now.astimezone(ZoneInfo('Pacific/Auckland')).weekday())).isoformat()
    current={(r.get('week'),r.get('symbol')) for r in calls}
    for c in candidates:
        if c.get('status')!='INVESTIGATE' or (week,c['symbol']) in current:continue
        q=qm.get(c['symbol'],{})
        if q.get('stale') or hours_old(q.get('price_at'),now)>75:continue
        calls.append({'week':week,'symbol':c['symbol'],'flagged_at':iso(now),
                      'reference_price':c['price'],'score':c['score'],'price_at':q.get('price_at')})
    for c in calls:
        ref=numeric(c.get('reference_price'))
        flagged=date_of(c.get('flagged_at'))
        if not ref or not flagged:continue
        for horizon in (7,30):
            k=f'return_{horizon}d_pct'
            if k in c:continue
            target=flagged+timedelta(days=horizon)
            found=[d for d in days if d.get('symbol')==c['symbol'] and date_of(d.get('price_at'))
                   and target<=date_of(d.get('price_at'))<=target+timedelta(days=10)]
            if found:
                d=min(found,key=lambda v:v['price_at'])
                pct=(d['price']/ref-1)*100
                # We have unadjusted free quotes; do not present likely stock
                # splits or bad ticks as exceptional performance.
                if abs(pct)>60:
                    c['return_unverified']='Extreme price change requires split/corporate-action validation'
                else:
                    c[k]=round(pct,2)
                    c[k+'_observed_on']=d['date']
    hist['daily']=days[-25000:]
    hist['calls']=calls[-1000:]
    return add_weekly_observations(hist,candidates,quotes,companies or {},now)


def generate_research(symbols, quotes, events, prev_cache, prev_history, prev_summary, token, fetch, verified_url, now, ml_model=None, ml_report=None, etf_symbols=None):
    cache=dict(prev_cache) if isinstance(prev_cache,dict) else {}
    data=dict(cache.get('companies',{}))
    etfs=set(etf_symbols or ('VOO','VTI','VT','QQQ','SPY','SCHD','IVV','VEA','VWO'))
    equities=[x for x in symbols if x not in etfs]
    idx=int(cache.get('cursor') or 0)%max(1,len(equities))
    batch=[equities[(idx+i)%len(equities)] for i in range(min(12,len(equities)))]
    problems=[]
    processed=0
    if token and os.environ.get('SCOUT_OFFLINE') != '1':
        for sym in batch:
            old=data.get(sym,{})
            try:
                m=extract_metric(fh_json('stock/metric',{'symbol':sym,'metric':'all'},token,fetch))
                if not m:raise ValueError('No metric data')
                if not old.get('profile') or not old.get('profile',{}).get('industry'):
                    try:
                        profile=fh_json('stock/profile2',{'symbol':sym},token,fetch)
                        if isinstance(profile,dict) and profile.get('weburl'):
                            old['profile']={'weburl':profile.get('weburl'),'industry':str(profile.get('finnhubIndustry') or 'Unclassified')[:80], 'name':str(profile.get('name') or sym)[:110]}
                            old['name']=str(profile.get('name') or sym)[:110]
                    except Exception as ex:
                        problems.append(sym+' profile: '+type(ex).__name__)
                date_from=(now-timedelta(days=8)).date().isoformat()
                date_to=now.date().isoformat()
                news=[]
                try:
                    n=fh_json('company-news',{'symbol':sym,'from':date_from,'to':date_to},token,fetch)
                    news=get_news(n,sym,old.get('profile',{}),now,verified_url)
                except Exception as ex:
                    problems.append(sym+' news: '+type(ex).__name__)
                    news=old.get('news',[])
                data[sym]={'metrics':m,'updated_at':iso(now),'name':old.get('name',sym),'profile':old.get('profile',{}),'news':news}
                processed+=1
            except Exception as ex:
                problems.append(sym+' metrics: '+type(ex).__name__)
        idx=(idx+len(batch))%max(1,len(equities))
    # Clean older cached articles too, so old, unrelated headlines don't remain
    # attached to a candidate until its next scheduled fundamentals refresh.
    for sym,entry in data.items():
        if isinstance(entry,dict):
            profile=dict(entry.get('profile') or {})
            profile['name']=profile.get('name') or entry.get('name','')
            entry['news']=[n for n in entry.get('news',[])
                           if headline_relevant(n.get('headline',''),sym,profile)]
    # Profile data isn't required for rankings. News is treated as secondary until
    # a verified issuer host is recorded; do not guess primary-source provenance.
    quote_map={x.get('symbol'):x for x in quotes}
    candidates=[evaluate(s,quote_map.get(s),data.get(s),now) for s in equities]
    # Price scenarios do not bypass quality gates or influence ML outcome labels.
    for candidate in candidates:
        sym=candidate['symbol']
        candidate['price_plan']=entry_plan(candidate,quote_map.get(sym),data.get(sym),now)
    candidates=rank_with_model(candidates,data,quotes,ml_model or {},now)
    ranked=sorted([c for c in candidates if c.get('score') is not None],
                  key=lambda c:c.get('ranking_score') if c.get('ranking_score') is not None else c['score'],reverse=True)
    serious=[c for c in ranked if c['status']=='INVESTIGATE']
    entry_candidates=[c for c in ranked if c.get('price_plan',{}).get('signal')=='ENTRY CANDIDATE']
    priced=[c for c in ranked if c.get('price_plan',{}).get('entry_ceiling') is not None]
    entry_watch=sorted(priced,key=lambda c:c['price']/max(.01,c['price_plan']['entry_ceiling']))[:8]
    # Avoid a shortlist dominated by several closely related businesses.
    # Sector classifications are broad and incomplete; never claim diversification.
    shortlist=[]
    sectors={}
    for c in serious + [c for c in ranked if c['status']=='WATCH']:
        group=c.get('industry') or 'Unclassified'
        if group!='Unclassified' and sectors.get(group,0)>=2:
            continue
        shortlist.append(c)
        sectors[group]=sectors.get(group,0)+1
        if len(shortlist)>=5:break
    # A shortlist is still useful when no company qualifies for consideration.
    week_monday=(now.astimezone(ZoneInfo('Pacific/Auckland')).date()-timedelta(days=now.astimezone(ZoneInfo('Pacific/Auckland')).weekday())).isoformat()
    prev=prev_summary if isinstance(prev_summary,dict) else {}
    if prev.get('week_start')==week_monday and prev.get('shortlist') and prev.get('method_version')==4:
        weekly=prev
    else:
        weekly={'week_start':week_monday,'generated_at':iso(now),'method_version':4,'shortlist':shortlist,
                'verdict':'Candidates for independent investigation, NOT buy instructions' if serious else 'No sufficiently strong purchase case; watchlist only',
                'method':'Rules-based financial screening of the configured US universe, with approximate industry concentration limit; not AI-generated financial advice.',
                'basis':'Finnhub quote and last reported company metrics; excludes fees, FX and NZ tax. Verify before trading.',
                'core_etfs':[s for s in symbols if s in ('VT','VTI','VOO','SPY','QQQ')],
                'note':'Broad diversified funds may suit long-term investing; a high score does not prove an undervalued company.'}
    alerts=urgent_alerts(candidates,quotes,now,[])
    history=update_history(prev_history,candidates,quotes,now,data)
    # Live ML progress must reflect freshly frozen observations, not the stale
    # Monday-only training report.
    learning=dict(ml_report or {})
    learning['recorded_signals']=len(history.get('episodes',[]))
    learning['observed_weeks']=len({r.get('week') for r in history.get('episodes',[])})
    # Read-only observed outcomes: training is still strictly weekly.
    from ml_engine import outcomes
    completed=outcomes(history,now)
    learning['matured_outcomes']=len(completed)
    learning['matured_weeks']=len({r['week'] for r in completed})
    paper={'matured_outcomes':len(completed),'matured_weeks':learning['matured_weeks'],
           'benchmark':'SPY','measurement':'Top 20% highest rules scores of each matured week, measured against SPY over ~30 days; USD price changes only',
           'estimate_round_trip_friction_pct':1.0,'sufficient_for_comparison':False}
    weekly_returns={}
    for item in completed:
        weekly_returns.setdefault(item['week'],[]).append(item)
    top_cohort_excess=[]
    for wk,items in weekly_returns.items():
        if len(items)<20:continue
        top=sorted(items,key=lambda z:z['score'],reverse=True)[:max(1,round(len(items)*.2))]
        top_cohort_excess.append(sum(z['excess_pct'] for z in top)/len(top))
    paper['usable_rule_weeks']=len(top_cohort_excess)
    if top_cohort_excess:
        top_cohort_excess.sort()
        paper['mean_excess_pct']=round(sum(top_cohort_excess)/len(top_cohort_excess),3)
        paper['median_excess_pct']=round(top_cohort_excess[len(top_cohort_excess)//2],3)
        paper['positive_excess_fraction']=round(sum(x>0 for x in top_cohort_excess)/len(top_cohort_excess),3)
    if len(top_cohort_excess)>=12 and len(completed)>=240:
        paper['sufficient_for_comparison']=True
    cache={'companies':data,'cursor':idx,'updated_at':iso(now)}
    mov=[{'symbol':q['symbol'],'change_pct':q.get('change_pct'),'price':q.get('price'),'price_at':q.get('price_at')}
         for q in quotes if isinstance(q.get('change_pct'),(int,float)) and abs(q['change_pct'])>=4 and not q.get('stale') and hours_old(q.get('price_at'),now)<=75]
    mov.sort(key=lambda q:abs(q['change_pct']),reverse=True)
    public={'generated_at':iso(now),'universe_size':len(symbols),'equity_universe_size':len(equities),
            'etf_universe_size':len(etfs),
            'screened_with_financials':sum(c.get('score') is not None for c in candidates),
            'updated_company_metrics_this_scan':processed,'candidates':ranked[:20],
            'entry_candidates':entry_candidates[:8],'entry_watch':entry_watch,
            'pricing_method':'Illustrative 12-month earnings-multiple and 52-week-range scenarios; not analyst consensus, proven fair value or automated trade instructions.',
             'daily_movers':mov[:20],'weekly':weekly,'urgent_alerts':alerts,
            'learning':learning or {'status':'COLLECTING','reason':'Waiting for initial learning report','model_active':False},
            'paper_diagnostics':paper,
            'research_log':history['calls'][-50:],
            'limitations':['No guaranteed real-time prices or complete market coverage.',
                           'Machine learning can influence at most 10% of rankings only after six purged, separated forward tests; no probabilities of gains.',
                           'Latest available financial data may be delayed or incomplete; timestamps and quality gates apply.',
                           'Entry and exit review zones are bounded earnings-multiple scenarios, not analyst price targets, proven fair values or guaranteed returns.',
                            'Do not trade based solely on Scout; verify issuer filings, market conditions and NZ trading costs.',
                            'Reference returns in the log exclude transaction fees, spreads, FX, tax and dividends.']}
    return public,cache,history,weekly,problems
