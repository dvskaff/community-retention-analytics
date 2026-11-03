"""Statistics on top of the dbt marts: confidence intervals, survival curves and a Cox model.

These are observational associations, not causal effects: newcomers whose first question gets a fast answer may
differ in other ways (clearer questions, popular topics). The Cox model adjusts for the other first-week signals and
the newcomer's signup-to-first-post delay, but cannot rule out unmeasured differences.
"""

from __future__ import annotations

import warnings

import duckdb
import numpy as np
import pandas as pd
from lifelines import CoxPHFitter, KaplanMeierFitter
from lifelines.statistics import logrank_test
from scipy import stats

HORIZON_DAYS = 180
WINDOW_YEARS = 3  # same as the dbt var experience_window_years

SIGNALS = {
    "first_q_answered_fast": "First question answered within 24 hours",
    "first_q_commented_fast": "First question got a comment within 24 hours",
    "first_q_upvoted_early": "First question upvoted in its first week",
    "first_q_downvoted_early": "First question downvoted in its first week",
    "first_q_closed_7d": "First question closed within a week",
    "first_a_upvoted_early": "First answer upvoted in its first week",
    "first_a_accepted": "First answer accepted by the asker",
}


def wilson(k: np.ndarray, n: np.ndarray, z: float = 1.96) -> tuple[np.ndarray, np.ndarray]:
    """Wilson score interval for a proportion (well-behaved for small n and rates near 0 or 1)."""
    k, n = np.asarray(k, float), np.asarray(n, float)
    p = np.divide(k, n, out=np.zeros_like(k), where=n > 0)
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return centre - half, centre + half


def experience_table(fe: pd.DataFrame) -> pd.DataFrame:
    """One row per signal: came-back rate with and without it, the difference and its 95% CI."""
    rows = []
    for signal, label in SIGNALS.items():
        s = fe[fe["signal"] == signal].set_index("has_signal")
        if True not in s.index or False not in s.index:
            continue
        yes, no = s.loc[True], s.loc[False]
        if min(yes["newcomers"], no["newcomers"]) < 20:
            continue
        p1, p0 = yes["came_back_rate"], no["came_back_rate"]
        se = np.sqrt(p1 * (1 - p1) / yes["newcomers"] + p0 * (1 - p0) / no["newcomers"])
        (lo1,), (hi1,) = wilson([yes["came_back"]], [yes["newcomers"]])
        (lo0,), (hi0,) = wilson([no["came_back"]], [no["newcomers"]])
        z = (p1 - p0) / se if se > 0 else 0.0
        rows.append(
            {
                "signal": signal,
                "label": label,
                "first_type": yes["first_contribution_type"],
                "n_yes": int(yes["newcomers"]),
                "rate_yes": p1,
                "lo_yes": lo1,
                "hi_yes": hi1,
                "n_no": int(no["newcomers"]),
                "rate_no": p0,
                "lo_no": lo0,
                "hi_no": hi0,
                "diff": p1 - p0,
                "diff_lo": p1 - p0 - 1.96 * se,
                "diff_hi": p1 - p0 + 1.96 * se,
                "p_value": float(2 * stats.norm.sf(abs(z))),
            }
        )
    return pd.DataFrame(rows).sort_values("diff", ascending=False).reset_index(drop=True)


def newcomer_frame(db_path) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return con.execute(f"""
            select u.*, year(u.first_contribution_at) as cohort_year
            from marts.dim_users u
            where u.is_contributor and u.first_contribution_type = 'question'
              and u.first_contribution_at >= (select max(created_at) from marts.fct_contributions)
                                             - interval {WINDOW_YEARS} year
              and u.follow_up_days >= 31
        """).df()
    finally:
        con.close()


def survival_data(df: pd.DataFrame) -> pd.DataFrame:
    """Time until the next visit, censored at the end of the data or at the 180-day horizon."""
    returned = df["days_to_next_visit"].notna()
    duration = np.where(returned, df["days_to_next_visit"], df["follow_up_days"]).astype(float)
    event = returned & (duration <= HORIZON_DAYS)
    out = df.assign(duration=np.clip(np.minimum(duration, HORIZON_DAYS), 0.01, None), event=event.astype(int))
    return out


def kaplan_meier(sd: pd.DataFrame, group: str = "first_q_answered_fast") -> dict:
    curves, at = {}, {}
    grid = np.arange(0, HORIZON_DAYS + 1)
    for flag, label in ((True, "Answered within 24 h"), (False, "Not answered within 24 h")):
        g = sd[sd[group] == flag]
        if len(g) < 10:
            continue
        km = KaplanMeierFitter().fit(g["duration"], g["event"], label=label)
        returned = 1 - km.survival_function_at_times(grid).to_numpy()
        curves[label] = pd.DataFrame({"day": grid, "share_returned": returned})
        at[label] = {
            "n": int(len(g)),
            "day30": float(returned[30]),
            "day90": float(returned[90]),
            "day180": float(returned[HORIZON_DAYS]),
        }
    yes, no = sd[sd[group]], sd[~sd[group].astype(bool)]
    p = (
        logrank_test(yes["duration"], no["duration"], yes["event"], no["event"]).p_value
        if len(yes) >= 10 and len(no) >= 10
        else float("nan")
    )
    return {"curves": curves, "summary": at, "logrank_p": float(p)}


COX_COVARIATES = {
    "first_q_answered_fast": "Answered within 24 h",
    "first_q_commented_fast": "Comment within 24 h",
    "first_q_upvoted_early": "Upvoted in first week",
    "first_q_downvoted_early": "Downvoted in first week",
    "first_q_closed_7d": "Closed within a week",
    "log_days_signup_to_first": "Days from signup to first post (log)",
}


def cox_model(sd: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Cox proportional hazards on time to next visit. HR > 1: newcomers with that signal come back sooner."""
    d = sd.copy()
    for c in [c for c in COX_COVARIATES if c.startswith("first_q")]:
        d[c] = d[c].fillna(False).astype(int)
    d["log_days_signup_to_first"] = np.log1p(d["days_signup_to_first"].clip(lower=0).fillna(0))
    cols = [c for c in COX_COVARIATES if d[c].nunique() > 1]
    if len(d) < 50 or d["event"].sum() < 20 or not cols:
        return pd.DataFrame(), {"n": int(len(d)), "events": int(d["event"].sum())}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cph = CoxPHFitter(penalizer=0.01).fit(d[[*cols, "duration", "event"]], "duration", "event")
    s = cph.summary
    table = pd.DataFrame(
        {
            "covariate": [COX_COVARIATES[c] for c in s.index],
            "hazard_ratio": s["exp(coef)"].to_numpy(),
            "lo": s["exp(coef) lower 95%"].to_numpy(),
            "hi": s["exp(coef) upper 95%"].to_numpy(),
            "p_value": s["p"].to_numpy(),
        }
    )
    return table, {
        "n": int(len(d)),
        "events": int(d["event"].sum()),
        "concordance": float(cph.concordance_index_),
    }


def run(db_path, first_experience: pd.DataFrame) -> dict:
    exp = experience_table(first_experience)
    sd = survival_data(newcomer_frame(db_path))
    km = kaplan_meier(sd) if len(sd) else {"curves": {}, "summary": {}, "logrank_p": float("nan")}
    cox, cox_info = cox_model(sd) if len(sd) else (pd.DataFrame(), {"n": 0, "events": 0})
    return {"experience": exp, "km": km, "cox": cox, "cox_info": cox_info}
