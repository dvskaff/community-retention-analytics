"""The community-retention dashboard (site/index.html)."""

from __future__ import annotations

import html
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs_version

from .config import Config
from .report_base import (
    AQUA,
    BLUE,
    CSS,
    GRID,
    INK2,
    LAYOUT_JS,
    MUTED,
    ORANGE,
    SURFACE,
    VIOLET,
    _card,
    _div,
    _int,
    _pct,
    _style,
    _table,
    health_section,
    load_artifacts,
)

CHATGPT = pd.Timestamp("2022-11-30")


def _pp(v) -> str:
    return "–" if pd.isna(v) else f"{v * 100:+.1f} pts"


def load_marts(db_path: Path) -> dict[str, pd.DataFrame]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        q = lambda sql: con.execute(sql).df()  # noqa: E731
        return {
            "kpi": q("select * from marts.mart_kpi_summary"),
            "monthly": q("select * from marts.mart_monthly_activity order by month"),
            "cohorts": q(
                "select * from marts.mart_cohort_retention order by cohort_month, months_since_first"
            ),
            "funnel": q("select * from marts.mart_activation_funnel order by signup_year"),
            "experience": q("select * from marts.mart_first_experience"),
            "weekly": q("select * from marts.mart_weekly_answers where is_complete order by week_start"),
            "lorenz": q("""select share_of_answerers, cumulative_share_of_answers
                           from marts.mart_answer_concentration order by answerer_rank"""),
            "dump": q("select * from raw.dump_info"),
            "layers": q("""
                select 'Raw users' as layer, 'raw.users' as relation, (select count(*) from raw.users) as row_count
                union all select 'Raw posts', 'raw.posts', (select count(*) from raw.posts)
                union all select 'Raw comments', 'raw.comments', (select count(*) from raw.comments)
                union all select 'Raw votes', 'raw.votes', (select count(*) from raw.votes)
                union all select 'Users (dimension)', 'marts.dim_users', (select count(*) from marts.dim_users)
                union all select 'Contributions (fact)', 'marts.fct_contributions',
                          (select count(*) from marts.fct_contributions)
                union all select 'Questions (fact)', 'marts.fct_questions', (select count(*) from marts.fct_questions)"""),
        }
    finally:
        con.close()


# --------------------------------------------------------------------------- figures
def _chatgpt_line(fig: go.Figure, x_min) -> None:
    if pd.Timestamp(x_min) < CHATGPT:
        fig.add_vline(x=CHATGPT, line=dict(color=MUTED, width=1, dash="dash"))
        fig.add_annotation(
            x=CHATGPT,
            y=1,
            yref="paper",
            text="ChatGPT released",
            showarrow=False,
            xanchor="left",
            xshift=4,
            font=dict(size=11, color=MUTED),
        )


def fig_volume(monthly: pd.DataFrame) -> go.Figure:
    m = monthly[monthly["is_complete_month"]]
    fig = go.Figure()
    for col, name, color in (("questions", "Questions", BLUE), ("answers", "Answers", ORANGE)):
        fig.add_trace(
            go.Scatter(
                x=m["month"], y=m[col], name=name, line=dict(color=color, width=2), hovertemplate="%{y:,.0f}"
            )
        )
    _style(fig, "Questions and answers per month", y_title="Posts per month")
    _chatgpt_line(fig, m["month"].min())
    return fig


def fig_active(monthly: pd.DataFrame) -> go.Figure:
    m = monthly[monthly["is_complete_month"]]
    fig = go.Figure(
        go.Scatter(
            x=m["month"],
            y=m["active_contributors"],
            name="Active contributors",
            fill="tozeroy",
            fillcolor="rgba(42,120,214,0.12)",
            line=dict(color=BLUE, width=2),
            hovertemplate="%{y:,.0f} contributors",
        )
    )
    _style(fig, "Monthly active contributors", y_title="People who posted or commented", showlegend=False)
    _chatgpt_line(fig, m["month"].min())
    return fig


def fig_growth(monthly: pd.DataFrame, months: int = 36) -> go.Figure:
    m = monthly[monthly["is_complete_month"]].tail(months)
    fig = go.Figure()
    for col, name, color in (
        ("retained", "Retained", BLUE),
        ("new_contributors", "New", AQUA),
        ("resurrected", "Resurrected", VIOLET),
    ):
        fig.add_trace(
            go.Bar(x=m["month"], y=m[col], name=name, marker=dict(color=color), hovertemplate="%{y:,.0f}")
        )
    fig.add_trace(
        go.Bar(
            x=m["month"],
            y=-m["churned"],
            name="Churned",
            marker=dict(color=ORANGE),
            customdata=m["churned"],
            hovertemplate="%{customdata:,.0f}",
        )
    )
    _style(
        fig,
        "Growth accounting: where each month's contributors came from",
        height=400,
        barmode="relative",
        bargap=0.15,
        y_title="Contributors (churned shown below zero)",
    )
    fig.update_yaxes(zeroline=True, zerolinecolor=INK2)
    return fig


def fig_cohorts(cohorts: pd.DataFrame, n_cohorts: int = 24, max_months: int = 12) -> go.Figure:
    c = cohorts[cohorts["is_complete"] & cohorts["months_since_first"].between(1, max_months)]
    recent = sorted(c["cohort_month"].unique())[-n_cohorts:]
    c = c[c["cohort_month"].isin(recent)]
    grid = c.pivot(index="cohort_month", columns="months_since_first", values="retention_rate")
    grid = grid.reindex(columns=range(1, max_months + 1))
    sizes = c.groupby("cohort_month")["cohort_size"].first().reindex(grid.index)
    labels = [f"{pd.Timestamp(i):%b %Y} ({int(n):,})" for i, n in zip(grid.index, sizes, strict=True)]
    z = grid.to_numpy()
    text = np.where(np.isnan(z), "", np.char.mod("%.0f%%", np.nan_to_num(z) * 100))
    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=[f"M{k}" for k in grid.columns],
            y=labels,
            text=text,
            texttemplate="%{text}",
            textfont=dict(size=10),
            colorscale=[[0, "#f4f8fd"], [0.5, "#7fb2ec"], [1, "#0b3a75"]],
            zmin=0,
            zmax=max(0.3, float(np.nanmax(z)) if np.isfinite(z).any() else 0.3),
            showscale=False,
            hovertemplate="%{y}<br>%{x}: %{z:.1%} still contributing<extra></extra>",
        )
    )
    _style(
        fig,
        "Share of each cohort active N months later",
        height=620,
        x_title="Months after first contribution",
        hovermode="closest",
    )
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(size=10))
    fig.update_xaxes(side="top")
    fig.update_layout(margin=dict(l=130, r=10, t=90, b=30))
    return fig


def fig_funnel(funnel: pd.DataFrame) -> go.Figure:
    f = funnel[funnel["is_complete"] & (funnel["signups"] >= 50)]
    fig = go.Figure()
    for col, name, color in (
        ("activated", "Contributed within 30 days of signup", BLUE),
        ("came_back", "…and came back within 30 days", ORANGE),
        ("active_after_6_months", "…and still contributing 6+ months later", AQUA),
    ):
        fig.add_trace(
            go.Scatter(
                x=f["signup_year"],
                y=f[col] / f["signups"],
                name=name,
                mode="lines+markers",
                line=dict(color=color, width=2),
                marker=dict(size=7),
                hovertemplate="%{y:.1%}",
            )
        )
    _style(
        fig,
        "Newcomer funnel by signup year (share of all signups)",
        height=400,
        y_title="Share of signups",
        legend=dict(orientation="h", yanchor="top", y=-0.15, x=0),
    )
    fig.update_yaxes(tickformat=".0%", rangemode="tozero")
    fig.update_layout(margin=dict(l=64, r=20, t=60, b=110))
    return fig


def fig_experience(exp: pd.DataFrame) -> go.Figure:
    e = exp.iloc[::-1]
    fig = go.Figure()
    for flag, color, name in (("no", MUTED, "Without it"), ("yes", BLUE, "With it")):
        fig.add_trace(
            go.Scatter(
                x=e[f"rate_{flag}"],
                y=e["label"],
                mode="markers",
                name=name,
                marker=dict(color=color, size=11, line=dict(color=SURFACE, width=2)),
                error_x=dict(
                    type="data",
                    symmetric=False,
                    array=e[f"hi_{flag}"] - e[f"rate_{flag}"],
                    arrayminus=e[f"rate_{flag}"] - e[f"lo_{flag}"],
                    color=color,
                    thickness=1.5,
                    width=0,
                ),
                customdata=e[f"n_{flag}"],
                hovertemplate="%{x:.1%} came back (n = %{customdata:,})<extra>" + name + "</extra>",
            )
        )
    _style(
        fig,
        "Came back within 30 days, by first experience (95% CI)",
        height=120 + 52 * len(e),
        x_title="Share of newcomers who came back",
        hovermode="closest",
    )
    fig.update_xaxes(tickformat=".0%", showgrid=True, gridcolor=GRID)
    fig.update_yaxes(showgrid=False)
    fig.update_layout(margin=dict(l=300, r=20, t=74, b=48))
    return fig


def fig_km(km: dict) -> go.Figure:
    fig = go.Figure()
    for (label, curve), color in zip(km["curves"].items(), (BLUE, MUTED), strict=False):
        fig.add_trace(
            go.Scatter(
                x=curve["day"],
                y=curve["share_returned"],
                name=label,
                line=dict(color=color, width=2, shape="hv"),
                hovertemplate="%{y:.1%}",
            )
        )
    _style(
        fig,
        "Time until a newcomer's next visit (Kaplan–Meier)",
        height=380,
        y_title="Share who came back",
        x_title="Days after first question",
    )
    fig.update_yaxes(tickformat=".0%", rangemode="tozero")
    return fig


def fig_cox(cox: pd.DataFrame) -> go.Figure:
    c = cox.iloc[::-1]
    colors = [
        BLUE if lo > 1 else (ORANGE if hi < 1 else MUTED) for lo, hi in zip(c["lo"], c["hi"], strict=True)
    ]
    fig = go.Figure(
        go.Scatter(
            x=c["hazard_ratio"],
            y=c["covariate"],
            mode="markers",
            marker=dict(color=colors, size=11),
            error_x=dict(
                type="data",
                symmetric=False,
                array=c["hi"] - c["hazard_ratio"],
                arrayminus=c["hazard_ratio"] - c["lo"],
                color=INK2,
                thickness=1.5,
                width=4,
            ),
            hovertemplate="%{y}: HR %{x:.2f}<extra></extra>",
        )
    )
    fig.add_vline(x=1, line=dict(color=INK2, width=1))
    _style(
        fig,
        "Cox model: what predicts coming back sooner (hazard ratio, 95% CI)",
        height=360,
        x_title="Hazard ratio (above 1 = returns sooner)",
        hovermode="closest",
        showlegend=False,
    )
    ticks = [0.1, 0.2, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 5, 10]
    lo, hi = float(c["lo"].min()), float(c["hi"].max())
    shown = [t for t in ticks if lo / 1.2 <= t <= hi * 1.2] or [1]
    fig.update_xaxes(
        type="log", showgrid=True, gridcolor=GRID, tickvals=shown, ticktext=[f"{t:g}" for t in shown]
    )
    fig.update_yaxes(showgrid=False)
    fig.update_layout(margin=dict(l=250, r=20, t=74, b=48))
    return fig


def fig_north_star(weekly: pd.DataFrame) -> go.Figure:
    w = weekly.copy()
    w["rolling"] = w["answered_within_7d"].rolling(4, min_periods=1).mean()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=w["week_start"],
            y=w["answered_within_7d"],
            name="Weekly",
            mode="lines",
            line=dict(color="rgba(42,120,214,0.35)", width=1),
            hovertemplate="%{y:,.0f}",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=w["week_start"],
            y=w["rolling"],
            name="4-week average",
            line=dict(color=BLUE, width=2.5),
            hovertemplate="%{y:,.0f}",
        )
    )
    _style(fig, "North star: questions answered by someone within 7 days, per week", y_title="Questions")
    _chatgpt_line(fig, w["week_start"].min())
    return fig


def fig_answer_share(weekly: pd.DataFrame) -> go.Figure:
    w = weekly.copy()
    w["rolling"] = w["share_answered_within_7d"].rolling(13, min_periods=4).mean()
    fig = go.Figure(
        go.Scatter(
            x=w["week_start"],
            y=w["rolling"],
            name="Share answered",
            line=dict(color=ORANGE, width=2),
            hovertemplate="%{y:.1%}",
        )
    )
    _style(
        fig,
        "Share of questions answered within 7 days (13-week average)",
        showlegend=False,
        y_title="Share of questions",
    )
    fig.update_yaxes(tickformat=".0%")
    _chatgpt_line(fig, w["week_start"].min())
    return fig


def fig_lorenz(lorenz: pd.DataFrame) -> go.Figure:
    pts = lorenz.iloc[np.unique(np.linspace(0, len(lorenz) - 1, min(len(lorenz), 400)).astype(int))]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=[0, 1],
            y=[0, 1],
            name="Everyone answers equally",
            line=dict(color=MUTED, dash="dash", width=1.5),
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=np.r_[0, pts["share_of_answerers"]],
            y=np.r_[0, pts["cumulative_share_of_answers"]],
            name="Actual",
            line=dict(color=VIOLET, width=2.5),
            hovertemplate="Top %{x:.0%} of answerers → %{y:.0%} of answers<extra></extra>",
        )
    )
    _style(
        fig,
        "Who does the answering? (last 12 months)",
        x_title="Share of answerers (most active first)",
        y_title="Share of all answers",
        hovermode="closest",
    )
    fig.update_xaxes(tickformat=".0%")
    fig.update_yaxes(tickformat=".0%")
    return fig


# --------------------------------------------------------------------------- page
def concentration_table(lorenz: pd.DataFrame) -> str:
    rows = []
    for top in (0.01, 0.05, 0.10, 0.25, 0.50):
        hit = lorenz[lorenz["share_of_answerers"] >= top]
        if len(hit):
            people = int((lorenz["share_of_answerers"] <= top).sum()) or 1
            rows.append([f"Top {top:.0%}", _int(people), _pct(hit["cumulative_share_of_answers"].iloc[0])])
    return _table(["Answerers", "People", "Share of all answers"], rows)


def concentration_note(top10: float) -> str:
    if pd.isna(top10):
        return ""
    if top10 >= 0.5:
        return (
            "Answering is concentrated in a small core, which makes capacity fragile: losing a handful of "
            "experts would noticeably cut how many questions get answered."
        )
    return "Answering is spread fairly widely across the community."


def chatgpt_sentence(monthly: pd.DataFrame) -> str:
    m = monthly[monthly["is_complete_month"]].set_index("month")["questions"]
    start = CHATGPT.replace(day=1)
    before = m[(m.index >= start - pd.DateOffset(months=12)) & (m.index < start)]
    after = m[(m.index >= start + pd.DateOffset(months=1)) & (m.index < start + pd.DateOffset(months=13))]
    if len(before) < 12 or len(after) < 12:
        return "The dashed line marks ChatGPT's release (November 30, 2022)."
    change = after.mean() / before.mean() - 1
    return (
        f"The dashed line marks ChatGPT's release (November 30, 2022). In the 12 months after it, questions "
        f"averaged {after.mean():,.0f} a month vs. {before.mean():,.0f} in the 12 months before ({change:+.0%}); "
        f"over the latest 12 months they averaged {m.tail(12).mean():,.0f}. The timing lines up, but this chart "
        f"alone does not prove ChatGPT caused the change."
    )


def experience_rows(exp: pd.DataFrame) -> str:
    rows = [
        [
            html.escape(r.label),
            _int(r.n_yes),
            _pct(r.rate_yes),
            _int(r.n_no),
            _pct(r.rate_no),
            f"{_pp(r.diff)} <span class='muted'>({r.diff_lo * 100:+.1f} to {r.diff_hi * 100:+.1f})</span>",
        ]
        for r in exp.itertuples(index=False)
    ]
    return _table(
        [
            "First experience",
            "Newcomers with it",
            "Came back",
            "Without it",
            "Came back",
            "Difference (95% CI)",
        ],
        rows,
    )


def build_site(cfg: Config, target: Path, stats: dict, synthetic: bool = False) -> dict:
    site = cfg.site_dir
    site.mkdir(parents=True, exist_ok=True)
    data, art = load_marts(cfg.db_path), load_artifacts(target)
    k = data["kpi"].iloc[0]
    exp, km, cox, cox_info = stats["experience"], stats["km"], stats["cox"], stats["cox_info"]
    docs = target / "static_index.html"
    if docs.exists():
        (site / "dbt-docs").mkdir(exist_ok=True)
        shutil.copy(docs, site / "dbt-docs" / "index.html")

    data_end = pd.Timestamp(k["data_end"])
    q_change = k["questions_12m"] / k["questions_prior_12m"] - 1 if k["questions_prior_12m"] else float("nan")
    m = data["monthly"]
    peak = m.loc[m["questions"].idxmax()]
    fast = (
        exp.set_index("signal").loc["first_q_answered_fast"]
        if "first_q_answered_fast" in set(exp["signal"])
        else None
    )
    km_s = km["summary"]
    cards = "".join(
        [
            _card(
                "Active contributors, last 12 months",
                _int(k["active_contributors_12m"]),
                f"{_int(k['contributors_all_time'])} people have ever contributed",
            ),
            _card(
                "Questions, last 12 months",
                _int(k["questions_12m"]),
                f"{_pct(q_change, True)} vs. the year before",
            ),
            _card(
                "Newcomers who came back",
                _pct(k["newcomer_came_back_rate"]),
                f"within 30 days; {_int(k['newcomers_12m'])} newcomers in the last year",
            ),
            _card(
                "Answered within 7 days",
                _pct(k["share_answered_7d"]),
                f"median first answer after {k['median_hours_to_answer']:.0f} hours",
            ),
            _card(
                "Top 10% of answerers", _pct(k["top10pct_answer_share"]), "write this share of all answers"
            ),
        ]
    )
    if fast is not None:
        headline = (
            f"Newcomers whose first question was answered within 24 hours came back "
            f"<b>{_pct(fast['rate_yes'])}</b> of the time, vs. <b>{_pct(fast['rate_no'])}</b> when it "
            f"wasn't ({_pp(fast['diff'])}, 95% CI {fast['diff_lo'] * 100:+.1f} to "
            f"{fast['diff_hi'] * 100:+.1f})."
        )
    else:
        headline = "Not enough recent newcomers to compare first experiences."
    km_note = ""
    if len(km_s) == 2:
        (la, a), (lb, b) = km_s.items()
        km_note = (
            f"After 90 days, {_pct(a['day90'])} of newcomers whose first question was answered within 24 hours "
            f"had come back, vs. {_pct(b['day90'])} of the others (log-rank p "
            f"{'< 0.001' if km['logrank_p'] < 0.001 else f'= {km["logrank_p"]:.3f}'})."
        )
    cox_html = (
        f"{_div(fig_cox(cox))}<p class='muted'>Cox proportional-hazards model on {cox_info['n']:,} newcomers whose first "
        f"contribution was a question ({cox_info['events']:,} came back within 180 days; concordance "
        f"{cox_info.get('concordance', float('nan')):.2f}). Each hazard ratio is adjusted for the other signals.</p>"
        if len(cox)
        else "<p class='muted'>Not enough data for the Cox model.</p>"
    )
    banner = (
        (
            "<div class='synthetic'>SYNTHETIC TEST DATA: this build was produced by the test suite, "
            "not from the Stack Exchange data dump.</div>"
        )
        if synthetic
        else ""
    )
    page = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Community Retention Analytics</title>
<meta name="description" content="Product analytics on Cross Validated (Stack Exchange): activation, cohort retention, growth accounting and what makes newcomers come back.">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📈</text></svg>">
<script src="https://cdn.plot.ly/plotly-{get_plotlyjs_version()}.min.js" charset="utf-8"></script>
<style>{CSS}</style></head>
<body>{banner}
<header><div class="wrap">
  <h1>What makes newcomers stick? Community retention on Cross Validated</h1>
  <p>Product analytics on {cfg.site_name}, Stack Exchange's statistics &amp; data science Q&amp;A community, from
  its public data dump ({data_end:%B %Y}): activation, cohort retention, growth accounting and the first-week
  experiences that predict whether a newcomer comes back.</p>
  <a class="btn" href="{cfg.repo_url}">Code on GitHub</a><a class="btn" href="dbt-docs/">dbt docs &amp; lineage</a>
</div></header>
<main>
<div class="cards">{cards}</div>

<section><h2>The long view</h2>
<p>Question volume peaked in {pd.Timestamp(peak["month"]):%B %Y} ({_int(peak["questions"])} questions).
{chatgpt_sentence(m)}</p>
<div class="grid2">{_div(fig_volume(m))}{_div(fig_active(m))}</div></section>

<section><h2>Growth accounting</h2>
<p>Every month's active contributors are either <b>new</b>, <b>retained</b> from last month, or <b>resurrected</b>
after a gap; <b>churned</b> contributors were active last month but not this one. When churn outweighs new plus
resurrected contributors, the active community shrinks.</p>
{_div(fig_growth(m))}</section>

<section><h2>Cohort retention</h2>
<p>Each row is the people who made their first contribution in that month (cohort size in brackets); each cell is the
share of them who contributed again N months later. Only complete months are shown.</p>
{_div(fig_cohorts(data["cohorts"]))}</section>

<section><h2>The newcomer funnel</h2>
<p>Most accounts never post. Of those who sign up each year: how many contribute within 30 days, how many of those
come back within 30 days of their first contribution, and how many are still contributing six months later.</p>
{_div(fig_funnel(data["funnel"]))}</section>

<section><h2>The aha moment: what makes newcomers come back?</h2>
<p>{headline} Below, every first-experience signal for newcomers from the last three years (only those with 30 days
of follow-up). These are associations in observational data, not proof of cause: a fast answer may partly reflect
a clearer question.</p>
{_div(fig_experience(exp)) if len(exp) else ""}
{experience_rows(exp) if len(exp) else ""}
<div class="grid2"><div>{_div(fig_km(km)) if km["curves"] else ""}<p class='muted'>{km_note}</p></div>
<div>{cox_html}</div></div></section>

<section><h2>North-star metric</h2>
<p>A Q&amp;A community exists to answer questions, so the north-star metric is <b>questions answered by another
user within 7 days</b>. It combines demand (people asking) with the community's capacity to help.</p>
<div class="grid2">{_div(fig_north_star(data["weekly"]))}{_div(fig_answer_share(data["weekly"]))}</div></section>

<section><h2>Who does the answering?</h2>
<p>In the last 12 months, the top 1% of answerers wrote <b>{_pct(k["top1pct_answer_share"])}</b> of all answers and
the top 10% wrote <b>{_pct(k["top10pct_answer_share"])}</b> ({_int(k["answerers_12m"])} people answered at least
once). {concentration_note(k["top10pct_answer_share"])}</p>
<div class="grid2">{_div(fig_lorenz(data["lorenz"]))}<div><h3>Share of answers by the most active answerers</h3>
{concentration_table(data["lorenz"])}</div></div></section>

<section><h2>Pipeline health</h2>
<p>The pipeline finds the newest dump on the Internet Archive, verifies its checksum, parses the XML into Parquet,
loads DuckDB and runs every dbt model and test; a failing test stops the site from being published.</p>
{health_section(art, data)}</section>

<section><h2>How it works</h2><ul class="method">
<li><b>Data:</b> the Stack Exchange data dump for {cfg.site} (users, posts, comments and votes; free text is not
loaded). Upvotes are anonymous and dated to the day in the public dump.</li>
<li><b>Modeling (dbt + DuckDB):</b> staging cleans each table; intermediate models build one row per contribution,
each question's outcome and each user's first contribution and next visit; marts hold <code>dim_users</code>,
<code>fct_contributions</code>, <code>fct_questions</code> and the metric tables.</li>
<li><b>Definitions:</b> a <i>contribution</i> is a question, answer or comment; <i>activated</i> = first
contribution within 30 days of signup; <i>came back</i> = another contribution on a later day within 30 days of the
first; growth accounting splits each month's contributors into new, retained and resurrected.</li>
<li><b>Statistics:</b> Wilson intervals for rates, normal-approximation intervals for differences, Kaplan–Meier
curves with a log-rank test, and a Cox proportional-hazards model (lifelines) for time to next visit.</li>
<li><b>Quality:</b> dbt data tests (keys, relationships, accepted values, ranges), singular tests (growth-accounting
identity, row reconciliation, month-0 retention = 100%), unit tests for the trickiest logic, and pytest.</li>
<li><b>Limits:</b> observational data, so signals are associations; deleted accounts are missing from the dump;
"came back" counts visible contributions only, not reading.</li>
</ul></section>
</main>
<footer>Data: Stack Exchange data dump ({cfg.site}), CC BY-SA, via the Internet Archive ·
<a href="{cfg.repo_url}">Source code</a></footer>
<script>{LAYOUT_JS}</script>
</body></html>"""
    (site / "index.html").write_text(page, encoding="utf-8")
    (site / ".nojekyll").touch()

    ts = art["test_status"]
    summary = {
        "dump_id": str(data["dump"].iloc[0]["dump_id"]),
        "data_start": str(k["data_start"]),
        "data_end": str(k["data_end"]),
        **{
            c: (float(k[c]) if isinstance(k[c], float | np.floating) else int(k[c]))
            for c in [
                "registered_users",
                "contributors_all_time",
                "contributions_all_time",
                "active_contributors_12m",
                "newcomers_12m",
                "newcomer_came_back_rate",
                "questions_12m",
                "questions_prior_12m",
                "share_answered_7d",
                "median_hours_to_answer",
                "top1pct_answer_share",
                "top10pct_answer_share",
                "answerers_12m",
            ]
        },
        "peak_month": str(pd.Timestamp(peak["month"]).date()),
        "peak_questions": int(peak["questions"]),
        "experience": exp.to_dict(orient="records"),
        "km": km_s,
        "logrank_p": km["logrank_p"],
        "cox": cox.to_dict(orient="records"),
        "cox_info": cox_info,
        "dbt": {
            "models": art["kinds"].get("model", 0),
            "data_tests": art["kinds"].get("test", 0),
            "unit_tests": art["kinds"].get("unit_test", 0),
            "passed": ts.get("pass", 0),
            "warnings": ts.get("warn", 0),
            "failed": ts.get("fail", 0) + ts.get("error", 0),
        },
        "synthetic": synthetic,
        "built_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
    }
    (site / "results.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary
