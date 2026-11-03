# What Makes Newcomers Stick? Community Retention Analytics

[![CI](https://github.com/dvskaff/community-retention-analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/dvskaff/community-retention-analytics/actions/workflows/ci.yml)
[![Build analysis](https://github.com/dvskaff/community-retention-analytics/actions/workflows/pipeline.yml/badge.svg)](https://github.com/dvskaff/community-retention-analytics/actions/workflows/pipeline.yml)
![dbt](https://img.shields.io/badge/dbt-1.12-orange) ![DuckDB](https://img.shields.io/badge/DuckDB-2.0-yellow)
![Python](https://img.shields.io/badge/python-3.13-blue)

**Live dashboard: https://dvskaff.github.io/community-retention-analytics/** ·
**dbt docs & lineage: https://dvskaff.github.io/community-retention-analytics/dbt-docs/**

Product analytics on **Cross Validated** (stats.stackexchange.com), Stack Exchange's statistics and data science Q&A
community, built from its public data dump. It answers the questions a product team asks about any community or app:

* How many people are active, and is the community growing or shrinking? (growth accounting)
* Of each month's new contributors, how many are still around 1, 3, 12 months later? (cohort retention)
* Where do newcomers drop off between signing up and becoming regulars? (activation funnel)
* What happens in a newcomer's first week that predicts whether they come back? (the "aha moment")
* Is the community delivering its core value? (north-star metric: questions answered within 7 days)

## Results

Rewritten automatically after every run.

<!-- RESULTS:START -->
_Stack Exchange dump `stackexchange_20240402` · Cross Validated activity through Mar 31, 2024 · 1,223,160 contributions by 113,497 people_

| Metric | Value |
|---|---|
| Active contributors, last 12 months | 11,342 |
| Questions, last 12 months | 18,827 (-27% vs. prior 12 months; peak was 2,272 in Mar 2017) |
| Newcomers who came back within 30 days | 29.1% of 7,071 |
| Questions answered within 7 days | 30.1% (median first answer after 3 h) |
| Share of answers written by the top 10% of answerers | 76% |

**Aha moment:** newcomers whose first question was answered within 24 hours came back 39.9% of the time vs. 34.1% otherwise (+5.8 pts, 95% CI +4.4 to +7.2; n = 18,192).

**Cox model:** adjusting for the other first-week signals, a fast first answer is associated with coming back 1.21× as fast (95% CI 1.16–1.27).

**Latest run:** 19 dbt models, 60 data tests and 3 unit tests: 63 passed, 0 warnings, 0 failed · 2026-11-03 12:31 UTC
<!-- RESULTS:END -->

## How it works

```
Internet Archive: newest Stack Exchange data dump (found via the archive's search + metadata APIs)
        │  src/commret/download.py: MD5-verified download, 7-Zip extraction of Users/Posts/Comments/Votes
        │  src/commret/parse.py:    streaming XML → Parquet (constant memory; free text dropped) → DuckDB raw
        ▼
dbt (dbt/)
  staging       stg_se__users · stg_se__posts · stg_se__comments · stg_se__votes
  intermediate  int_contributions · int_question_outcomes · int_post_feedback · int_user_firsts · int_dump_window
  marts         dim_users (contract) · fct_contributions (contract) · fct_questions
                mart_monthly_activity (growth accounting) · mart_cohort_retention · mart_activation_funnel
                mart_first_experience · mart_weekly_answers (north star) · mart_answer_concentration · mart_kpi_summary
        │  src/commret/analysis.py: Wilson CIs, Kaplan–Meier + log-rank, Cox proportional hazards (lifelines)
        ▼
GitHub Pages: dashboard + dbt docs (rebuilt by GitHub Actions on every push and monthly)
```

**Key definitions** (all in dbt, documented on the docs site)

| Metric | Definition |
|---|---|
| Contribution | A question, answer or comment by a registered user |
| Activated | First contribution within 30 days of signing up |
| Came back | Another contribution on a later day, within 30 days of the first contribution |
| Growth accounting | Each month's active contributors = new + retained (active last month) + resurrected (back after a gap); churned = active last month, not this month |
| North star | Questions answered by another user within 7 days |

**Testing.** dbt data tests on keys, relationships, accepted values and ranges; enforced contracts on `dim_users` and
`fct_contributions`; singular tests for the growth-accounting identity (actives = new + retained + resurrected, and
month-over-month balance), row reconciliation and 100% month-0 retention; dbt unit tests for tag parsing,
next-visit logic and growth-accounting classification; pytest for the downloader, parser and statistics, plus a full
end-to-end build on synthetic data in which a known effect is planted and must be recovered.

**Caveats.** The data is observational, so first-experience results are associations, not causal effects (a fast
answer may partly reflect a clearer question). Upvotes are anonymous and dated to the day in the public dump.
Deleted accounts are missing. "Came back" counts visible contributions, not reading.

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest                                                 # ~30 seconds, offline
PYTHONPATH=src python -m commret.pipeline              # downloads the real dump (~1 GB), then builds everything
```

## Data

[Stack Exchange data dump](https://archive.org/details/stackexchange) for stats.stackexchange.com, published by
Stack Exchange, Inc. under CC BY-SA and hosted by the Internet Archive. Only user IDs, timestamps, scores and
structure are used; no post text, names or profiles appear in this project. No account or API key is needed.

## Stack

Python 3.13 · DuckDB · dbt Core (dbt-duckdb) · pandas · PyArrow · lifelines · SciPy · Plotly · pytest · ruff ·
GitHub Actions · GitHub Pages
