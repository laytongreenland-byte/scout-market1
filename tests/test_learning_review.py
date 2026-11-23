import unittest
from datetime import datetime, timezone
from pathlib import Path
import learning_review as learning

NOW=datetime(2026,11,23,9,tzinfo=timezone.utc)

def trade(symbol,status,ret=None,method='PAPER_V2',week='2026-11-23',price=1.2):
    r={'symbol':symbol,'id':week+'|NZX|'+symbol+'|'+method,'market':'NZX',
       'week':week,'original_price':price,'decision_at':week,
       'result':{'status':status}}
    if ret is not None:r['result']['net_return_pct']=ret
    if status in ('OPEN','TARGET_REACHED','CLOSED_LOSS','CLOSED_GAIN'):
        r['result']['entry']={'date':'2026-11-24','price':price}
    return r

class ScoutLearningReview(unittest.TestCase):
    def test_pending_does_not_count_as_winner_or_accuracy(self):
        x=learning.build({'research':{'scoreboard':{'records':[]}}},{},
            {'paper_trades':[trade('BLT','WAITING_TO_BUY',method='PAPER_V1',price=.025)]},NOW)
        self.assertEqual(x['summary']['verified_closed_total'],0)
        self.assertFalse(x['summary']['ready_to_claim_improved_accuracy'])
        self.assertEqual(x['summary']['nzx']['pending'],1)
        titles=[e['title'] for e in x['lessons']]
        self.assertTrue(any('penny-share' in s for s in titles))
        self.assertTrue(any('No completed' in s for s in titles))
        self.assertFalse(any(e['kind']=='LOSING_TRADE' for e in x['lessons']))

    def test_loss_is_not_hid_or_relabelled_as_a_win(self):
        lost=trade('ABC','CLOSED_LOSS',-14.3)
        missed=trade('XYZ','NO_ENTRY')
        us={'research':{'scoreboard':{'records':[{'symbol':'MSFT','result':{'status':'CLOSED_LOSS',
             'net_return_pct':-2.2},'why':'Profit growth weakening'}]}}}
        x=learning.build(us,{}, {'paper_trades':[lost,missed]},NOW)
        self.assertEqual(x['summary']['verified_closed_total'],2)
        self.assertEqual(x['summary']['nzx']['losing'],1)
        self.assertEqual(x['summary']['nzx']['no_entry'],1)
        self.assertTrue(any(e['market']=='US' and e['kind']=='LOSING_TRADE' for e in x['lessons']))
        self.assertTrue(any(e['market']=='NZX' and e['kind']=='MISSED_ENTRY' for e in x['lessons']))

    def test_never_claims_learning_improvement_on_small_sample(self):
        x=learning.build({}, {}, {'paper_trades':[trade('ABC','TARGET_REACHED',14)]},NOW)
        self.assertFalse(x['summary']['nzx']['enough_history_to_adjust_rules'])
        self.assertIsNone(x['summary']['nzx']['method_reviews']['v2']['net_average_pct'])
        self.assertFalse(x['summary']['ready_to_claim_improved_accuracy'])

    def test_visible_dashboard_is_outside_collapsed_home_details(self):
        html=(Path(__file__).resolve().parents[1]/'index.html').read_text()
        self.assertIn('id="nzx-overview"',html)
        self.assertIn('id="nzx-paper"',html)
        self.assertLess(html.index('id="nzx-overview"'),
                        html.index('<details class="scout-more">'))
        self.assertLess(html.index('id="nzx-paper"'),
                        html.index('id="results-list"'))
        self.assertIn('nzx.js?v=',html)
        self.assertIn('style.css?v=',html)

if __name__=='__main__':
    unittest.main()
