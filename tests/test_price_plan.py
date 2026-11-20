import unittest
from datetime import datetime, timedelta, timezone
from price_plan import entry_plan

class PricePlanTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,20,10,0,tzinfo=timezone.utc)
        self.quote={'symbol':'ACME','price':100,'price_at':self.now.isoformat(),'currency':'USD'}
        self.company={'updated_at':self.now.isoformat(),'profile':{'industry':'Technology'},
          'metrics':{'peTTM':15,'netProfitMarginTTM':20,'roeTTM':20,
          'revenueGrowthTTMYoy':20,'epsGrowthTTMYoy':25,'marketCapitalization':80000,
          '52WeekHigh':130,'52WeekLow':60}}
        self.candidate={'status':'INVESTIGATE','score':85}

    def get(self, price=100, **kwargs):
        return entry_plan(kwargs.get('candidate',self.candidate),
            dict(self.quote,price=price,**kwargs.get('quote',{})),
            kwargs.get('company',self.company),self.now)

    def test_not_buy_when_price_above_entry(self):
        p=self.get()
        self.assertEqual(p['signal'],'WAIT FOR ENTRY')
        self.assertLess(p['entry_ceiling'],100)
        self.assertGreater(p['exit_review_low'],p['entry_ceiling'])
        self.assertGreater(p['exit_review_high'],p['exit_review_low'])
        self.assertLess(p['bear_case'],p['entry_ceiling'])

    def test_entry_only_after_discount_and_quality(self):
        p=self.get(price=80)
        self.assertEqual(p['signal'],'ENTRY CANDIDATE')
        self.assertGreaterEqual(p['entry_ceiling'],80)
        self.assertLess(p['entry_ceiling'],p['exit_review_low'])

    def test_watch_grade_cannot_trigger_entry(self):
        p=self.get(price=80,candidate=dict(self.candidate,status='WATCH',score=72))
        self.assertNotEqual(p['signal'],'ENTRY CANDIDATE')

    def test_financials_get_no_fake_pe_based_targets(self):
        c=dict(self.company,profile={'industry':'Banking'})
        p=self.get(company=c,price=80)
        self.assertIsNone(p['entry_ceiling'])
        self.assertIn('Sector-specific',p['reason'])

    def test_stale_quote_suppresses_levels(self):
        q={'price_at':(self.now-timedelta(days=8)).isoformat()}
        self.assertIsNone(self.get(quote=q)['entry_ceiling'])

    def test_future_quote_suppresses_levels(self):
        q={'price_at':(self.now+timedelta(hours=3)).isoformat()}
        self.assertIsNone(self.get(quote=q)['entry_ceiling'])

    def test_bad_ratio_and_split_context_are_rejected(self):
        c=dict(self.company,metrics=dict(self.company['metrics'],peTTM=0))
        self.assertIsNone(self.get(company=c)['entry_ceiling'])
        c=dict(self.company,metrics=dict(self.company['metrics'],**{'52WeekHigh':35}))
        self.assertIsNone(self.get(company=c)['entry_ceiling'])

    def test_missing_growth_makes_no_price_prediction(self):
        m=dict(self.company['metrics'])
        m.pop('epsGrowthTTMYoy')
        self.assertIsNone(self.get(company=dict(self.company,metrics=m))['exit_review_low'])

    def test_explicit_method_not_model_prediction(self):
        p=self.get()
        self.assertEqual(p['confidence'],'ILLUSTRATIVE / NOT VALIDATED')
        self.assertIn('not a return forecast',p['horizon'])
        self.assertIn('not analyst consensus',p['caution'].lower())

if __name__=='__main__':
    unittest.main()
