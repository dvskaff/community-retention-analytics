"""Rewrites the results block in README.md after each run."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


def results_block(s: dict) -> str:
    end = pd.Timestamp(s["data_end"])
    q_change = s["questions_12m"] / s["questions_prior_12m"] - 1 if s["questions_prior_12m"] else 0
    lines = [
        f"_Stack Exchange dump `{s['dump_id']}` · Cross Validated activity through {end:%b %d, %Y} · "
        f"{s['contributions_all_time']:,} contributions by {s['contributors_all_time']:,} people_",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Active contributors, last 12 months | {s['active_contributors_12m']:,} |",
        f"| Questions, last 12 months | {s['questions_12m']:,} ({q_change:+.0%} vs. prior 12 months; "
        f"peak was {s['peak_questions']:,} in {pd.Timestamp(s['peak_month']):%b %Y}) |",
        f"| Newcomers who came back within 30 days | {s['newcomer_came_back_rate']:.1%} "
        f"of {s['newcomers_12m']:,} |",
        f"| Questions answered within 7 days | {s['share_answered_7d']:.1%} "
        f"(median first answer after {s['median_hours_to_answer']:.0f} h) |",
        f"| Share of answers written by the top 10% of answerers | {s['top10pct_answer_share']:.0%} |",
    ]
    fast = next((e for e in s["experience"] if e["signal"] == "first_q_answered_fast"), None)
    if fast:
        lines += [
            "",
            f"**Aha moment:** newcomers whose first question was answered within 24 hours came back "
            f"{fast['rate_yes']:.1%} of the time vs. {fast['rate_no']:.1%} otherwise "
            f"({(fast['diff']) * 100:+.1f} pts, 95% CI {fast['diff_lo'] * 100:+.1f} to "
            f"{fast['diff_hi'] * 100:+.1f}; n = {fast['n_yes'] + fast['n_no']:,}).",
        ]
    hr = next((c for c in s["cox"] if c["covariate"].startswith("Answered within")), None)
    if hr:
        lines += [
            "",
            f"**Cox model:** adjusting for the other first-week signals, a fast first answer is associated "
            f"with coming back {hr['hazard_ratio']:.2f}× as fast (95% CI {hr['lo']:.2f}–{hr['hi']:.2f}).",
        ]
    d = s["dbt"]
    lines += [
        "",
        f"**Latest run:** {d['models']} dbt models, {d['data_tests']} data tests and {d['unit_tests']} unit "
        f"tests: {d['passed']} passed, {d['warnings']} warning{'' if d['warnings'] == 1 else 's'}, "
        f"{d['failed']} failed · {s['built_at']}",
    ]
    return "\n".join(lines)


def update_readme(readme: Path, summary: dict) -> None:
    text = readme.read_text()
    pattern = r"(<!-- RESULTS:START -->\n).*?(\n<!-- RESULTS:END -->)"
    block = results_block(summary)
    readme.write_text(re.sub(pattern, lambda m: m.group(1) + block + m.group(2), text, flags=re.S))
