"""Source-validated NZX announcement metadata for educational company research.

Only retain title, report date and original NZX announcement links from a
bounded, authenticated per-issuer API query. Never copy PDF content, AI analysis,
full issuer databases, or claim that routine notices are positive catalysts.
"""
from __future__ import annotations
from datetime import date
import re
from urllib.parse import urlencode
from apac_data import NZX_ROOT, request

OFFICIAL=re.compile(r'^https://www\.nzx\.com/announcements/[0-9]{3,12}(?:\?.*)?$')

def rows(obj):
    if isinstance(obj,dict): obj=obj.get('data',obj)
    if isinstance(obj,list): return obj
    if isinstance(obj,dict):
        for k in ('announcements','results','items','data'):
            if isinstance(obj.get(k),list):return obj[k]
    return []

def parse(obj,now):
    found={}
    for item in rows(obj):
        if not isinstance(item,dict):continue
        url=str(item.get('announcement_url') or item.get('nzx_url') or '')
        if not OFFICIAL.fullmatch(url):continue
        title=str(item.get('title') or '').strip()
        dt=str(item.get('announcement_date') or item.get('date') or '')[:10]
        try:d=date.fromisoformat(dt)
        except (TypeError,ValueError):continue
        if not 5<=len(title)<=200 or d>now or (now-d).days>730:continue
        found[url]={'title':title[:200], 'date':dt, 'url':url,'source':'NZX primary announcement'}
    return sorted(found.values(),key=lambda x:x['date'],reverse=True)[:5]

def fetch_for(symbol,key):
    qs=urlencode({'ticker':symbol,'limit':5})
    return request(NZX_ROOT+'announcements?'+qs,key)
