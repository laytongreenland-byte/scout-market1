import unittest
from unittest.mock import patch
import scanner


class ScannerTests(unittest.TestCase):
    def test_rss_and_atom_parsing(self):
        rss=b'''<rss><channel><item><title>Company profit upgrade</title><link>https://example.com/a</link><pubDate>Thu, 19 Nov 2026 08:45:00 GMT</pubDate></item></channel></rss>'''
        atom=b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Filing</title><link href="https://example.com/b"/><updated>2026-11-19T08:45:00Z</updated></entry></feed>'''
        self.assertEqual(scanner.feed_items(rss)[0]['published_at'], '2026-11-19T08:45:00Z')
        self.assertEqual(scanner.feed_items(atom)[0]['url'], 'https://example.com/b')

    def test_primary_origin(self):
        self.assertTrue(scanner.primary_site('https://www.sec.gov/example'))
        self.assertTrue(scanner.primary_site('https://announcements.nzx.com/'))
        self.assertFalse(scanner.primary_site('https://fake-sec.gov.test/'))
        self.assertFalse(scanner.primary_site('javascript:alert(1)'))

    def test_only_strong_primary_events_become_priorities(self):
        items = [dict(id='x', ticker='ABC', type='NZX', title='Guidance raised', sentiment='positive', primary=True,
                      published_at=scanner.stamp(scanner.NOW), url='https://announcements.nzx.com/a'),
                 dict(id='y', ticker='ABC', type='NZX', title='Guidance raised', sentiment='positive', primary=False,
                      published_at=scanner.stamp(scanner.NOW), url='https://unverified.invalid/a')]
        self.assertEqual(len(scanner.priority_events(items)), 1)

    def test_old_delisted_price_never_counts_as_fresh(self):
        import json
        from datetime import timedelta
        payload={'c':65.55,'pc':65.25,'t':int((scanner.NOW-timedelta(days=14)).timestamp())}
        with patch.object(scanner,'fetch',return_value=json.dumps(payload).encode()):
            with patch.object(scanner.time,'sleep'):
                quotes, count, errors = scanner.prices(['EQR'],'test-token',[])
        self.assertEqual(count,0)
        self.assertIsNone(quotes[0]['price'])
        self.assertTrue(errors)

    def test_current_quote_remains_valid(self):
        import json
        payload={'c':123.45,'pc':120.0,'t':int(scanner.NOW.timestamp())}
        with patch.object(scanner,'fetch',return_value=json.dumps(payload).encode()):
            with patch.object(scanner.time,'sleep'):
                quotes, count, errors = scanner.prices(['TEST'],'test-token',[])
        self.assertEqual(count,1)
        self.assertEqual(quotes[0]['price'],123.45)
        self.assertEqual(errors,[])

    def test_finnhub_no_key_does_not_make_up_quotes(self):
        quotes, count, errors = scanner.prices(['AAPL'], '', [])
        self.assertIsNone(quotes[0]['price'])
        self.assertEqual(count, 0)
        self.assertEqual(errors, [])

if __name__ == '__main__':
    unittest.main()
