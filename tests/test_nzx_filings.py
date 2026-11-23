import unittest
from datetime import date, datetime, timezone
from nzx_filings import parse
from nzx_fundamentals import build

NOW=datetime(2026,11,23,10,tzinfo=timezone.utc)
CAT={'items':[{'market':'NZX','type':'SHARE','symbol':'AIR','name':'Air New Zealand'}]}
PRICES={'quotes':[{'market':'NZX','currency':'NZD','symbol':'AIR',
                   'close':1.0,'date':'2026-11-23'}]}
MET={'data':{'ticker':'AIR','fiscal_year':2026,'period_type':'ANNUAL',
             'sector':'Industrials','profitability':{'roe':15,'net_margin':12},
             'valuation':{'pe_ratio':15},'growth':{'revenue_growth':8},
             'leverage':{'debt_to_equity':0.5}}}
FILING={'data':[{'title':'AIR Annual Financial Results 2026',
                 'announcement_date':'2026-11-23',
                 'announcement_url':'https://www.nzx.com/announcements/484239',
                 'announcement_id':'484239'},
                {'title':'Untrusted company claim', 'announcement_date':'2026-11-23',
                 'announcement_url':'https://example.com/phishing'}]}
class NZXFilingTests(unittest.TestCase):
    def test_requires_original_nzx_announcement_url_and_date(self):
        out=parse(FILING,date(2026,11,23))
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]['source'],'NZX primary announcement')
        self.assertTrue(out[0]['url'].startswith('https://www.nzx.com/announcements/'))
        self.assertEqual(parse({'data':[dict(FILING['data'][0],announcement_date='2026-11-24')]},
                               date(2026,11,23)),[])

    def test_bounded_filings_and_metrics_with_no_network(self):
        hits=[]
        def metrics(sym,key):
            hits.append(('metrics',sym))
            return MET
        def filings(sym,key):
            hits.append(('filings',sym))
            return FILING
        a=build({},CAT,PRICES,fetcher=metrics,now=NOW,key='dummy',
                limit=4,filing_fetcher=filings)
        self.assertEqual(a['status']['valid_this_scan'],1)
        self.assertEqual(a['status']['filings_with_official_links'],1)
        self.assertEqual(a['companies']['AIR']['announcements'][0]['title'],
                         'AIR Annual Financial Results 2026')
        b=build(a,CAT,PRICES,fetcher=lambda *_:self.fail('recalled metrics'),
                now=NOW,key='dummy',filing_fetcher=lambda *_:self.fail('recalled filings'))
        self.assertEqual(b['status']['status'],'ALREADY_CHECKED')
        self.assertEqual(len(hits),2)
        self.assertEqual(len(b['companies']['AIR']['announcements']),1)

    def test_missing_provider_key_never_fabricates_filing_evidence(self):
        x=build({},CAT,PRICES,key='',now=NOW)
        self.assertEqual(x['status']['status'],'NO_KEY')
        self.assertEqual(x['companies'],{})
if __name__=='__main__':unittest.main()
