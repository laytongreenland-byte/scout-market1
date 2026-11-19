import unittest
from datetime import datetime, timedelta, timezone
import research

class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,20,10,0,tzinfo=timezone.utc)
        self.quote={'symbol':'ACME','price':100.0,'price_at':research.iso(self.now),
                    'previous_close':99,'change_pct':1.01,'currency':'USD'}
        self.cache={'updated_at':research.iso(self.now), 'name':'Acme Test', 'metrics':{
            'netProfitMarginTTM':20,'roeTTM':20,'peTTM':15,'psTTM':3,
            'revenueGrowthTTMYoy':20,'epsGrowthTTMYoy':20,'52WeekHigh':120,'52WeekLow':60}, 'news':[]}

    def test_strong_but_not_buy(self):
        c=research.evaluate('ACME',self.quote,self.cache,self.now)
        self.assertEqual(c['status'],'INVESTIGATE')
        self.assertGreaterEqual(c['score'],76)
        self.assertIn('rules-based', c['limitations'].lower())

    def test_missing_metrics_no_fake_score(self):
        c=research.evaluate('ACME',self.quote,{},self.now)
        self.assertIsNone(c['score'])
        self.assertEqual(c['status'],'INSUFFICIENT DATA')

    def test_stale_quote_no_opportunity(self):
        q=dict(self.quote,price_at=research.iso(self.now-timedelta(days=8)))
        c=research.evaluate('ACME',q,self.cache,self.now)
        self.assertIsNone(c['score'])

    def test_primary_catalyst_requires_issuer_origin(self):
        dt=int(self.now.timestamp())
        raw=[{'headline':'Acme Raises Guidance','datetime':dt,'url':'https://acme.com/news/raise','source':'Acme'},
             {'headline':'Acme Raises Guidance','datetime':dt,'url':'https://random-blog.example/hype','source':'Blog'}]
        n=research.get_news(raw,'ACME',{'weburl':'https://acme.com'},self.now,lambda x:x.startswith('https://'))
        self.assertTrue(n[0]['primary'])
        self.assertFalse(n[1]['primary'])
        c=research.evaluate('ACME',self.quote,dict(self.cache,news=n),self.now)
        alerts=research.urgent_alerts([c],[self.quote],self.now,[])
        self.assertEqual(len(alerts),1)
        self.assertEqual(len(research.urgent_alerts([c],[self.quote],self.now,[alerts[0]['id']])),0)

    def test_unverified_news_not_urgent(self):
        news=[{'headline':'Acme Raises Guidance','url':'https://blog.example/rumour',
               'published_at':research.iso(self.now),'primary':False}]
        c=research.evaluate('ACME',self.quote,dict(self.cache,news=news),self.now)
        self.assertEqual(research.urgent_alerts([c],[self.quote],self.now,[]),[])

    def test_history_no_invented_profit(self):
        c=research.evaluate('ACME',self.quote,self.cache,self.now)
        hist=research.update_history({},[c],[self.quote],self.now)
        self.assertEqual(len(hist['calls']),1)
        self.assertNotIn('return_7d_pct',hist['calls'][0])

if __name__ == '__main__':
    unittest.main()
