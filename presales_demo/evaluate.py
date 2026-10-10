"""B2B presales RAG evaluation harness.

Deterministic replay is a test of the *evaluation harness*, never a claim of
model quality. Live mode calls the upstream application's JSON POST /chat API.
No SAP or employer data is included.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
SOURCES_PATTERN = re.compile(r"\[([^\[\]\n]+?\.(?:md|pdf))(?:#[^\]\n]*)?\]", re.I)


def load_cases(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("cases"), list):
        raise ValueError("Expected schema_version=1 and a list of cases")
    cases = data["cases"]
    ids = [case.get("id") for case in cases]
    if not ids or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Cases must have non-empty, unique IDs")
    for case in cases:
        if (not isinstance(case.get("question"), str)
                or not isinstance(case.get("required_terms"), list)
                or not isinstance(case.get("required_sources"), list)
                or not isinstance(case.get("forbidden_terms"), list)
                or not isinstance(case.get("abstain"), bool)):
            raise ValueError("Malformed case: " + str(case.get("id")))
        if any(not isinstance(group, list) or not group or not all(isinstance(s, str) and s for s in group)
               for group in case["required_terms"]):
            raise ValueError("Each required_terms group must contain valid alternatives")
    return cases


def load_fixtures(path: Path) -> dict[str, str]:
    answers: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row.get("id"), str) or not isinstance(row.get("answer"), str):
            raise ValueError("Invalid response fixture at line " + str(number))
        if row["id"] in answers:
            raise ValueError("Duplicate response ID: " + row["id"])
        answers[row["id"]] = row["answer"]
    return answers


def extract_sources(answer: str) -> set[str]:
    """Extract explicit [file.md] or [file.pdf#page=1] citations only."""
    return {Path(match).name.casefold() for match in SOURCES_PATTERN.findall(answer)}


def evaluate_case(case: dict, answer: str) -> dict:
    lowered = answer.casefold()
    missing_terms = [
        list(group) for group in case["required_terms"]
        if not any(term.casefold() in lowered for term in group)
    ]
    citations = extract_sources(answer)
    expected = {Path(source).name.casefold() for source in case["required_sources"]}
    missing_sources = sorted(expected - citations)
    forbidden = [term for term in case["forbidden_terms"] if term.casefold() in lowered]
    passed = not missing_terms and not missing_sources and not forbidden
    return {
        "id": case["id"],
        "category": case.get("category", "uncategorized"),
        "pass": passed,
        "required_facts_matched": len(case["required_terms"]) - len(missing_terms),
        "required_facts_total": len(case["required_terms"]),
        "citations_found": sorted(citations),
        "missing_citations": missing_sources,
        "missing_fact_groups": missing_terms,
        "forbidden_phrases": forbidden,
        "abstention_expected": case["abstain"],
        "note": "Heuristic keyword/citation checks only; no semantic or factual verification.",
    }


def endpoint_url(base: str) -> str:
    parsed = urlsplit(base)
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        raise ValueError("Provide a full http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Userinfo, query parameters and fragments are not accepted")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Non-local endpoints require HTTPS")
    clean = base.rstrip("/")
    return clean if clean.endswith("/chat") else clean + "/chat"


def ask_live(url: str, question: str, bearer_token: str | None, timeout: float) -> tuple[str, float]:
    payload = {
        "messages": [{"role": "user", "content": question}],
        "context": {"overrides": {"retrieval_mode": "hybrid", "top": 5}},
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if bearer_token:
        headers["Authorization"] = "Bearer " + bearer_token
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    start = time.monotonic()
    with urlopen(request, timeout=timeout) as response:
        body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError("Live response exceeds the 2 MB safety limit")
    elapsed_ms = round((time.monotonic() - start) * 1000, 1)
    data = json.loads(body)
    if not isinstance(data, dict) or not isinstance(data.get("output_text"), str):
        raise ValueError("Expected upstream /chat response with output_text string")
    return data["output_text"], elapsed_ms


def run(cases: list[dict], answers: dict[str, str] | None = None,
        live_url: str | None = None, token: str | None = None,
        timeout: float = 30.0) -> dict:
    results = []
    category_totals: dict[str, dict[str, int]] = defaultdict(lambda: {"passed": 0, "total": 0})
    for case in cases:
        latency = None
        try:
            if answers is not None:
                if case["id"] not in answers:
                    raise ValueError("Missing fixture response for " + case["id"])
                answer = answers[case["id"]]
            elif live_url:
                answer, latency = ask_live(live_url, case["question"], token, timeout)
            else:
                raise ValueError("Select fixture or live mode")
            item = evaluate_case(case, answer)
        except (ValueError, HTTPError, URLError, TimeoutError, OSError) as exc:
            # Never serialize server responses, private user questions or auth headers.
            item = {"id": case["id"], "category": case.get("category", "uncategorized"),
                    "pass": False, "error_type": type(exc).__name__}
        item["latency_ms"] = latency
        results.append(item)
        aggregate = category_totals[item["category"]]
        aggregate["total"] += 1
        aggregate["passed"] += int(item["pass"])
    passed = sum(int(r["pass"]) for r in results)
    measured = [r["latency_ms"] for r in results if r["latency_ms"] is not None]
    return {
        "mode": "fixtures" if answers is not None else "live",
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": round(passed / len(results), 4) if results else 0,
        "average_latency_ms": round(sum(measured) / len(measured), 1) if measured else None,
        "by_category": dict(sorted(category_totals.items())),
        "results": results,
        "disclaimer": "Rule-based regression checks, NOT an AI quality, accuracy, compliance or production-readiness certification.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic presales RAG regression suite")
    parser.add_argument("--mode", choices=["fixtures", "live"], default="fixtures")
    parser.add_argument("--cases", type=Path, default=ROOT / "scenarios.json")
    parser.add_argument("--fixtures", type=Path, default=ROOT / "fixtures" / "answers.jsonl")
    parser.add_argument("--url", help="Deployed app base URL or /chat URL (live only)")
    parser.add_argument("--token-env", help="Environment variable containing bearer token (live only)")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--report", type=Path, help="Optional local JSON report; contains no answer text")
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        cases = load_cases(args.cases)
        if args.mode == "fixtures":
            if args.url or args.token_env:
                parser.error("--url and --token-env are only valid for live mode")
            report = run(cases, answers=load_fixtures(args.fixtures))
        else:
            if not args.url:
                parser.error("--url is required for live mode")
            url = endpoint_url(args.url)
            token = os.environ.get(args.token_env) if args.token_env else None
            if args.token_env and not token:
                parser.error("The selected token environment variable is empty or missing")
            report = run(cases, live_url=url, token=token, timeout=args.timeout)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("Mode: " + report["mode"])
        print("Cases passed: " + str(report["passed"]) + "/" + str(report["total"]))
        print("Pass rate (heuristic): " + f"{report['pass_rate']:.0%}")
        if report["average_latency_ms"] is not None:
            print("Mean successful-response latency: " + str(report["average_latency_ms"]) + " ms")
        print(report["disclaimer"])
        for result in report["results"]:
            if not result["pass"]:
                print("FAIL: " + result["id"], file=sys.stderr)
        return 0 if not report["failed"] else 1
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print("Invalid evaluation configuration: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
