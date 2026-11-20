"""Transparent market/earnings *scenarios*, NOT certified fair values or trade orders.

Inputs are only dated Finnhub quotes, trailing ratio metrics and 52-week price bounds.
Prices are USD and scenarios are hypothetical, not analyst consensus or forecasts.
For sectors where price/earnings is a poor stand-alone valuation tool, withhold levels.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

METHOD_VERSION = 1
RESTRICTED_INDUSTRIES = (
    'bank', 'financial', 'insurance', 'capital markets', 'reit',
    'real estate', 'utility', 'utilities', 'energy', 'oil', 'gas',
    'biotech', 'biotechnology', 'investment'
)

def number(x):
    if isinstance(x, bool):
        return None
    try:
        x = float(x)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None

def age_hours(iso, now):
    try:
        dt = datetime.fromisoformat(str(iso).replace('Z', '+00:00'))
        if not dt.tzinfo:
            return float('inf')
        age = (now.astimezone(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()/3600
        return age if age >= -1/6 else float('inf')
    except (ValueError, TypeError, OverflowError):
        return float('inf')

def entry_plan(candidate, quote, company, now):
    """Conservative screen of illustrative 12-month market-price scenarios.

    A 20%+ margin of safety and a low-half 52-week market cap are required.
    ENTRY CANDIDATE requires existing INVESTIGATE quality gates. Other signals
    are not claims of fair value, projected performance or calibrated odds.
    """
    result = {
        'method_version': METHOD_VERSION, 'signal':'NO RELIABLE PRICE RANGE',
        'entry_ceiling':None,'entry_floor':None,'exit_review_low':None,
        'exit_review_high':None,'bear_case':None,'scenario_upside_pct':None,
        'reason':'Insufficient reliable inputs to estimate an entry or exit scenario.',
        'confidence':'ILLUSTRATIVE / NOT VALIDATED',
        'horizon':'Illustrative 12-month scenario, not a return forecast',
        'method':'Trailing earnings proxy + bounded illustrative earnings growth + fixed scenario P/E; 22% valuation haircut and lower-half 52-week entry cap.',
        'currency':'USD', 'as_of':(quote or {}).get('price_at'),
        'basis':['Finnhub US share quote','Finnhub P/E, growth and 52-week range'],
        'caution':'Not analyst consensus, intrinsic value or an order to buy/sell. Historical growth may not repeat. Excludes dividends, fees, FX and NZ tax.'
    }
    def unavailable(reason):
        result['reason'] = reason
        return result
    company = company or {}
    quote = quote or {}
    metrics = company.get('metrics') or {}
    industry = str((company.get('profile') or {}).get('industry') or '').strip()
    price = number(quote.get('price'))
    score = number((candidate or {}).get('score'))
    if price is None or price<=0 or quote.get('stale') or age_hours(quote.get('price_at'),now)>75:
        return unavailable('Quote is missing, stale or future-dated; no entry price can be calculated.')
    if age_hours(company.get('updated_at'),now)>24*10:
        return unavailable('Company ratios are stale or missing; price range withheld.')
    if score is None or (candidate or {}).get('status') in ('INSUFFICIENT DATA','LOW PRIORITY'):
        return unavailable('Current company screen does not establish a credible entry candidate.')
    if not industry or industry.lower()=='unclassified':
        return unavailable('Industry unavailable; cannot apply this earnings-based method safely.')
    if any(t in industry.lower() for t in RESTRICTED_INDUSTRIES):
        return unavailable('Sector-specific valuation required for '+industry+'; earnings multiple scenario withheld.')
    pe = number(metrics.get('peTTM'))
    revenue_growth = number(metrics.get('revenueGrowthTTMYoy'))
    eps_growth = number(metrics.get('epsGrowthTTMYoy'))
    margin = number(metrics.get('netProfitMarginTTM'))
    cap = number(metrics.get('marketCapitalization'))
    high = number(metrics.get('52WeekHigh'))
    low = number(metrics.get('52WeekLow'))
    if any(x is None for x in (pe,revenue_growth,eps_growth,margin,cap,high,low)):
        return unavailable('Missing P/E, growth, profit, market-cap or 52-week price inputs.')
    if not 6<=pe<=45 or margin<8 or revenue_growth<0 or eps_growth<0 or cap<2000:
        return unavailable('Unstable or unsuitable earnings, growth, valuation or liquidity inputs.')
    if not (low>0 and high>low and low*.70<=price<=high*1.30):
        return unavailable('52-week price bounds conflict with the quote; check for a split or bad data.')
    assumed_growth = round(min(9.0, revenue_growth*.45, eps_growth*.35),2)
    scenario_pe = round(max(12.0,min(23.0, 15.0+min(revenue_growth,30)*.24)),2)
    earnings_proxy = price/pe
    base = earnings_proxy*(1+assumed_growth/100)*scenario_pe
    bull = earnings_proxy*(1+min(18,assumed_growth*1.75)/100)*min(26,scenario_pe*1.15)
    bear = earnings_proxy*.85*max(8,scenario_pe*.68)
    ceiling = min(base*.78, low+.50*(high-low))
    if not (math.isfinite(ceiling) and bear>0 and base>ceiling>0 and bull>base and bear<ceiling):
        return unavailable('Scenario mathematics produced inconsistent or unusable levels.')
    if price<bear*.95:
        signal='POSSIBLE VALUE TRAP'
        reason='Share price is beneath the downside scenario. Verify whether the business has deteriorated.'
    elif (candidate or {}).get('status')=='INVESTIGATE' and score>=80 and price<=ceiling:
        signal='ENTRY CANDIDATE'
        reason='Screened company meets the illustrative entry ceiling. Independently verify current earnings and disclosures before any trade.'
    elif price>=base:
        signal='ABOVE BASE CASE'
        reason='Quote is at or above the illustrative base-case level; no attractive entry indicated.'
    else:
        signal='WAIT FOR ENTRY'
        reason='The current quote has not met the required margin-of-safety and company-quality gates.'
    result.update({
        'signal':signal,'reason':reason,
        'entry_floor':round(max(bear,ceiling*.9),2),
        'entry_ceiling':round(ceiling,2),
        'exit_review_low':round(base,2),
        'exit_review_high':round(bull,2),
        'bear_case':round(bear,2),
        'scenario_upside_pct':round((base/price-1)*100,1),
        'assumptions':{
            'trailing_pe':round(pe,2),
            'earnings_growth_assumed_pct':assumed_growth,
            'scenario_exit_pe':scenario_pe,
            'valuation_haircut_pct':22,
            'market_range_entry_cap':'52-week low + 50% of observed range',
            'metrics_retrieved_at':company.get('updated_at'),
        },
    })
    return result
