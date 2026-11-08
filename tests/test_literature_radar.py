"""All literature-radar tests are offline and use mock metadata."""
import datetime as dt
import unittest

from research.literature import parse_candidates, run_radar, render_markdown


class LiteratureRadarTests(unittest.TestCase):
    def fixture(self):
        return {"message":{"items":[
            {"DOI":"10.1234/important.one","title":["Adaptive Index Test"],
             "published":{"date-parts":[[2026,11,3]]}},
            {"DOI":"10.1234/old","title":["Old Paper"],
             "published":{"date-parts":[[2012,3,1]]}},
            {"DOI":"unsafe-string","title":["Invalid DOI"],
             "published":{"date-parts":[[2026,11,1]]}},
        ]}}

    def test_filter_by_date_and_doi(self):
        out=parse_candidates(self.fixture(),"indexing","2026-07-01")
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]["doi"],"10.1234/important.one")

    def test_all_queries_dedupe_same_doi(self):
        out=run_radar(today=dt.date(2026,11,8),
                      fetcher=lambda topic,cutoff:self.fixture())
        self.assertEqual(out["status"],"COMPLETE")
        self.assertEqual(len(out["results"]),1)
        self.assertIn("CANDIDATES ONLY",render_markdown(out))

    def test_partial_api_failure_is_exposed(self):
        def fetch(topic,cutoff):
            if topic.startswith("database adaptive"):
                raise TimeoutError("test timeout")
            return self.fixture()
        out=run_radar(today=dt.date(2026,11,8),fetcher=fetch)
        self.assertEqual(out["status"],"PARTIAL")
        self.assertEqual(len(out["failures"]),1)

    def test_total_failure_is_not_false_success(self):
        def fetch(topic,cutoff):
            raise TimeoutError("test failure")
        out=run_radar(today=dt.date(2026,11,8),fetcher=fetch)
        self.assertEqual(out["status"],"UNAVAILABLE")
        self.assertFalse(out["results"])


if __name__ == "__main__":
    unittest.main()
