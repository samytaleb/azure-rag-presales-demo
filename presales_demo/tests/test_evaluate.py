"""Unit tests for the synthetic presales evaluation extension."""
import json
import tempfile
import unittest
from pathlib import Path

from presales_demo.evaluate import (
    ROOT,
    endpoint_url,
    evaluate_case,
    extract_sources,
    load_cases,
    load_fixtures,
    run,
)


class PresalesEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.cases = load_cases(ROOT / "scenarios.json")
        self.answers = load_fixtures(ROOT / "fixtures" / "answers.jsonl")

    def test_all_synthetic_replay_cases_pass(self):
        report = run(self.cases, answers=self.answers)
        self.assertEqual(report["total"], 12)
        self.assertEqual(report["passed"], 12)
        self.assertEqual(report["failed"], 0)
        self.assertEqual(report["mode"], "fixtures")
        self.assertIsNone(report["average_latency_ms"])

    def test_missing_answer_fails_closed(self):
        answers = dict(self.answers)
        del answers[self.cases[0]["id"]]
        report = run(self.cases, answers=answers)
        self.assertEqual(report["failed"], 1)
        self.assertEqual(report["results"][0]["error_type"], "ValueError")

    def test_citation_cannot_be_plain_filename(self):
        case = self.cases[1]
        result = evaluate_case(case, "CSV import limit 50,000. Source: 01-product.txt")
        self.assertFalse(result["pass"])
        self.assertIn("01-product.txt", result["missing_citations"])

    def test_forbidden_promise_is_rejected(self):
        case = self.cases[-2]
        result = evaluate_case(case, "No documented uptime SLA, but I guarantee 99.99% uptime. [04-implementation.txt]")
        self.assertFalse(result["pass"])
        self.assertTrue(result["forbidden_phrases"])

    def test_wrong_fact_is_rejected(self):
        case = self.cases[3]
        result = evaluate_case(case, "Growth includes 10 users for $450 per month. [02-pricing.txt]")
        self.assertFalse(result["pass"])

    def test_source_parser(self):
        refs = extract_sources("See [02-pricing.txt], [folder/03-security.txt#page=2] and no citation 01-product.txt.")
        self.assertEqual(refs, {"02-pricing.txt", "03-security.txt"})

    def test_validate_remote_transport(self):
        self.assertEqual(endpoint_url("http://127.0.0.1:50505"), "http://127.0.0.1:50505/chat")
        self.assertEqual(endpoint_url("https://example.test/chat"), "https://example.test/chat")
        with self.assertRaises(ValueError):
            endpoint_url("http://example.test")
        with self.assertRaises(ValueError):
            endpoint_url("https://user:pass@example.test")
        with self.assertRaises(ValueError):
            endpoint_url("https://example.test?token=secret")

    def test_reject_duplicate_cases(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "cases.json"
            p.write_text(json.dumps({"schema_version": 1, "cases": [self.cases[0], self.cases[0]]}))
            with self.assertRaises(ValueError):
                load_cases(p)

    def test_reject_duplicate_fixture_response(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "answers.jsonl"
            line = json.dumps({"id": "duplicate", "answer": "hello"}) + "\n"
            p.write_text(line + line)
            with self.assertRaises(ValueError):
                load_fixtures(p)


if __name__ == "__main__":
    unittest.main()
