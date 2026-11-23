#!/usr/bin/env python3
"""Audit prior Scout decisions and report lessons without rewriting history.

This is a transparent post-mortem of frozen paper predictions, not model
training. NZXplorer prohibits using its data to train AI/ML without permission.
The existing separate US walk-forward learner remains in charge of US ML.
"""
from __future__ import annotations

import json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
CLOSED={'TARGET_REACHED','CLOSED_GAIN','CLOSED_LOSS'}
FINAL={'TARGET_REACHED','CLOSED_GAIN','CLOSED_LOSS','NO_ENTRY','UNVERIFIED'}
SKIP={'OBSERVED_AFTER_SKIP'}

def read(path):
    try:
        x=json.loads(path.read_text())
        return x if isinstance(x,dict) else {}
    except (OSError,ValueError):
        return {}

def summarize(records,market):
    frozen=[r for r in records if isinstance(r,dict) and r.get('symbol')]
    status=Counter((r.get('result') or {}).get('status','PENDING') for r in frozen)
    assessed=[r for r in frozen if (r.get('result') or {}).get('status') in CLOSED]
    pnl=[r['result']['net_return_pct'] for r in assessed
         if isinstance((r.get('result') or {}).get('net_return_pct'),(int,float))]
    losses=[r for r in assessed if isinstance((r.get('result') or {}).get('net_return_pct'),(int,float))
            and r['result']['net_return_pct']<0]
    missed=[r for r in frozen if (r.get('result') or {}).get('status')=='NO_ENTRY']
    unverified=[r for r in frozen if (r.get('result') or {}).get('status')=='UNVERIFIED']
    by_version=defaultdict(list)
    for row in assessed:
        id_=str(row.get('id',''))
        method=('v1' if 'PAPER_V1' in id_ else 'v2' if 'PAPER_V2' in id_
                else str(row.get('method') or 'legacy'))
        by_version[method].append(row)
    methods={}
    for method,rows in by_version.items():
        returns=[x['result']['net_return_pct'] for x in rows
                 if isinstance((x.get('result') or {}).get('net_return_pct'),(int,float))]
        distinct_weeks={x.get('week') for x in rows if x.get('week')}
        enough=len(returns)>=12 and len(distinct_weeks)>=6
        methods[method]={'closed':len(returns),'distinct_weeks':len(distinct_weeks),
                         'sufficient_for_a_rule_reassessment':enough,
                         'net_average_pct':round(sum(returns)/len(returns),2) if enough else None}
    return {'market':market,'recorded':len(frozen),'opened':sum(bool((r.get('result') or {}).get('entry'))
                     for r in frozen),
            'closed':len(assessed),'with_verified_return':len(pnl),'losing':len(losses),
            'no_entry':len(missed),'unverified':len(unverified),
            'pending':status.get('WAITING_TO_BUY',0)+status.get('OPEN',0)+status.get('PENDING',0),
            'enough_history_to_adjust_rules':any(x['sufficient_for_a_rule_reassessment']
                                                  for x in methods.values()),
            'method_reviews':methods}

def build(us_latest,nzx_research,nzx_history,now=None):
    now=now or datetime.now(timezone.utc)
    us=(us_latest.get('research') or {}).get('scoreboard') or {}
    us_rows=us.get('records') or []
    nz_rows=nzx_history.get('paper_trades') or []
    us_stat=summarize(us_rows,'US')
    # Scout's public scoreboard intentionally shows a limited recent sample.
    # The published summary covers all frozen USD decisions, so use those
    # authoritative totals rather than mislabeling 120 recent cards as total.
    us_full=us.get('summary') or {}
    us_stat['recent_records_audited']=us_stat['recorded']
    for target,source in [('recorded','recorded'),('opened','opened'),
                          ('closed','closed'),('losing','negative'),
                          ('no_entry','not_triggered'),('unverified','unverified')]:
        value=us_full.get(source)
        if isinstance(value,int) and value>=0:
            us_stat[target]=value
    nz_stat=summarize(nz_rows,'NZX')
    items=[]
    # A process problem can be noticed without labeling an unfinished trade a loss.
    v1=[r for r in nz_rows if str(r.get('id','')).endswith('PAPER_V1')]
    sub_dime=[r for r in v1 if isinstance(r.get('original_price'),(int,float))
              and r['original_price']<0.10]
    if sub_dime:
        items.append({'kind':'PROCESS_CORRECTION','severity':'review',
                      'title':'Earlier NZX penny-share screen was too permissive',
                      'detail':f'{len(sub_dime)} frozen legacy idea(s) were generated below NZ$0.10. A later, more conservative screen now excludes new paper entries at those prices. Original decisions are preserved for accountability.',
                      'evidence_count':len(sub_dime),
                      'verified_profitable_trades':0,
                      'change':'New NZX paper-entry gate requires a price of at least NZ$0.10. This is a risk guardrail, not a proven return advantage.'})
    if not us_stat['closed'] and not nz_stat['closed']:
        items.append({'kind':'OUTCOME_PENDING','severity':'waiting',
                      'title':'No completed paper outcomes yet',
                      'detail':'Scout cannot tell you which selection rules are profitable until later verified closes, costs and sufficient independent weeks have been recorded. It must not call a pending paper idea a win or a mistake.',
                      'evidence_count':0,'change':'Keep collecting outcomes without rewriting the original rules.'})
    for market,rows in [('US',us_rows),('NZX',nz_rows)]:
        for row in rows:
            result=row.get('result') or {}
            state=result.get('status')
            if state=='CLOSED_LOSS':
                items.append({'kind':'LOSING_TRADE','severity':'loss',
                              'market':market,'symbol':row.get('symbol'),'title':market+': '+str(row.get('symbol'))+' lost on paper',
                              'detail':'Original reasoning: '+str(row.get('why') or 'Not recorded')[:380],
                              'original_decision_at':row.get('decision_at'),
                              'observed_net_return_pct':result.get('net_return_pct'),
                              'change':'Investigate which original assumptions failed, and check issuer filings, costs and market-wide movement before changing rules.'})
            if state=='NO_ENTRY':
                items.append({'kind':'MISSED_ENTRY','severity':'neutral',
                              'market':market,'symbol':row.get('symbol'),
                              'title':market+': '+str(row.get('symbol'))+' was never bought on paper',
                              'detail':'The original entry price was not observed in the permitted window. This is neither a successful trade nor a loss.',
                              'original_decision_at':row.get('decision_at'),
                              'change':'Track repeated missed entries by method before adjusting entry thresholds.'})
    max_items=24
    items=items[:max_items]
    matured=us_stat['closed']+nz_stat['closed']
    stage='ENOUGH_DATA_FOR_REVIEW' if (us_stat['enough_history_to_adjust_rules'] or
                                      nz_stat['enough_history_to_adjust_rules']) else 'COLLECTING_OUTCOMES'
    return {
        'schema_version':1,
        'generated_at':now.astimezone(timezone.utc).isoformat().replace('+00:00','Z'),
        'status':stage,
        'description':'Transparent post-mortem review of frozen decisions; no automatic NZX machine learning or real trades.',
        'summary':{'us':us_stat,'nzx':nz_stat,'verified_closed_total':matured,
                   'ready_to_claim_improved_accuracy':False},
        'lessons':items,
        'feedback_policy':{
            'step_1':'Freeze the original score, source evidence, costs, entry and selling rule at the time of decision.',
            'step_2':'Observe later market-session prices and record fills or missed entries, never fill same-day or retrospectively.',
            'step_3':'Explain negative outcomes and missed opportunities, preserving earlier mistakes.',
            'step_4':'Compare at least 12 closed results from six distinct independent weeks per method before proposing any changed selection rule.',
            'step_5':'Keep revised rules in an independent shadow test before allowing them to affect future rankings. Do not train on NZXplorer data without written permission.',
        },
        'licensing':'NZXplorer expressly prohibits training ML/AI on its data without written permission. This is a non-training accountability review only.',
        'limitations':['Closed paper outcomes are not evidence of future investment profits.',
                       'NZX rules have been revised for risk control; no independent validation of an accuracy improvement yet.',
                       'US statistical learning retains its pre-existing independent validation gates.'],
    }

def main():
    result=build(read(DATA/'latest.json'),read(DATA/'nzx_research.json'),
                 read(DATA/'nzx_history.json'))
    out=DATA/'learning_review.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('Scout learning review:',result['status'],result['summary']['verified_closed_total'],
          'completed outcomes,',len(result['lessons']),'auditable lessons')

if __name__=='__main__':main()
