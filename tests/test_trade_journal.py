import unittest
from datetime import datetime,timedelta,timezone
from trade_journal import record_decisions,update_results,public_results,result_of,close_index,stamp

UTC=timezone.utc
def at(s):
    return datetime.fromisoformat(s.replace('Z','+00:00'))
def price_row(sym,iso,price):
    return {'symbol':sym,'price_at':iso,'price':price}

class JournalTests(unittest.TestCase):
    def setUp(self):
        self.start=at('2026-11-20T22:00:00Z')
        self.ref='2026-11-20T21:00:00Z'
        self.candidate={
            'symbol':'XYZ','name':'Example Corp','status':'INVESTIGATE',
            'score':86,'as_of':self.ref,'price':84.0,
            'why':'Profits growing; manageable debt',
            'risks':['Forecast earnings may fall'],
            'fundamentals_at':self.ref,
            'price_plan':{'signal':'ENTRY CANDIDATE','entry_ceiling':85,
                         'exit_review_low':115,'bear_case':60,'method_version':1}
        }
        self.start_rows=[
            price_row('XYZ',self.ref,84),
            price_row('SPY',self.ref,700)
        ]

    def initial(self):
        h={'daily':list(self.start_rows)}
        return record_decisions(h,[self.candidate],self.start)

    def add(self,h,iso,price,spy):
        h['daily']+=[price_row('XYZ',iso,price),price_row('SPY',iso,spy)]
        return h

    def test_frozen_price_and_reason_never_change_after_later_scan(self):
        h=self.initial()
        newer=dict(self.candidate,price=70,why='Different thesis',
            price_plan=dict(self.candidate['price_plan'],entry_ceiling=75))
        h=record_decisions(h,[newer],self.start+timedelta(hours=3))
        self.assertEqual(len(h['decisions']),1)
        d=h['decisions'][0]
        self.assertEqual(d['buy_ceiling'],85)
        self.assertEqual(d['reference_price'],84)
        self.assertEqual(d['why'],'Profits growing; manageable debt')
        self.assertEqual(d['decision_at'],stamp(self.start))

    def test_cannot_buy_from_signal_day_close(self):
        h=self.initial()
        market=close_index(h,self.start)
        state=result_of(h['decisions'][0],market,self.start)
        self.assertEqual(state['status'],'WAITING_TO_BUY')

    def test_target_hit_and_spy_outperformance(self):
        h=self.initial()
        self.add(h,'2026-11-23T21:00:00Z',84,702)
        self.add(h,'2026-11-27T21:00:00Z',116,705)
        out=update_results(h,at('2026-11-28T10:00:00Z'))
        result=out['decisions'][0]['sealed_result']
        self.assertEqual(result['status'],'TARGET_REACHED')
        self.assertEqual(result['entry_price'],84)
        self.assertEqual(result['exit_price'],116)
        self.assertTrue(result['net_return_pct']>0)
        self.assertTrue(result['excess_after_cost_pct']>0)
        self.assertEqual(public_results(out,at('2026-11-28T10:00:00Z'))['summary']['positive'],1)

    def test_loss_must_be_shown_not_censored(self):
        h=self.initial()
        self.add(h,'2026-11-23T21:00:00Z',84,702)
        self.add(h,'2026-12-24T21:00:00Z',72,711)
        result=update_results(h,at('2026-12-25T10:00:00Z'))['decisions'][0]['sealed_result']
        self.assertEqual(result['status'],'CLOSED_LOSS')
        self.assertLess(result['net_return_pct'],0)
        self.assertLess(result['excess_after_cost_pct'],0)

    def test_missing_entry_after_14_days_does_not_count_as_losing_trade(self):
        h=self.initial()
        for day,price,spy in [('2026-11-23T21:00:00Z',91,702),
                              ('2026-11-24T21:00:00Z',90,704),
                              ('2026-11-25T21:00:00Z',88,705),
                              ('2026-12-03T21:00:00Z',86,708)]:
            self.add(h,day,price,spy)
        today=at('2026-12-09T12:00:00Z')
        res=public_results(h,today)
        self.assertEqual(res['records'][0]['result']['status'],'NO_ENTRY')
        self.assertEqual(res['summary']['not_triggered'],1)
        self.assertEqual(res['summary']['negative'],0)

    def test_missing_spy_does_not_fake_a_fill(self):
        h=self.initial()
        h['daily'].append(price_row('XYZ','2026-11-23T21:00:00Z',83))
        r=public_results(h,at('2026-11-26T21:00:00Z'))
        self.assertEqual(r['records'][0]['result']['status'],'WAITING_TO_BUY')
        self.assertEqual(r['summary']['opened'],0)

    def test_avoid_or_watch_is_never_scored_as_a_win(self):
        h=self.initial()
        bad=dict(self.candidate,price_plan={'signal':'ABOVE BASE CASE','entry_ceiling':70,'exit_review_low':90})
        h=record_decisions(h,[bad],self.start)
        self.add(h,'2026-12-23T21:00:00Z',110,709)
        today=at('2026-12-24T10:00:00Z')
        out=public_results(h,today)
        skipped=[r for r in out['records'] if r['signal']=='ABOVE BASE CASE'][0]
        self.assertEqual(skipped['result']['status'],'OBSERVED_AFTER_SKIP')
        self.assertGreater(skipped['result']['stock_change_pct'],0)
        self.assertEqual(out['summary']['positive'],0)
        self.assertEqual(out['summary']['skipped'],1)

    def test_no_hindsight_targets_for_old_research_flags(self):
        h={'daily':self.start_rows,'calls':[{'symbol':'XYZ','reference_price':84,'flagged_at':stamp(self.start)}]}
        out=public_results(h,self.start)
        self.assertEqual(out['summary']['recorded'],0)
        self.assertEqual(out['legacy_research_flags'],1)

    def test_terminal_prediction_result_is_sealed(self):
        h=self.initial()
        self.add(h,'2026-11-23T21:00:00Z',84,702)
        self.add(h,'2026-11-27T21:00:00Z',116,705)
        today=at('2026-11-28T10:00:00Z')
        h=update_results(h,today)
        frozen=dict(h['decisions'][0]['sealed_result'])
        h['daily'][-2]['price']=20
        self.assertEqual(update_results(h,today)['decisions'][0]['sealed_result'],frozen)

    def test_stale_candidate_refused(self):
        old=dict(self.candidate,as_of=stamp(self.start-timedelta(days=5)))
        self.assertEqual(record_decisions({},[old],self.start)['decisions'],[])

if __name__=='__main__':
    unittest.main()
