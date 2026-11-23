#!/usr/bin/env python3
"""Separate NZX weekly/price-movement research notifications.

No buy/price targets or model training. Does not change the US Issues workflow.
"""
from __future__ import annotations
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from post_reports import create, existing

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'/'nzx_research.json'

def main():
    repo=os.environ.get('GITHUB_REPOSITORY','')
    if not repo or not os.environ.get('GH_TOKEN') or not DATA.exists():
        print('NZX issue notifications unavailable; no market data changed')
        return
    data=json.loads(DATA.read_text())
    if data.get('market')!='NZX' or data.get('currency')!='NZD':
        return
    issued=existing(repo)
    if issued is None:return
    owner=repo.split('/')[0]
    for move in (data.get('alerts') or [])[:5]:
        sym=move.get('symbol')
        day=move.get('price_date')
        if not sym or not day:continue
        title=f'[Scout NZX Movement] {sym} {day} — review only'
        if title in issued:continue
        body=(f'@{owner}\n\n## Verified NZX closing-price movement — research only\n\n'
              f'**{sym}**: {move.get("headline","Large NZD price movement")}.\n\n'
              f'{move.get("why","Check source filings, liquidity and corporate actions.")}\n\n'
              f'Official issuer: {move.get("source_url","https://www.nzx.com/")}\n\n'
              'No buy or sell target is implied. Prices may be affected by dividends, '
              'stock splits, liquidity and delayed reporting; this is not a live trade alert.')
        if create(repo,title,body):issued.add(title)
    nz=datetime.now(ZoneInfo('Pacific/Auckland'))
    weekly=data.get('weekly') or {}
    if nz.weekday()!=0 or nz.hour<19 or not weekly.get('week_start'):
        return
    title='[Scout NZX Weekly] Price/disclosure watch — '+weekly['week_start']
    if title in issued:return
    rows=[]
    for c in (weekly.get('shortlist') or [])[:5]:
        records=' '.join(e.get('url','') for e in (c.get('evidence') or [])[:2])
        quote=f'NZD {c.get("price")} on {c.get("price_date")}' if c.get('price') is not None else 'No price verified'
        rows.append(f'- **NZX:{c["symbol"]}** {c.get("name","")} — {quote}. '
                    f'{c.get("why","")} Sources: {records}')
    body=(f'@{owner}\n\n## NZX research watch — separate from USD models\n\n'
          f'{weekly.get("verdict","No fully validated NZX buy cases.")}\n\n')
    body+='\n'.join(rows) if rows else 'No verified NZX observation this week.'
    body+=('\n\n**No NZX company has been given invented buy/sell targets.** '
           'These are price/disclosure watch notes, not financially ranked '
           'recommendations, profitable paper trades or ML-generated forecasts. '
           'NZXplorer-derived data is not used to train machine-learning models.\n')
    create(repo,title,body)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('::warning::NZX issue notification failed: '+type(exc).__name__)
