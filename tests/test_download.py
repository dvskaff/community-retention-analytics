from dataclasses import replace

import pytest

from commret import download, fixture
from commret.config import Config


def test_site_files_matches_whole_site_and_per_table_archives():
    files = [
        {"name": "stats.stackexchange.com.7z"},
        {"name": "stats.meta.stackexchange.com.7z"},
        {"name": "stats.stackexchange.com-Posts.7z"},
        {"name": "stats.stackexchange.com.7z.torrent"},
    ]
    names = [f["name"] for f in download.site_files(files, "stats.stackexchange.com")]
    assert names == ["stats.stackexchange.com.7z", "stats.stackexchange.com-Posts.7z"]


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeHttp:
    """Answers the archive search and metadata endpoints like archive.org does."""

    def __init__(self, items: dict[str, list[dict]], search: list[str]):
        self.items, self.search = items, search

    def get(self, url, **kwargs):
        if "advancedsearch" in url:
            return FakeResponse({"response": {"docs": [{"identifier": i} for i in self.search]}})
        item = url.rsplit("/", 1)[-1]
        return FakeResponse({"files": self.items.get(item, [])})


def test_find_dump_prefers_the_newest_item_that_has_the_site():
    http = FakeHttp(
        items={
            "stackexchange_20260630": [
                {"name": "stackoverflow.com-Posts.7z"}
            ],  # newest, but no Cross Validated
            "stackexchange_20251231": [{"name": "stats.stackexchange.com.7z", "size": "1000", "md5": "abc"}],
            "stackexchange": [{"name": "stats.stackexchange.com.7z", "size": "900", "md5": "def"}],
        },
        search=[
            "stackexchange",
            "stackexchange_20260630",
            "stackexchange_20251231",
            "stackexchange-mirror-x",
        ],
    )
    files = download.find_dump(Config(), http)
    assert [(f.item, f.name, f.md5) for f in files] == [
        ("stackexchange_20251231", "stats.stackexchange.com.7z", "abc")
    ]
    assert files[0].url == "https://archive.org/download/stackexchange_20251231/stats.stackexchange.com.7z"


def test_find_dump_fails_clearly_when_nothing_matches():
    with pytest.raises(RuntimeError, match="stats.stackexchange.com"):
        download.find_dump(Config(), FakeHttp(items={}, search=[]))


def test_extract_pulls_only_the_needed_tables(tmp_path):
    xml = fixture.make_dump(tmp_path / "src", n_users=60)
    archive = fixture.make_7z(xml, tmp_path / "site.7z")
    out = download.extract(archive, ("Users", "Posts"), tmp_path / "out")
    assert sorted(out) == ["Posts", "Users"] and all(p.exists() for p in out.values())


def test_md5_matches_hashlib(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"abc")
    assert download.md5sum(f) == "900150983cd24fb0d6963f7d28e17f72"


def test_config_paths_can_be_redirected(tmp_path):
    cfg = replace(Config(), data_dir=tmp_path)
    assert cfg.data_dir == tmp_path
