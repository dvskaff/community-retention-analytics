"""End to end on synthetic data: XML -> Parquet -> DuckDB -> dbt build (all tests) -> statistics -> website."""

import json
import shutil
from dataclasses import replace

import pytest

from commret.config import Config
from commret.pipeline import run
from commret.readme import update_readme

pytestmark = pytest.mark.skipif(shutil.which("dbt") is None, reason="dbt not installed")


def test_full_pipeline_on_fixture(tmp_path):
    cfg = replace(
        Config(),
        data_dir=tmp_path / "data",
        db_path=tmp_path / "data" / "c.duckdb",
        site_dir=tmp_path / "site",
    )
    s = run(cfg, use_fixture=True)

    page = (tmp_path / "site" / "index.html").read_text()
    assert "SYNTHETIC TEST DATA" in page and (tmp_path / "site" / "dbt-docs" / "index.html").exists()
    assert json.loads((tmp_path / "site" / "results.json").read_text())["synthetic"] is True
    assert s["dbt"]["failed"] == 0 and s["dbt"]["models"] >= 19

    # The fixture builds in "a fast first answer doubles the chance of coming back"; the analysis must find it.
    fast = next(e for e in s["experience"] if e["signal"] == "first_q_answered_fast")
    assert fast["diff_lo"] > 0
    hr = next(c for c in s["cox"] if c["covariate"].startswith("Answered within"))
    assert hr["lo"] > 1

    readme = tmp_path / "README.md"
    readme.write_text("# T\n<!-- RESULTS:START -->\nold\n<!-- RESULTS:END -->\nend\n")
    update_readme(readme, s)
    text = readme.read_text()
    assert "Aha moment" in text and "\nold\n" not in text and text.endswith("end\n")
