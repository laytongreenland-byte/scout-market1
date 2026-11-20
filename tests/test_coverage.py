import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

import research

ROOT = Path(__file__).resolve().parents[1]


class UniverseCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads((ROOT / "config" / "watchlist.json").read_text())

    def test_nontrivial_sample_and_no_duplicate_symbols(self):
        symbols = self.cfg["us_symbols"]
        self.assertGreaterEqual(len(symbols), 250)
        self.assertLessEqual(len(symbols), 340)
        self.assertEqual(len(symbols), len(set(symbols)))
        self.assertIn("SPY", symbols)
        self.assertIn("AAPL", symbols)

    def test_etfs_are_exact_subset_of_tracked_universe(self):
        symbols = set(self.cfg["us_symbols"])
        etfs = self.cfg["etf_symbols"]
        self.assertEqual(len(etfs), len(set(etfs)))
        self.assertTrue(set(etfs).issubset(symbols))
        self.assertGreaterEqual(len(etfs), 40)
        self.assertIn("VOO", etfs)
        self.assertIn("VTI", etfs)

    def test_financial_screening_excludes_etf_ratios(self):
        now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
        nowiso = research.iso(now)
        quotes = [
            dict(symbol=s, price=100.0, price_at=nowiso, currency="USD")
            for s in ("AAPL", "SPY", "VOO")
        ]
        # No token: only local inputs. No external API request or inferred values.
        public, cache, hist, weekly, errors = research.generate_research(
            ["AAPL", "SPY", "VOO"], quotes, [], {}, {}, {}, "", 
            lambda url: (_ for _ in ()).throw(AssertionError("network forbidden")),
            lambda url: url.startswith("https://"), now,
            etf_symbols=["SPY", "VOO"]
        )
        self.assertEqual(public["universe_size"], 3)
        self.assertEqual(public["equity_universe_size"], 1)
        self.assertEqual(public["etf_universe_size"], 2)
        self.assertEqual(public["screened_with_financials"], 0)
        self.assertEqual(public["candidates"], [])

    def test_scanner_bounded_without_secret_in_frontend(self):
        scanner_text = (ROOT / "scanner.py").read_text()
        self.assertIn("[:720]", scanner_text)
        self.assertIn("discover_sp500()", scanner_text)
        self.assertIn("'quotes_fresh_this_scan':good_quotes", scanner_text)
        self.assertIn("'etf_symbols':etfs", scanner_text)

    def test_compass_and_cache_are_published(self):
        workflow = (ROOT / ".github/workflows/scan.yml").read_text()
        # GitHub Pages publishes root files directly; scanner must not duplicate deployment.
        self.assertNotIn("actions/deploy-pages@", workflow)
        self.assertNotIn("actions/upload-pages-artifact@", workflow)
        self.assertIn("git add data/stocksdeepdive.json data/apac.json", workflow)
        self.assertTrue((ROOT / ".nojekyll").exists())
        self.assertTrue((ROOT / "compass.js").exists())
        self.assertTrue((ROOT / "data" / "research_cache.json").exists())
        html = (ROOT / "index.html").read_text()
        self.assertIn('<script src="./compass.js" defer></script>', html)
        self.assertLess(html.index('src="./compass.js"'), html.index('src="./app.js"'))
        self.assertIn("ScoutCompass.render(data)", (ROOT / "app.js").read_text())


if __name__ == "__main__":
    unittest.main()
