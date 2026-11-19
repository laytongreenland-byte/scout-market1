#!/usr/bin/env python3
"""Weekly Scout learning job; executes inside the existing free GitHub Actions scan.
Runs full training only on Mondays after 19:00 NZ or on an explicit test run.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from ml_engine import evaluate_training, stamp

ROOT=Path(__file__).resolve().parent
HISTORY=ROOT/'data/history.json'
MODEL=ROOT/'data/ml_model.json'
REPORT=ROOT/'data/ml_report.json'


def main(now=None,force=False):
    now=now or datetime.now(timezone.utc)
    nz=now.astimezone(ZoneInfo('Pacific/Auckland'))
    week=(nz.date()-timedelta(days=nz.weekday())).isoformat()
    previous=json.loads(REPORT.read_text()) if REPORT.exists() else {}
    due=(nz.weekday()==0 and nz.hour>=19) or force
    if previous.get('last_review_week')==week and not force:
        print('Scout learning: already reviewed this week; preserving existing model')
        return previous
    if not due and REPORT.exists():
        print('Scout learning: next review Monday NZ evening; outcomes are still being archived')
        return previous
    history=json.loads(HISTORY.read_text()) if HISTORY.exists() else {}
    model,report=evaluate_training(history,now)
    # Initial status is published immediately so the app is never ambiguous.
    # Subsequent training takes place weekly, after sufficient matured outcomes.
    if not due:
        report['reason']='Initial warm-up. '+report['reason']
        report['last_review_week']=None
    MODEL.write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n')
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('Scout learning: '+report['status']+'; samples='+str(report['matured_outcomes'])+
          '; observations='+str(report['recorded_signals'])+
          '; model_active='+str(model.get('active')))
    return report

if __name__=='__main__':
    main(force=os.environ.get('SCOUT_LEARN_FORCE')=='1')
