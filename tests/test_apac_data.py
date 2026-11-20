import unittest
from datetime import datetime,timezone
from unittest.mock import patch
import apac_data as ap

NOW=datetime(2026,11,20,18,0,tzinfo=timezone.utc)

class ApacDataTests(unittest.TestCase):
    def test_nzx_pricing_is_explicitly_eod_and_currency_specific(self):
        row=ap.valid_price([{'date':'2026-11-20','close':1.25}], 'NZX','AIR',NOW)
        self.assertEqual(row['close'],1.25)
        self.assertEqual(row['currency'],'NZD')
        self.assertTrue(row['research_only'])
        self.assertEqual(row['price_type'],'EOD')
    def test_bad_and_old_prices_not_published(self):
        self.assertIsNone(ap.valid_price([{'date':'2026-11-01','close':3}], 'ASX','BHP',NOW))
        self.assertIsNone(ap.valid_price([{'date':'2026-11-20','close':-10}], 'ASX','BHP',NOW))
        self.assertIsNone(ap.valid_price([{'date':'2026-11-20','last':'10'}], 'ASX','BHP',NOW))
    def test_provider_data_extraction(self):
        self.assertEqual(ap.extract_rows({'data':{'bars':[{'date':'2026-11-20','close':2}]}})[0]['close'],2)
        self.assertEqual(ap.extract_rows({'data':[{'date':'2026-11-20','close':2}]})[0]['close'],2)
    def test_never_scores_or_trades(self):
        with patch.dict('os.environ',{'NZXPLORER_API_KEY':'dummy'},clear=True):
            result=ap.build(now=NOW,catalog={'items':[{'market':'NZX','symbol':'AIR'}]},
                previous={},fetchers={'NZX':lambda symbol,key:{'data':[{'date':'2026-11-20','close':1.2}]}})
        self.assertEqual(result['markets']['NZX']['valid_this_run'],1)
        self.assertEqual(result['quotes'][0]['symbol'],'AIR')
        self.assertNotIn('buy',result)
        self.assertNotIn('recommendations',result)

if __name__=='__main__': unittest.main()
