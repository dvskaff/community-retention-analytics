import duckdb
import numpy as np
import pandas as pd
import pytest

from commret import analysis, fixture, parse


def test_xml_rows_become_parquet_and_raw_tables(tmp_path):
    xml = fixture.make_dump(tmp_path / "xml", n_users=80)
    pq = parse.parse_all(xml, tmp_path / "pq")
    counts = parse.load(tmp_path / "w.duckdb", pq, "test-dump", "stats.stackexchange.com")
    assert counts["users"] == 81  # 80 people + the Community account
    con = duckdb.connect(str(tmp_path / "w.duckdb"))
    cols = [r[0] for r in con.execute("describe raw.posts").fetchall()]
    assert cols == list(parse.FIELDS["Posts"]) and "Body" not in cols  # free text is never loaded
    assert con.execute("select dump_id from raw.dump_info").fetchall() == [("test-dump",)]


def test_wilson_interval_known_values():
    lo, hi = analysis.wilson(np.array([50]), np.array([100]))
    assert lo[0] == pytest.approx(0.4038, abs=1e-3) and hi[0] == pytest.approx(0.5962, abs=1e-3)
    lo, hi = analysis.wilson(np.array([0]), np.array([20]))
    assert lo[0] == pytest.approx(0, abs=1e-9) and 0 < hi[0] < 0.2


def test_experience_table_computes_difference_and_ci():
    fe = pd.DataFrame(
        [
            {
                "signal": "first_q_answered_fast",
                "first_contribution_type": "question",
                "has_signal": True,
                "newcomers": 400,
                "came_back": 200,
                "came_back_rate": 0.5,
            },
            {
                "signal": "first_q_answered_fast",
                "first_contribution_type": "question",
                "has_signal": False,
                "newcomers": 400,
                "came_back": 120,
                "came_back_rate": 0.3,
            },
            {
                "signal": "first_q_closed_7d",
                "first_contribution_type": "question",
                "has_signal": True,
                "newcomers": 5,
                "came_back": 1,
                "came_back_rate": 0.2,
            },  # too small: dropped
            {
                "signal": "first_q_closed_7d",
                "first_contribution_type": "question",
                "has_signal": False,
                "newcomers": 795,
                "came_back": 319,
                "came_back_rate": 0.4,
            },
        ]
    )
    t = analysis.experience_table(fe)
    assert list(t["signal"]) == ["first_q_answered_fast"]
    row = t.iloc[0]
    assert row["diff"] == pytest.approx(0.2)
    assert row["diff_lo"] < 0.2 < row["diff_hi"] and row["p_value"] < 1e-6


def test_cox_recovers_a_known_effect():
    rng = np.random.default_rng(0)
    n = 2000
    fast = rng.random(n) < 0.5
    # Exponential return times: the fast group returns twice as fast (true hazard ratio = 2).
    t = rng.exponential(np.where(fast, 30, 60))
    sd = pd.DataFrame(
        {
            "days_to_next_visit": t,
            "follow_up_days": 400.0,
            "days_signup_to_first": rng.exponential(5, n),
            "first_q_answered_fast": fast,
            "first_q_commented_fast": rng.random(n) < 0.3,
            "first_q_upvoted_early": False,
            "first_q_downvoted_early": False,
            "first_q_closed_7d": False,
        }
    )
    table, info = analysis.cox_model(analysis.survival_data(sd))
    hr = table.set_index("covariate").loc["Answered within 24 h"]
    assert hr["lo"] < 2 < hr["hi"] and info["events"] > 1000
