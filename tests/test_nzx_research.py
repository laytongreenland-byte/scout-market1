import unittest
from datetime import datetime, timedelta, timezone
import nzx_research as nz

BASE=datetime(2026,11,23,8,0,tzinfo=timezone.utc)
CATALOG={'items':[
    {'market':'NZX','symbol':'AIR','name':'Air New Zealand'},
    {'market':'NZX','symbol':'FPH','name':'Fisher & Paykel Healthcare'},
    {'market':'US','symbol':'AAPL','name':'Apple'},
]}
LATEST={'events':[{'type':'NZX','ticker':'AIR','title':'Half-year result',
                   'url':'https://www.nzx.com/announcements/123456',
                   'published_at':'2026-11-23T03:00:00Z'}]}

def sample(symbol='AIR',day='2026-11-23',price=1.0,change=9.0):
    return {'symbol':symbol,'market':'NZX','currency':'NZD',
            'date':day,'close':price,'price_type':'EOD',
            'source':'NZXplorer','research_only':True,
            'change_pct':change,'previous_close':0.92}

class NZXResearchTests(unittest.TestCase):
    def test_new_zealand_candidates_have_nzd_only_and_no_fake_targets(self):
        output,hist=nz.build(CATALOG,{'quotes':[sample()]},LATEST,now=BASE)
        self.assertEqual(output['coverage']['listed'],2)
        self.assertEqual(output['coverage']['verified_eod'],1)
        self.assertEqual(len(output['candidates']),2)
        air=next(c for c in output['candidates'] if c['symbol']=='AIR')
        fph=next(c for c in output['candidates'] if c['symbol']=='FPH')
        self.assertEqual(air['currency'],'NZD')
        self.assertEqual(air['price'],1)
        self.assertIsNone(air['score'])
        self.assertIsNone(air['price_plan']['entry_ceiling'])
        self.assertIsNone(fph['price'])
        self.assertTrue(air['evidence'])
        self.assertFalse(output['learning']['model_active'])
        self.assertEqual(output['paper']['summary']['paper_trades'],0)
        self.assertEqual(len(hist['observations']),1)
        self.assertEqual(len(hist['calls']),1)

    def test_movement_is_research_alert_not_entry_signal(self):
        out,_=nz.build(CATALOG,{'quotes':[sample()]},LATEST,now=BASE)
        self.assertEqual(len(out['alerts']),1)
        alert=out['alerts'][0]
        self.assertEqual(alert['market'],'NZX')
        self.assertIn('not an issuer-confirmed catalyst',alert['risk'])
        self.assertNotIn('buy',alert)
        self.assertEqual(len(out['weekly']['shortlist']),1)

    def test_no_backfilling_or_doubling_same_week(self):
        x,h=nz.build(CATALOG,{'quotes':[sample()]},LATEST,now=BASE)
        _,later=nz.build(CATALOG,{'quotes':[sample()]},LATEST,history=h,
                         now=BASE+timedelta(hours=1))
        self.assertEqual(len(later['calls']),len(h['calls']))
        self.assertEqual(len(later['observations']),1)
        self.assertNotIn('change_7d_pct',later['calls'][0])

    def test_30_day_price_outcomes_are_forward_only_and_never_fake_trades(self):
        first,h=nz.build(CATALOG,{'quotes':[sample()]},LATEST,now=BASE)
        future=BASE+timedelta(days=32)
        new={'quotes':[sample(day=future.astimezone(nz.NZ).date().isoformat(),
                              price=1.20,change=1.0)]}
        output,h2=nz.build(CATALOG,new,LATEST,history=h,now=future)
        old=next(c for c in h2['calls'] if c['week']==first['weekly']['week_start'])
        self.assertEqual(old['reference_price'],1.0)
        self.assertEqual(old['change_30d_pct'],20.0)
        self.assertEqual(output['paper']['summary']['matured_30d'],1)
        self.assertEqual(output['paper']['summary']['paper_trades'],0)

    def test_bad_eod_records_and_us_names_never_enter_nzx_results(self):
        bad=[sample(symbol='AAPL'),sample(symbol='AIR',price=0),
             dict(sample(),currency='USD'),dict(sample(),research_only=False),
             dict(sample(),date='2026-12-31')]
        out,h=nz.build(CATALOG,{'quotes':bad},LATEST,now=BASE)
        self.assertEqual(out['coverage']['verified_eod'],0)
        self.assertEqual(len(h['observations']),0)
        self.assertFalse(any(c['symbol']=='AAPL' for c in out['candidates']))

if __name__=='__main__':
    unittest.main()
