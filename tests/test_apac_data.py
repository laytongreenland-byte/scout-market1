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

    def test_provider_envelopes_and_fail_closed(self):
        rows=[{'date':'2026-11-20','close':2.5}]
        self.assertEqual(ap.extract_rows({'data':{'bars':rows}}),rows)
        self.assertEqual(ap.extract_rows({'data':{'prices':rows}}),rows)
        self.assertEqual(ap.extract_rows({'data':{'daily':rows}}),rows)
        self.assertEqual(ap.extract_rows({'data':{'history':rows}}),rows)

    def test_nzx_exchange_local_day_not_utc_day(self):
        local_midnight=datetime(2026,11,22,12,15,tzinfo=timezone.utc)
        # NZ is already on 23 Nov, so an exchange-dated 23 Nov
        # observation is not automatically rejected as future-dated.
        row=ap.valid_price([{'date':'2026-11-23','close':3.25}],
                           'NZX','AIR',local_midnight)
        self.assertEqual(row['close'],3.25)

    def test_failed_prices_are_not_marked_as_fetched_or_hammered_hourly(self):
        with patch.dict('os.environ',{'NZXPLORER_API_KEY':'dummy'},clear=True):
            base={'items':[{'market':'NZX','symbol':'AIR'}]}
            fail=lambda sym,key: (_ for _ in ()).throw(RuntimeError('unavailable'))
            result=ap.build(now=NOW,catalog=base,previous={},
                            fetchers={'NZX':fail})
            self.assertEqual(result['markets']['NZX']['status'],'PROVIDER_ERROR')
            self.assertNotIn('NZX',result['fetched_days'])
            self.assertIn('NZX',result['retry_after'])
            next_run=ap.build(now=NOW.replace(hour=19),catalog=base,
                              previous=result,fetchers={'NZX':fail})
            self.assertEqual(next_run['markets']['NZX']['attempted'],0)

    def test_valid_prices_fetched_once_per_day_without_affecting_us(self):
        with patch.dict('os.environ',{'NZXPLORER_API_KEY':'dummy'},clear=True):
            base={'items':[{'market':'NZX','symbol':'AIR'}]}
            good=lambda sym,key:{'data':{'prices':[{'date':'2026-11-20','close':1.2}]}}
            result=ap.build(now=NOW,catalog=base,previous={},
                            fetchers={'NZX':good})
            self.assertEqual(result['markets']['NZX']['valid_this_run'],1)
            self.assertEqual(result['fetched_days']['NZX'],'2026-11-20')
            next_run=ap.build(now=NOW.replace(hour=19),catalog=base,
                              previous=result,fetchers={'NZX':lambda *a: (_ for _ in ()).throw(AssertionError('second fetch'))})
            self.assertEqual(next_run['markets']['NZX']['attempted'],0)
            self.assertEqual(len(next_run['quotes']),1)

if __name__=='__main__': unittest.main()
