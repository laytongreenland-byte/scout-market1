import unittest
from datetime import datetime,timezone
from urllib.error import HTTPError
import stocksdeepdive as s

NOW=datetime(2026,11,21,tzinfo=timezone.utc)
class StocksDeepDiveTests(unittest.TestCase):
    def test_scan_sanitises_values_and_does_not_create_buy_signal(self):
        def provider(path):
            if path=="/scan/asx-200":
                return {"as_of":"2026-11-20","results":[{"ticker":"BHP.AX","name":"BHP",
                    "value_score":86,"quality_score":72,"buy":True}]}
            raise HTTPError(path,401,"Unauthorized",{},None)
        report=s.build(now=NOW,fetch=provider,previous={})
        self.assertEqual(report["status"],"AVAILABLE")
        self.assertEqual(report["scans"]["asx-200"][0]["value_score"],86)
        self.assertNotIn("buy", report["scans"]["asx-200"][0])
        self.assertFalse(report["recommendation_influence"])
        self.assertEqual(report["source_status"]["scan/asx-300"],"HTTP_401")
    def test_broken_api_never_presented_as_working(self):
        def blocked(path):raise HTTPError(path,401,"Unauthorized",{},None)
        report=s.build(now=NOW,fetch=blocked,previous={})
        self.assertEqual(report["status"],"UNAVAILABLE")
        self.assertFalse(report["scans"])
        self.assertEqual(report["fresh_source_count"],0)
    def test_provider_history_requires_date_and_close(self):
        data={"currency":"AUD","points":[{"date":"2026-11-20","close":10},
                                            {"date":"2026-11-21","close":-1}]}
        self.assertEqual(s.slim_history(data,"BHP.AX")["points"],[{"date":"2026-11-20","close":10.0}])
        self.assertIsNone(s.slim_history({"data":[]}, "BHP.AX"))
    def test_no_broker_or_secret_in_endpoint(self):
        with self.assertRaises(ValueError):s.get("/portfolio")
        with self.assertRaises(ValueError):s.get("/scan/private-data")
if __name__=="__main__":unittest.main()
