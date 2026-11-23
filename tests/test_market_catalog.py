import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import market_catalog as mc

NOW=datetime(2026,11,20,8,30,tzinfo=timezone.utc)

def listings(source='NASDAQ',count=2100):
    if source=='NASDAQ':
        cols='Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n'
        rows=''.join(f'Z{i:04d}|Example {i} Common Stock|Q|N|N|100|N|N\n' for i in range(count))
        rows+='ZTEST|Fake test issue|Q|Y|N|100|N|N\n'
        rows+='ZWRT|Some company Warrant|Q|N|N|100|N|N\n'
        rows+='ZETF|Example Investment ETF|Q|N|N|100|Y|N\n'
    else:
        cols='ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\n'
        rows=''.join(f'P{i:04d}|Example {i} Common Stock|N|P{i:04d}|N|100|N|P{i:04d}\n' for i in range(count))
        rows+='PBAD|Test issue|N|PBAD|N|100|Y|PBAD\n'
        rows+='POTHER|Example Unit|N|POTHER|N|100|N|POTHER\n'
    return (cols+rows+'File Creation Time: 20261120\n').encode()

class MarketCatalogTests(unittest.TestCase):
    def test_official_directories_parse_and_remove_test_symbols(self):
        nasdaq=mc.parse_listing('NASDAQ',listings('NASDAQ'))
        other=mc.parse_listing('OTHER_US',listings('OTHER_US'))
        self.assertGreaterEqual(len(nasdaq),2100)
        self.assertGreaterEqual(len(other),2100)
        self.assertNotIn('ZTEST',{x['symbol'] for x in nasdaq})
        self.assertNotIn('PBAD',{x['symbol'] for x in other})
        self.assertEqual(next(x for x in nasdaq if x['symbol']=='ZWRT')['type'],'OTHER')
        self.assertEqual(next(x for x in nasdaq if x['symbol']=='ZETF')['type'],'ETF')
        self.assertEqual(next(x for x in other if x['symbol']=='POTHER')['type'],'OTHER')

    def test_reject_truncated_or_bogus_source(self):
        with self.assertRaises(ValueError):
            mc.parse_listing('NASDAQ',b'Symbol|Security Name|Test Issue|ETF\nAAPL|Apple|N|N\n')
        with self.assertRaises(ValueError):
            mc.parse_listing('OTHER_US',listings('NASDAQ'))
        with self.assertRaises(ValueError):
            mc.parse_listing('NASDAQ',b'A'*(mc.MAX_BYTES+1))

    def test_combined_directory_never_claims_sharesies_availability(self):
        m={mc.SOURCES['NASDAQ']:listings('NASDAQ'),mc.SOURCES['OTHER_US']:listings('OTHER_US')}
        with patch.object(mc,'fetch_apac',side_effect=TimeoutError('offline during test')):
            got=mc.build(lambda url:m[url],NOW)
        self.assertEqual(got['status'],'READY')
        self.assertGreater(got['counts']['listed_total'],4000)
        self.assertFalse(got['sharesies_availability_verified'])
        self.assertFalse(got['prices_collected'])
        self.assertFalse(got['valuation_done'])
        self.assertEqual(got['markets']['ASX']['status'],'NOT_CONNECTED')
        self.assertEqual(got['markets']['NZX']['status'],'NOT_CONNECTED')
        self.assertEqual(len(got['items']),len({(x['market'],x['symbol']) for x in got['items']}))

    def test_asx_directory_parser_validates_rows(self):
        csv_data='ASX listed companies\nASX code,Company name,GICS industry group\n'
        csv_data+=''.join(f'{i:04d},Test Company {i},Industrials\n' for i in range(1100))
        result=mc.parse_asx(csv_data.encode())
        self.assertEqual(len(result),1100)
        self.assertTrue(all(x['market']=='ASX' for x in result))
        with self.assertRaises(ValueError):
            mc.parse_asx(b'wrong columns')

    def test_nzx_directory_parser_fails_closed(self):
        rows=[{'ticker':f'N{i:03d}','name':f'Test Company {i}'} for i in range(100)]
        self.assertEqual(len(mc.parse_nzx(json.dumps({'data':rows}).encode())),100)
        self.assertEqual(len(mc.parse_nzx(json.dumps({'data':rows[:3]}).encode())),3)
        # A full authenticated directory may legitimately exceed one 100-row page.
        larger=[{'ticker':f'N{i:03d}','name':f'Test Company {i}'} for i in range(140)]
        self.assertEqual(len(mc.parse_nzx(json.dumps({'data':larger}).encode())),140)
        mapped={r['ticker']:{'name':r['name']} for r in larger}
        self.assertEqual(len(mc.parse_nzx(json.dumps({'data':mapped}).encode())),140)
        oversized=[{'ticker':f'N{i:03d}','name':f'Test Company {i}'} for i in range(351)]
        with self.assertRaises(ValueError):
            mc.parse_nzx(json.dumps({'data':oversized}).encode())

    def test_nzx_unpaginated_provider_response_is_accepted_without_offset_requests(self):
        companies=[{'ticker':f'N{i:03d}','name':f'Test Company {i}'} for i in range(140)]
        def mocked_fetch(url,key=None):
            if url==mc.NZX_FULL:return json.dumps({'data':companies}).encode()
            raise AssertionError('Unnecessary paginated provider request')
        with patch.object(mc,'fetch_apac',side_effect=mocked_fetch),patch.dict('os.environ',{'NZXPLORER_API_KEY':'dummy'},clear=False):
            items,markets,sources=mc.apac_discovery()
        self.assertEqual(markets['NZX']['listed_in_directory'],140)
        self.assertEqual(markets['NZX']['status'],'DISCOVERED')
        self.assertTrue(sources['NZX']['ok'])

    def test_us_count_does_not_include_asx_or_nzx(self):
        m={mc.SOURCES["NASDAQ"]:listings("NASDAQ"),mc.SOURCES["OTHER_US"]:listings("OTHER_US")}
        asx=[{"market":"ASX","symbol":"BHP","name":"BHP","type":"SHARE","exchange":"ASX"}]
        with patch.object(mc,"apac_discovery",return_value=(asx,{
              "ASX":{"status":"DISCOVERED","listed_in_directory":1},
              "NZX":{"status":"NOT_CONNECTED","listed_in_directory":0}},{})):
            report=mc.build(lambda url:m[url],NOW)
        self.assertEqual(report["markets"]["US"]["listed_in_directory"],
                         sum(1 for x in report["items"] if x["market"]=="US"))
        self.assertEqual(report["counts"]["listed_total"],
                         report["markets"]["US"]["listed_in_directory"]+1)

    def test_recent_failed_nzx_check_is_not_repeated_hourly(self):
        now=mc.NOW
        prior={"schema_version":2,"nzx_directory_strategy_version":3,"status":"READY","generated_at":mc.stamp(now-timedelta(hours=2)),
               "markets":{"NZX":{"status":"NOT_CONNECTED","last_attempt_at":mc.stamp(now-timedelta(hours=2))}}}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"market_catalog.json"
            path.write_text(json.dumps(prior))
            with patch.object(mc,"OUT",path),patch.dict("os.environ",{"NZXPLORER_API_KEY":"dummy"},clear=False),patch.object(mc,"build",side_effect=AssertionError("retried too early")):
                self.assertEqual(mc.main(),0)
            self.assertEqual(json.loads(path.read_text()),prior)

    def test_failure_is_explicit_not_silently_full(self):
        with patch.object(mc,'fetch_apac',side_effect=TimeoutError('offline during test')):
            out=mc.build(lambda url:listings('NASDAQ') if url==mc.SOURCES['NASDAQ'] else (_ for _ in ()).throw(TimeoutError()),NOW)
        self.assertEqual(out['status'],'PARTIAL')
        self.assertFalse(out['sources']['OTHER_US']['ok'])
        self.assertTrue(out['sources']['NASDAQ']['ok'])

    def test_failed_refresh_does_not_overwrite_previous_good_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'catalog.json'
            previous={'status':'READY','generated_at':mc.stamp(NOW-timedelta(days=10)),'items':[{'symbol':'SAFE'}]}
            path.write_text(json.dumps(previous))
            with patch.object(mc,'OUT',path),patch.object(mc,'NOW',NOW),patch.object(mc,'build',return_value={'status':'UNAVAILABLE'}):
                self.assertEqual(mc.main(),0)
            self.assertEqual(json.loads(path.read_text()),previous)

    def test_no_broker_credentials_or_orders_or_altered_scan(self):
        self.assertTrue(all('nasdaqtrader.com' in u for u in mc.SOURCES.values()))
        self.assertNotIn('FINNHUB_API_KEY',Path(mc.__file__).read_text())
        self.assertNotIn('data/history.json',Path(mc.__file__).read_text())
        self.assertEqual(mc.OUT.name,'market_catalog.json')

if __name__=='__main__':
    unittest.main()
