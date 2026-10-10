"""Unit tests for the dependency-free HTML report renderer."""
import unittest
from presales_demo.report_html import render_html
from presales_demo.evaluate import ROOT, load_cases, load_fixtures, run


class ReportTests(unittest.TestCase):
    def test_fixture_summary_is_explicitly_not_model_accuracy(self):
        cases = load_cases(ROOT / "scenarios.json")
        fixture_answers = load_fixtures(ROOT / "fixtures" / "answers.jsonl")
        page = render_html(run(cases, answers=fixture_answers))
        self.assertIn("SYNTHETIC FIXTURE REPLAY", page)
        self.assertIn("12/12", page)
        self.assertIn("Not measured", page)
        self.assertIn("not the Azure RAG system", page)

    def test_escapes_untrusted_id_and_category(self):
        page = render_html({
            "mode": "live", "total": 1, "passed": 0,
            "by_category": {"<script>alert(1)</script>": {"total": 1, "passed": 0}},
            "results": [{"id": "<img src=x onerror=alert(1)>", "category": "demo",
                         "pass": False, "error_type": "ValueError"}],
        })
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertNotIn("<img src=x onerror=alert(1)>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("LIVE ENDPOINT EVALUATION", page)

    def test_rejects_invalid_totals(self):
        with self.assertRaises(ValueError):
            render_html({"mode": "fixtures", "total": 1, "passed": 2})


if __name__ == "__main__":
    unittest.main()
