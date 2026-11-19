import unittest
from datetime import datetime,timedelta,timezone
from ml_engine import (features,add_weekly_observations,outcomes,evaluate_training,
                       rank_with_model,train_logistic,predict,FEATURES,SCHEMA)

UTC=timezone.utc
class LearningTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,20,12,0,tzinfo=UTC)
        self.t=self.now.isoformat().replace('+00:00','Z')
        self.c={'symbol':'ACME','status':'WATCH','score':75}
        self.cache={'ACME':{'metrics':{'peTTM':15,'psTTM':3,'netProfitMarginTTM':20,'roeTTM':22,
                                    'revenueGrowthTTMYoy':12,'epsGrowthTTMYoy':20,'52WeekHigh':120,
                                    'totalDebt/totalEquityQuarterly':.3}}}
        self.quotes=[{'symbol':'ACME','price':100,'price_at':self.t,'change_pct':1,'source':'Finnhub'},
                     {'symbol':'SPY','price':400,'price_at':self.t,'source':'Finnhub'}]

    def test_weekly_episode_immutable(self):
        h=add_weekly_observations({},[self.c],self.quotes,self.cache,self.now)
        self.assertEqual(len(h['episodes']),1)
        self.assertEqual(len(h['episodes'][0]['features']),len(FEATURES))
        another=dict(self.c,score=1)
        h=add_weekly_observations(h,[another],self.quotes,self.cache,self.now+timedelta(hours=2))
        self.assertEqual(len(h['episodes']),1)
        self.assertEqual(h['episodes'][0]['score_at_signal'],75)

    def test_no_future_or_unmatched_benchmark(self):
        hist=add_weekly_observations({},[self.c],self.quotes,self.cache,self.now)
        future=self.now+timedelta(days=31)
        hist['daily']=[{'symbol':'ACME','price':110,'price_at':future.isoformat()},
                       {'symbol':'SPY','price':420,'price_at':future.isoformat()}]
        self.assertEqual(outcomes(hist,self.now+timedelta(days=15)),[])
        mature=outcomes(hist,self.now+timedelta(days=32))
        self.assertEqual(len(mature),1)
        self.assertAlmostEqual(mature[0]['excess_pct'],5.0)
        self.assertEqual(mature[0]['label'],1)
        hist['daily'][1]['price_at']=(future+timedelta(days=1)).isoformat()
        self.assertEqual(outcomes(hist,self.now+timedelta(days=32)),[])

    def test_requires_spy(self):
        self.assertEqual(add_weekly_observations({},[self.c],self.quotes[:1],self.cache,self.now)['episodes'],[])

    def test_no_premature_learning(self):
        h=add_weekly_observations({},[self.c],self.quotes,self.cache,self.now)
        model,report=evaluate_training(h,self.now)
        self.assertFalse(model['active'])
        self.assertEqual(report['matured_outcomes'],0)
        self.assertEqual(report['status'],'COLLECTING')

    def test_model_cannot_reorder_without_validation(self):
        cs=[self.c,dict(self.c,symbol='OTHER',score=95)]
        adjusted=rank_with_model(cs,self.cache,self.quotes,{'active':False})
        self.assertEqual([r['ranking_score'] for r in adjusted],[75,95])
        self.assertTrue(all(r['rank_method']=='FINANCIAL RULES' for r in adjusted))

    def test_classifier_learns_from_outcomes(self):
        rows=[]
        for i in range(80):
            x=[0.0]*len(FEATURES);x[0]=0.9 if i%2 else 0.1
            rows.append({'features':x,'label':i%2})
        model=train_logistic(rows)
        lo=[0.0]*len(FEATURES);hi=[0.0]*len(FEATURES)
        lo[0]=.1;hi[0]=.9
        self.assertGreater(predict(model,hi),predict(model,lo))

if __name__=='__main__':unittest.main()

class WalkForwardTests(unittest.TestCase):
    def test_learns_only_after_later_weeks_show_real_lift(self):
        # Artificial TEST DATA: 10 genuinely separate weeks with freeze-time
        # features, 25 symbols and a matched SPY close after each horizon.
        # The signals in this fixture deliberately contradict the rules.
        from ml_engine import evaluate_training
        start=datetime(2025,1,6,19,0,tzinfo=UTC)
        episodes=[]; daily=[]
        for w in range(56):
            entry=start+timedelta(days=w*7)
            end=entry+timedelta(days=31)
            daily.append({'symbol':'SPY','price':101,'price_at':end.isoformat()})
            for i in range(30):
                wins=i%2==0
                symbol=f'TEST{i:02}'
                score=50 if wins else 92
                x=[score/100, 1.0 if wins else 0.0]+[0.0]*(len(FEATURES)-2)
                episodes.append({'week':entry.date().isoformat(),'symbol':symbol,'observed_at':entry.isoformat(),
                                 'quote_at':entry.isoformat(),'reference_price':100,'benchmark_symbol':'SPY',
                                 'benchmark_price':100,'benchmark_quote_at':entry.isoformat(),
                                 'score_at_signal':score,'feature_schema':SCHEMA,'features':x})
                daily.append({'symbol':symbol,'price':112 if wins else 95,'price_at':end.isoformat()})
        model,report=evaluate_training({'episodes':episodes,'daily':daily},start+timedelta(days=56*7+40))
        self.assertTrue(model['active'],report)
        self.assertGreater(report['validation']['lift_percentage_points'],.5)
        self.assertEqual(report['validation']['holdout_samples'],180)
        self.assertEqual(report['validation']['independent_test_weeks'],6)
