"""Find, download and unpack the newest Stack Exchange data dump for one site from the Internet Archive.

The dumps are published as 7-Zip archives of XML files. Older dumps put a whole site in one archive
(`stats.stackexchange.com.7z`); very large sites are split per table (`site-Posts.7z`). Both layouts are handled.
Every file is checked against the MD5 published in the archive's metadata, so a truncated download fails loudly.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Config

log = logging.getLogger(__name__)
ARCHIVE = "https://archive.org"
ITEM_RE = re.compile(r"^stackexchange(_\d{8})?$")


@dataclass
class DumpFile:
    item: str
    name: str
    size: int | None
    md5: str | None

    @property
    def url(self) -> str:
        return f"{ARCHIVE}/download/{self.item}/{self.name}"


def session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=6, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=["GET"]
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers["User-Agent"] = (
        "community-retention-analytics (github.com/dvskaff/community-retention-analytics)"
    )
    return s


def site_files(files: list[dict], site: str) -> list[dict]:
    """Archive entries for one site: either `site.7z` or per-table `site-Table.7z` files."""
    pattern = re.compile(rf"^{re.escape(site)}(-[A-Za-z]+)?\.7z$")
    return [f for f in files if pattern.match(f.get("name", ""))]


def candidate_items(http: requests.Session, cfg: Config) -> list[str]:
    """Newest-first list of dump items: anything found by search, then the known items as a fallback."""
    found: list[str] = []
    try:
        r = http.get(
            f"{ARCHIVE}/advancedsearch.php",
            timeout=60,
            params={
                "q": "identifier:stackexchange*",
                "fl[]": "identifier",
                "sort[]": "publicdate desc",
                "rows": 50,
                "output": "json",
            },
        )
        r.raise_for_status()
        found = [d["identifier"] for d in r.json()["response"]["docs"] if ITEM_RE.match(d["identifier"])]
    except Exception as exc:  # search is a convenience; the known items still work
        log.warning("Archive search failed (%s); using the known dump items", exc)
    dated = sorted((i for i in set(found) | set(cfg.known_items) if i != "stackexchange"), reverse=True)
    return dated + ["stackexchange"]


def find_dump(cfg: Config, http: requests.Session | None = None) -> list[DumpFile]:
    http = http or session()
    for item in candidate_items(http, cfg):
        try:
            r = http.get(f"{ARCHIVE}/metadata/{item}", timeout=60)
            r.raise_for_status()
            all_files = r.json().get("files", [])
            files = site_files(all_files, cfg.site)
        except Exception as exc:
            log.warning("Could not read archive item %s: %s", item, exc)
            continue
        if not files:
            label = cfg.site.split(".")[0]
            similar = [f["name"] for f in all_files if f.get("name", "").startswith(label + ".")][:5]
            log.info(
                "Archive item %s has no %s archive%s; trying an older dump",
                item,
                cfg.site,
                f" (similar files: {similar})" if similar else "",
            )
            continue
        log.info("Using dump %s: %s", item, ", ".join(f["name"] for f in files))
        return [
            DumpFile(item, f["name"], int(f["size"]) if f.get("size") else None, f.get("md5")) for f in files
        ]
    raise RuntimeError(f"No Stack Exchange dump containing {cfg.site} was found on the Internet Archive.")


def md5sum(path: Path) -> str:
    h = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(f: DumpFile, dest_dir: Path, http: requests.Session | None = None) -> Path:
    http = http or session()
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f.name
    if out.exists() and f.md5 and md5sum(out) == f.md5:
        log.info("Already downloaded: %s", out.name)
        return out
    log.info("Downloading %s (%s MB)", f.url, f"{(f.size or 0) / 1e6:,.0f}")
    with http.get(f.url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with out.open("wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
    if f.md5 and md5sum(out) != f.md5:
        out.unlink()
        raise RuntimeError(
            f"Checksum mismatch for {f.name}; the download was incomplete. Re-run the pipeline."
        )
    return out


def extract(archive: Path, tables: tuple[str, ...], dest_dir: Path) -> dict[str, Path]:
    """Extract Table.xml files from a 7z archive (7z command if installed, else the py7zr library)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    wanted = [f"{t}.xml" for t in tables]
    exe = shutil.which("7z") or shutil.which("7za")
    if exe:
        subprocess.run(
            [exe, "e", "-y", f"-o{dest_dir}", str(archive), *wanted, "-r"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    else:
        import py7zr

        with py7zr.SevenZipFile(archive) as z:
            names = [n for n in z.getnames() if Path(n).name in wanted]
            z.extract(path=dest_dir, targets=names)
        for n in names:  # flatten any folder structure inside the archive
            src = dest_dir / n
            if src.parent != dest_dir:
                src.replace(dest_dir / src.name)
    return {t: dest_dir / f"{t}.xml" for t in tables if (dest_dir / f"{t}.xml").exists()}


def fetch_site(cfg: Config) -> tuple[dict[str, Path], str]:
    """Download and unpack the newest dump for the configured site. Returns XML paths and the dump id."""
    http = session()
    files = find_dump(cfg, http)
    xml: dict[str, Path] = {}
    for f in files:
        archive = download(f, cfg.data_dir / "archives", http)
        xml.update(extract(archive, cfg.tables, cfg.data_dir / "xml"))
    missing = [t for t in cfg.tables if t not in xml]
    if missing:
        raise RuntimeError(f"The dump did not contain {missing}.xml")
    return xml, files[0].item
