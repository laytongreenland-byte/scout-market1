#!/usr/bin/env python3
"""Best-effort GitHub issue notifications, with deduplication and no paid service.

Watching the repo (All Activity) and enabling GitHub push/email notifications is
required for delivery. Creating issues does not guarantee instant delivery.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'data'/'latest.json'


def existing(repo):
    x = subprocess.run(['gh','issue','list','--repo',repo,'--state','all','--limit','100',
                        '--json','title'],capture_output=True,text=True,timeout=30)
    if x.returncode:
        print('::warning::Unable to read GitHub issues: '+x.stderr[:170])
        return None
    try:return {it['title'] for it in json.loads(x.stdout)}
    except (ValueError, KeyError, TypeError):return None


def create(repo,title,body):
    p = subprocess.run(['gh','issue','create','--repo',repo,'--title',title,'--body',body],
                       capture_output=True,text=True,timeout=45)
    if p.returncode:
        print('::warning::Could not create Scout notification: '+p.stderr[:200])
        return False
    print('Created research notification: '+p.stdout.strip())
    return True


def main():
    repo=os.environ.get('GITHUB_REPOSITORY','')
    if not repo or not os.environ.get('GH_TOKEN'):
        print('::notice::GitHub notification service not configured')
        return
    data=json.loads(DATA.read_text())
    research=data.get('research') or {}
    prev=existing(repo)
    if prev is None:
        return
    owner=repo.split('/')[0]
    for alert in research.get('urgent_alerts',[]):
        if alert.get('status')!='URGENT RESEARCH' or not alert.get('source_url'):
            continue
        title=f"[Scout Alert {alert['id']}] {alert['symbol']}: issuer news for review"[:140]
        if title in prev:continue
        body=(f"@{owner}\n\n## Unusual issuer-sourced development — RESEARCH ONLY\n\n"
              f"**{alert['symbol']}** — {alert['headline']}\n\n"
              f"Announcement: {alert['published_at']}\n\n"
              f"Source: {alert['source_url']}\n\n"
              f"Last reported quote: {alert['currency']} {alert['price']} at {alert['quote_time']} (not executable)\n\n"
              f"Change vs previous close: {alert['change_pct']:+.2f}%\n\n"
              f"Rules-based research score: {alert['score']}/100, NOT probability of gain.\n\n"
              f"Why review: {alert['why']}\n\n**Risk:** {alert['risk']}\n\n"
              f"This is not a buy recommendation. Confirm official filing, valuation, spread, NZD FX and taxes.\n")
        if create(repo,title,body):prev.add(title)
    nz = datetime.now(ZoneInfo('Pacific/Auckland'))
    w = research.get('weekly') or {}
    # One notification issue each Monday evening NZ time, with unique title for dedupe.
    if nz.weekday()==0 and nz.hour>=19 and w.get('week_start'):
        title='[Scout Weekly] Research shortlist — '+w['week_start']
        if title not in prev:
            rows=[]
            for c in (w.get('shortlist') or [])[:5]:
                risks='; '.join((c.get('risks') or [])[:2])
                docs=' '.join(e.get('url','') for e in (c.get('evidence') or [])[:2])
                rows.append(f"- **{c['symbol']}** — {c.get('status','WATCH')} ({c.get('score','?')}/100), "
                            f"{c.get('why','')} | Risks: {risks} | Sources: {docs}")
            body=f"@{owner}\n\n## Scout weekly evidence-based research shortlist\n\n"
            body+=f"**Verdict:** {w.get('verdict','No vetted opportunity')}\n\n"
            learning=research.get('learning') or {}
            validation=learning.get('validation') or {}
            body+=(f"**Weekly learning:** {learning.get('status','UNKNOWN')} — "
                  f"{learning.get('recorded_signals',0)} recorded observations, "
                  f"{learning.get('matured_outcomes',0)} matured 30-day outcomes.\n")
            if validation:
                body+=(f"Chronological held-out comparison: ML lift "
                      f"{validation.get('lift_percentage_points','?')} percentage points vs rules "
                      f"on {validation.get('holdout_samples','?')} rows.\n")
            body+='No verified ML improvement means financial rules remain in control.\n\n'
            body+='\n'.join(rows) if rows else 'No sufficiently documented research candidates.'
            body+=(f"\n\nFull screen: https://{owner}.github.io/{repo.split('/')[1]}/\n\n"
                  'Rule-based ranking only, not personalized financial advice. Price/financial reports can lag; ' 
                  'confirm all facts, taxes and fees before investing.\n')
            create(repo,title,body)


if __name__=='__main__':
    try:main()
    except Exception as e:
        print('::warning::Could not deliver optional research notifications: '+type(e).__name__+' '+str(e)[:150])
        sys.exit(0)
