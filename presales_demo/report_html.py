"""Render the synthetic presales evaluation report as a static, shareable HTML page.

No generated answer text, tokens or remote requests are needed. Escapes all
untrusted fields in the report and requires no JavaScript or third-party code.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_html(report: dict) -> str:
    mode = report.get("mode", "unknown")
    total = int(report.get("total", 0))
    passed = int(report.get("passed", 0))
    if total < 0 or passed < 0 or passed > total:
        raise ValueError("Invalid summary totals")
    rate = round(passed * 100 / total) if total else 0
    label = "SYNTHETIC FIXTURE REPLAY — NOT AI PERFORMANCE" if mode == "fixtures" else "LIVE ENDPOINT EVALUATION — HEURISTIC ONLY"

    categories = []
    for name, stat in sorted(report.get("by_category", {}).items()):
        n = int(stat["total"])
        ok = int(stat["passed"])
        if n < 0 or ok < 0 or ok > n:
            raise ValueError("Invalid category totals")
        width = round(ok * 100 / n) if n else 0
        categories.append(
            "<tr><td>" + esc(name) + "</td><td>" + str(ok) + "/" + str(n)
            + '</td><td><div class="track"><div class="bar" style="width:'
            + str(width) + '%"></div></div></td></tr>'
        )

    rows = []
    for result in report.get("results", []):
        good = bool(result.get("pass"))
        ident = esc(result.get("id", "unknown"))
        category = esc(result.get("category", "unknown"))
        status = "PASS" if good else "FAIL"
        notes = "Matched expectations" if good else "Review missing facts, citations or blocked claims"
        if result.get("error_type"):
            notes = "Error type: " + esc(result["error_type"])
        rows.append("<tr><td>" + ident + "</td><td>" + category + "</td><td><strong>"
                    + status + "</strong></td><td>" + notes + "</td></tr>")

    latency = report.get("average_latency_ms")
    latency_text = "Not measured" if latency is None else esc(latency) + " ms"
    return ("""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Synthetic B2B Presales Evaluation</title>
<style>
:root{color-scheme:light;font-family:system-ui,-apple-system,BlinkMacSystemFont,sans-serif}
body{max-width:1060px;margin:40px auto;padding:0 22px;color:#14233b;background:#fbfcfe}
h1{font-size:2rem;margin-bottom:.3rem} h2{margin-top:2.2rem}
small, .muted{color:#5d6978} .banner{padding:14px 18px;border:1px solid #b3bdcc;border-radius:8px;background:#f1f4f8}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:22px 0}
.card{padding:20px;border:1px solid #d8dee8;border-radius:10px;background:white}
.number{font-size:1.8rem;font-weight:700}table{border-collapse:collapse;width:100%;background:white}
td,th{text-align:left;border-bottom:1px solid #e1e7ef;padding:11px 9px;font-size:.94rem}
th{background:#f1f4f8}.track{height:9px;background:#e6eaf0;border-radius:99px;overflow:hidden}
.bar{height:100%;background:#446e9d}footer{margin:28px 0;color:#5d6978;font-size:.88rem}
</style></head><body>
<h1>B2B Presales RAG Evaluation</h1><p class="muted">Synthetic policy knowledge base · regression checks · evidence-aware demo</p>
<p class="banner"><strong>""" + esc(label) + """</strong><br>
Keyword/citation regression checks are not an accuracy, groundedness, compliance or security certification.
Fixture results validate the evaluator, not the Azure RAG system.</p>
<div class="cards"><div class="card"><div class="number">""" + str(passed) + "/" + str(total) + """</div>Cases passed</div>
<div class="card"><div class="number">""" + str(rate) + """%</div>Heuristic pass rate</div>
<div class="card"><div class="number">""" + latency_text + """</div>Mean request latency</div></div>
<h2>Results by business category</h2>
<table><thead><tr><th>Category</th><th>Cases passed</th><th>Coverage</th></tr></thead><tbody>"""
    + "\n".join(categories) + """</tbody></table>
<h2>Scenario-level checks</h2><table><thead><tr><th>Scenario</th><th>Category</th><th>Status</th><th>Interpretation</th>
</tr></thead><tbody>""" + "\n".join(rows) + """</tbody></table>
<footer>Generated from a summary-only JSON report. No raw answers, authentication tokens or customer data are included.
<a href="https://github.com/Azure-Samples/azure-search-openai-demo">Microsoft upstream</a> is credited separately.</footer>
</body></html>""")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Render a safe static HTML view of an evaluation report")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.input.read_text(encoding="utf-8"))
        page = render_html(report)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(page, encoding="utf-8")
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(2, "Report rendering failed: " + type(error).__name__ + "\n")
    print("HTML report saved: " + str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
