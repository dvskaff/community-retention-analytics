"""SYNTHETIC Stack Exchange-style XML used only by the tests and CI (never published as results).

It mimics the dump's format exactly (one <row/> per record, attributes as fields, the Community user with Id -1,
anonymous upvotes, deleted owners) and builds in a known pattern, newcomers whose first question gets a fast
answer come back more often, so the end-to-end tests can check that the analysis recovers it.
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import quoteattr

import numpy as np
import pandas as pd

TAGS = ["regression", "r", "machine-learning", "hypothesis-testing", "bayesian", "time-series", "probability"]


def _ts(t: pd.Timestamp) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}"


def _write(path: Path, root: str, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        fh.write(f'<?xml version="1.0" encoding="utf-8"?>\n<{root}>\n')
        for r in rows:
            attrs = " ".join(f"{k}={quoteattr(str(v))}" for k, v in r.items() if v is not None)
            fh.write(f"  <row {attrs} />\n")
        fh.write(f"</{root}>\n")


def make_dump(
    out_dir: Path, n_users: int = 1500, start: str = "2016-01-01", end: str = "2025-12-31", seed: int = 11
) -> dict[str, Path]:
    rng = np.random.default_rng(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    t0, t1 = pd.Timestamp(start), pd.Timestamp(end)
    span = (t1 - t0).total_seconds()
    users = [{"Id": -1, "CreationDate": _ts(t0), "Reputation": 1, "LastAccessDate": _ts(t0), "AccountId": -1}]
    posts, comments, votes = [], [], []
    pid = cid = vid = 0
    expert_ids = list(range(1, 41))  # a core of regular answerers
    signup = {}
    for uid in range(1, n_users + 1):
        s = t0 + pd.Timedelta(seconds=span * rng.random() ** 0.8)
        signup[uid] = s
        users.append(
            {
                "Id": uid,
                "CreationDate": _ts(s),
                "Reputation": int(rng.integers(1, 5000)),
                "LastAccessDate": _ts(min(t1, s + pd.Timedelta(days=int(rng.integers(1, 900))))),
                "AccountId": 100000 + uid,
            }
        )

    def add_answer(q_id, q_time, answerer, delay_h):
        nonlocal pid, vid
        pid += 1
        at = q_time + pd.Timedelta(hours=delay_h)
        posts.append(
            {
                "Id": pid,
                "PostTypeId": 2,
                "ParentId": q_id,
                "OwnerUserId": answerer,
                "CreationDate": _ts(at),
                "Score": int(rng.integers(-1, 6)),
                "CommentCount": 0,
            }
        )
        for _ in range(int(rng.integers(0, 3))):
            vid += 1
            votes.append(
                {
                    "Id": vid,
                    "PostId": pid,
                    "VoteTypeId": 2,
                    "CreationDate": _ts((at + pd.Timedelta(days=int(rng.integers(0, 10)))).normalize()),
                }
            )
        return pid, at

    for uid in range(1, n_users + 1):
        if uid in expert_ids or rng.random() < 0.45:  # lurkers never contribute
            continue
        t = signup[uid] + pd.Timedelta(hours=float(rng.exponential(72)))
        sessions = 0
        while t < t1 and sessions < 30:
            pid += 1
            q_id, q_time = pid, t
            tag = rng.choice(TAGS, size=2, replace=False)
            q = {
                "Id": q_id,
                "PostTypeId": 1,
                "OwnerUserId": uid,
                "CreationDate": _ts(q_time),
                "Score": int(rng.integers(-2, 8)),
                "ViewCount": int(rng.integers(10, 5000)),
                "Tags": f"|{tag[0]}|{tag[1]}|",
                "AnswerCount": 0,
                "CommentCount": 0,
            }
            if rng.random() < 0.03:
                q["ClosedDate"] = _ts(q_time + pd.Timedelta(days=1))
            posts.append(q)
            fast = rng.random() < 0.5
            answered = fast or rng.random() < 0.5
            if answered:
                a_id, _ = add_answer(
                    q_id,
                    q_time,
                    int(rng.choice(expert_ids)),
                    rng.uniform(0.2, 20) if fast else rng.uniform(30, 400),
                )
                q["AnswerCount"] = 1
                if rng.random() < 0.5:
                    q["AcceptedAnswerId"] = a_id
            if rng.random() < 0.4:
                cid += 1
                comments.append(
                    {
                        "Id": cid,
                        "PostId": q_id,
                        "UserId": int(rng.choice(expert_ids)),
                        "CreationDate": _ts(q_time + pd.Timedelta(hours=float(rng.uniform(0.1, 48)))),
                        "Score": 0,
                    }
                )
                q["CommentCount"] = 1
            sessions += 1
            # Built-in pattern: a fast first answer makes the asker much more likely to come back.
            p_return = 0.7 if (sessions == 1 and fast) else (0.35 if sessions == 1 else 0.75)
            if rng.random() > p_return:
                break
            t = t + pd.Timedelta(days=float(rng.exponential(25)))
    # Expert answers on their own schedule plus a few deleted-owner posts and Community-owned wiki posts.
    for _ in range(300):
        pid += 1
        posts.append(
            {
                "Id": pid,
                "PostTypeId": 1,
                "CreationDate": _ts(t0 + pd.Timedelta(seconds=span * rng.random())),
                "Score": 0,
                "Tags": "|r|",
                "AnswerCount": 0,
                "CommentCount": 0,
            }
        )  # owner deleted
    pid += 1
    posts.append({"Id": pid, "PostTypeId": 5, "OwnerUserId": -1, "CreationDate": _ts(t0), "Score": 0})
    paths = {}
    for name, rows in {"Users": users, "Posts": posts, "Comments": comments, "Votes": votes}.items():
        paths[name] = out_dir / f"{name}.xml"
        _write(paths[name], name.lower(), rows)
    return paths


def make_7z(xml: dict[str, Path], archive: Path) -> Path:
    import py7zr

    with py7zr.SevenZipFile(archive, "w") as z:
        for path in xml.values():
            z.write(path, arcname=path.name)
    return archive
