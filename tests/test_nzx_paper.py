import unittest
from datetime import date, datetime, timedelta, timezone
import nzx_paper as p
import nzx_fundamentals as f
import nzx_research as nz

BASE=datetime(2026,11,23,8,tzinfo=timezone.utc)
METRIC={'symbol':'AIR','market':'NZX','sector':'Industrials',
        'fiscal_year':2026,'period_type':'FY','retrieved_at':'2026-11-23T07:00:00Z',
        'metrics':{'pe_ratio':14.2,'net_margin':13.0,'roe':17.0,
                   'revenue_growth':10.1,'debt_to_equity':0.7},
        'source_url':'https://nzxplorer.co.nz/companies/air'}
CAT={'items':[{'market':'NZX','type':'SHARE','symbol':'AIR','name':'Air New Zealand'}]}
LATEST={'events':[{'type':'NZX','ticker':None,'title':'[AIR] Interim Financial Results',
                   'published_at':'2026-11-23T06:00:00Z',
                   'url':'https://nzxplorer.co.nz/companies/air'}]}
def quote(d='2026-11-23',price=1.00):
    return {'market':'NZX','currency':'NZD','symbol':'AIR','close':price,
            'date':d,'price_type':'EOD','research_only':True,'source':'NZXplorer'}

class NZXPaperTests(unittest.TestCase):
    def test_financial_period_and_sector_gate(self):
        good=p.score_financials(METRIC,date(2026,11,23))
        self.assertEqual(good['status'],'INVESTIGATE')
        self.assertGreaterEqual(good['score'],75)
        old=dict(METRIC,fiscal_year=2022)
        self.assertIsNone(p.score_financials(old,date(2026,11,23))['score'])
        bank=dict(METRIC,sector='Banking')
        self.assertIsNone(p.score_financials(bank,date(2026,11,23))['score'])

    def test_no_retroactive_fills_and_validated_issuer_news_requirement(self):
        q=quote()
        x=p.plan(q,p.score_financials(METRIC,date(2026,11,23)),True)
        self.assertIsNotNone(x)
        self.assertIsNone(p.plan(q,p.score_financials(METRIC,date(2026,11,23)),False))
        ideas=[dict(symbol='AIR',name='Air New Zealand',price=1.0,price_date='2026-11-23',
                    score=91,price_plan=x)]
        calls=p.new_calls(ideas,{},date(2026,11,23),'2026-11-23')
        rows=[{'symbol':'AIR','date':'2026-11-23','price':0.98}]
        p.settle(calls,rows,date(2026,11,23))
        self.assertEqual(calls[0]['result']['status'],'WAITING_TO_BUY')
        p.settle(calls,rows+[{'symbol':'AIR','date':'2026-11-24','price':1.0}],
                 date(2026,11,24))
        self.assertEqual(calls[0]['result']['status'],'OPEN')
        self.assertEqual(calls[0]['result']['entry']['date'],'2026-11-24')
        self.assertEqual(len(p.new_calls(ideas,{'paper_trades':calls},date(2026,11,24),'2026-11-23')),1)

    def test_outcomes_and_costs_include_losses(self):
        x=p.plan(quote(),p.score_financials(METRIC,date(2026,11,23)),True)
        candidate=dict(symbol='AIR',name='Air New Zealand',price=1.0,price_date='2026-11-23',
                       score=91,price_plan=x)
        calls=p.new_calls([candidate],{},date(2026,11,23),'2026-11-23')
        obs=[{'symbol':'AIR','date':'2026-11-24','price':1.0},
             {'symbol':'AIR','date':'2026-12-26','price':0.90}]
        p.settle(calls,obs,date(2026,12,26))
        self.assertEqual(calls[0]['result']['status'],'CLOSED_LOSS')
        self.assertLess(calls[0]['result']['net_return_pct'],-10)
        self.assertEqual(p.summary(calls)['negative'],1)
        first=calls[0]['result'].copy()
        p.settle(calls,obs+[{'symbol':'AIR','date':'2026-12-27','price':1.5}],
                 date(2026,12,27))
        self.assertEqual(calls[0]['result'],first)

    def test_exit_only_after_a_later_observed_close(self):
        x=p.plan(quote(),p.score_financials(METRIC,date(2026,11,23)),True)
        c=dict(symbol='AIR',name='Air New Zealand',price=1.0,price_date='2026-11-23',
               score=90,price_plan=x)
        calls=p.new_calls([c],{},date(2026,11,23),'2026-11-23')
        p.settle(calls,[{'symbol':'AIR','date':'2026-11-24','price':1.0},
                        {'symbol':'AIR','date':'2026-11-27','price':1.14}],date(2026,11,27))
        self.assertEqual(calls[0]['result']['status'],'TARGET_REACHED')
        self.assertGreater(calls[0]['result']['net_return_pct'],10)

    def test_full_nzx_builder_isolated_from_us_and_existing_watch(self):
        fundamentals={'companies':{'AIR':METRIC}}
        output,h=nz.build(CAT,{'quotes':[quote()]},LATEST,history={},now=BASE,
                          fundamentals=fundamentals)
        self.assertEqual(output['coverage']['financially_scored'],1)
        self.assertEqual(output['paper']['summary']['recorded'],1)
        self.assertEqual(output['paper']['summary']['opened'],0)
        self.assertEqual(h['paper_trades'][0]['currency'],'NZD')
        self.assertEqual(h['calls'][0]['signal'],'PRICE WATCH ONLY')
        self.assertEqual(output['candidates'][0]['price_plan']['signal'],'PAPER ENTRY CANDIDATE')

    def test_ratio_parser_rejects_mismatched_ticker(self):
        raw={'data':{'ticker':'FPH','fiscal_year':2026,'period_type':'FY',
                     'valuation':{'pe_ratio':14}}}
        self.assertIsNone(f.unpack(raw,'AIR',BASE))
        raw['data']['ticker']='AIR'
        raw['data']['profitability']={'roe':0.1,'net_margin':0.1}
        obj=f.unpack(raw,'AIR',BASE)
        self.assertEqual(obj['metrics']['pe_ratio'],14)
        self.assertEqual(obj['fiscal_year'],2026)

if __name__=='__main__':unittest.main()
