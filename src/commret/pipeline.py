"""End-to-end run: find & download the newest dump -> XML to Parquet -> DuckDB -> dbt build -> statistics -> site.

python -m commret.pipeline              # real data from the Internet Archive
python -m commret.pipeline --fixture    # offline run on synthetic test data (CI and tests only)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import duckdb

from . import analysis, download, fixture, parse
from .config import Config
from .readme import update_readme
from .report import build_site

log = logging.getLogger("commret")


class DbtFailed(RuntimeError):
    pass


def dbt(cfg: Config, args: list[str], target: Path, fatal: bool = True) -> bool:
    exe = shutil.which("dbt", path=str(Path(sys.executable).parent)) or shutil.which("dbt") or "dbt"
    env = {**os.environ, "COMMRET_DB_PATH": str(cfg.db_path), "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"}
    cmd = [
        exe,
        *args,
        "--project-dir",
        str(cfg.dbt_dir),
        "--profiles-dir",
        str(cfg.dbt_dir),
        "--target-path",
        str(target),
        "--log-path",
        str(target / "logs"),
    ]
    log.info("dbt %s", " ".join(args))
    ok = subprocess.run(cmd, env=env, check=False).returncode == 0
    if fatal and not ok:
        raise DbtFailed(f"`dbt {' '.join(args)}` failed; see the log above for the failing model or test.")
    return ok


def run(cfg: Config, *, use_fixture: bool = False) -> dict:
    t0 = time.time()
    target = cfg.dbt_dir / "target" if not use_fixture else cfg.data_dir / "dbt-target"
    target.mkdir(parents=True, exist_ok=True)

    # 1. Extract: newest dump from the Internet Archive (or synthetic XML for tests).
    if use_fixture:
        xml, dump_id = fixture.make_dump(cfg.data_dir / "xml"), "synthetic-fixture"
    else:
        xml, dump_id = download.fetch_site(cfg)

    # 2. Load: stream XML -> Parquet -> DuckDB raw tables.
    parquet = parse.parse_all(xml, cfg.data_dir / "parquet")
    counts = parse.load(cfg.db_path, parquet, dump_id, cfg.site)
    log.info("Loaded %s", counts)

    # 3. Transform & test.
    dbt(cfg, ["build"], target)
    shutil.copy(target / "run_results.json", target / "build_run_results.json")
    dbt(cfg, ["source", "freshness"], target, fatal=False)
    dbt(cfg, ["docs", "generate", "--static"], target)

    # 4. Statistics, website, README.
    con = duckdb.connect(str(cfg.db_path), read_only=True)
    first_experience = con.execute("select * from marts.mart_first_experience").df()
    con.close()
    stats = analysis.run(cfg.db_path, first_experience)
    summary = build_site(cfg, target, stats, synthetic=use_fixture)
    if not use_fixture:
        update_readme(cfg.readme_path, summary)
    log.info("Done in %.0fs. Site: %s", time.time() - t0, cfg.site_dir / "index.html")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--fixture", action="store_true", help="offline run on synthetic test data")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = Config()
    if args.fixture:
        tmp = Path(os.environ.get("COMMRET_FIXTURE_DIR", "/tmp/commret-fixture")).resolve()
        shutil.rmtree(tmp, ignore_errors=True)
        cfg = replace(cfg, data_dir=tmp, db_path=tmp / "community.duckdb", site_dir=tmp / "site")
    summary = run(cfg, use_fixture=args.fixture)
    print(
        json.dumps(
            {k: summary[k] for k in ("data_end", "active_contributors_12m", "newcomer_came_back_rate")},
            default=str,
        )
    )


if __name__ == "__main__":
    main()
