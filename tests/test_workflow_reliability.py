import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
class WorkflowReliabilityTests(unittest.TestCase):
    def test_branch_pages_only_one_publisher(self):
        workflow=(ROOT/'.github/workflows/scan.yml').read_text()
        self.assertNotIn('actions/deploy-pages@',workflow)
        self.assertNotIn('actions/upload-pages-artifact@',workflow)
        self.assertIn('git add data/stocksdeepdive.json data/apac.json',workflow)
        for item in ('index.html','market.js','data/latest.json','data/market_catalog.json'):
            self.assertTrue((ROOT/item).exists(),item)
    def test_research_is_not_cancelled_by_new_job(self):
        workflow=(ROOT/'.github/workflows/scan.yml').read_text()
        self.assertIn('cancel-in-progress: false',workflow)
        self.assertIn('python -m unittest discover -s tests -v',workflow)

if __name__=='__main__':unittest.main()
