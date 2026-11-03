"""Project settings. Paths can be overridden with environment variables (used by tests and CI)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _path(env: str, default: Path) -> Path:
    return Path(os.environ[env]).resolve() if os.environ.get(env) else default


@dataclass
class Config:
    # Which Stack Exchange site to analyze. Cross Validated is Stack Exchange's statistics & data science Q&A.
    site: str = "stats.stackexchange.com"
    site_name: str = "Cross Validated"
    # Data dumps on the Internet Archive, newest first. The pipeline also searches for newer ones on every run.
    known_items: tuple[str, ...] = ("stackexchange_20251231", "stackexchange")
    tables: tuple[str, ...] = ("Users", "Posts", "Comments", "Votes")

    data_dir: Path = field(default_factory=lambda: _path("COMMRET_DATA_DIR", ROOT / "data"))
    db_path: Path = field(
        default_factory=lambda: _path("COMMRET_DB_PATH", ROOT / "data" / "community.duckdb")
    )
    dbt_dir: Path = field(default_factory=lambda: ROOT / "dbt")
    site_dir: Path = field(default_factory=lambda: _path("COMMRET_SITE_DIR", ROOT / "site"))
    readme_path: Path = field(default_factory=lambda: ROOT / "README.md")

    repo_url: str = "https://github.com/dvskaff/community-retention-analytics"
    site_url: str = "https://dvskaff.github.io/community-retention-analytics/"
