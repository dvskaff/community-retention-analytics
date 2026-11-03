"""Static dashboard (site/index.html) built from the dbt marts, the survival analysis and dbt's run artifacts."""

from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

BLUE, ORANGE, AQUA, YELLOW, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#6250d6"
SERIES = [BLUE, ORANGE, AQUA, YELLOW, VIOLET]
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
GOOD, WARN, BAD = "#1a7f37", "#b7791f", "#c4352b"
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


# --------------------------------------------------------------------------- plotting helpers
def _style(
    fig: go.Figure, title: str = "", height: int = 360, y_title: str = "", x_title: str = "", **layout
):
    base = dict(
        title=dict(text=title, x=0, xanchor="left", font=dict(size=15, color=INK)) if title else None,
        height=height,
        margin=dict(l=64, r=20, t=74 if title else 30, b=48),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family=FONT, size=12, color=INK2),
        hovermode="x unified",
        hoverlabel=dict(font=dict(family=FONT)),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_layout(**{**base, **layout})
    fig.update_xaxes(
        showgrid=False,
        linecolor=AXIS,
        tickfont=dict(color=MUTED),
        zeroline=False,
        title=dict(text=x_title, font=dict(color=MUTED)),
    )
    fig.update_yaxes(
        gridcolor=GRID,
        linecolor=AXIS,
        tickfont=dict(color=MUTED),
        zeroline=False,
        title=dict(text=y_title, font=dict(color=MUTED)),
    )
    return fig


def _div(fig: go.Figure) -> str:
    return fig.to_html(
        full_html=False, include_plotlyjs=False, config={"displaylogo": False, "responsive": True}
    )


def _days(v) -> str:
    return "–" if pd.isna(v) else f"{v:.1f}"


def _pct(v, signed=False) -> str:
    return "–" if pd.isna(v) else (f"{v:+.0%}" if signed else f"{v:.0%}")


def _pts(v) -> str:
    return "–" if pd.isna(v) else f"{v * 100:+.1f} pts"


def _int(v) -> str:
    return "–" if pd.isna(v) else f"{int(v):,}"


# --------------------------------------------------------------------------- data access
def load_artifacts(target: Path) -> dict:
    manifest = json.loads((target / "manifest.json").read_text())
    build = json.loads((target / "build_run_results.json").read_text())
    sources_path = target / "sources.json"
    sources = json.loads(sources_path.read_text()) if sources_path.exists() else {"results": []}

    nodes = manifest["nodes"]
    status = Counter(r["status"] for r in build["results"])
    test_results = [r for r in build["results"] if r["unique_id"].startswith(("test.", "unit_test."))]
    test_status = Counter(r["status"] for r in test_results)
    warnings = [
        (nodes.get(r["unique_id"], {}).get("name", r["unique_id"].split(".")[-1]), r.get("failures"))
        for r in test_results
        if r["status"] == "warn"
    ]
    kinds = Counter(n["resource_type"] for n in nodes.values())
    kinds["unit_test"] = len(manifest.get("unit_tests", {}))

    layers: dict[str, list[tuple[str, str]]] = {
        "Sources": [],
        "Staging": [],
        "Intermediate": [],
        "Marts": [],
        "Exposure": [],
    }
    for src in manifest["sources"].values():
        layers["Sources"].append((f"{src['schema']}.{src['name']}", "source"))
    for n in nodes.values():
        if n["resource_type"] == "model":
            folder = n["fqn"][1] if len(n["fqn"]) > 2 else "marts"
            key = {"staging": "Staging", "intermediate": "Intermediate"}.get(folder, "Marts")
            layers[key].append((n["name"], n["config"]["materialized"]))
        elif n["resource_type"] == "snapshot":
            layers.setdefault("Snapshots", []).append((n["name"], "snapshot"))
        elif n["resource_type"] == "seed":
            layers["Sources"].append((n["name"], "seed"))
    for e in manifest.get("exposures", {}).values():
        layers["Exposure"].append((e.get("label") or e["name"], e["type"]))

    fresh = next((r for r in sources["results"] if r["unique_id"].endswith(".posts")), None)
    return {
        "dbt_version": manifest["metadata"]["dbt_version"],
        "status": status,
        "test_status": test_status,
        "warnings": warnings,
        "kinds": kinds,
        "layers": {k: sorted(v) for k, v in layers.items()},
        "freshness": fresh,
        "elapsed": build.get("elapsed_time", 0),
    }


def _table(headers: list[str], rows: list[list[str]], left_cols: int = 1) -> str:
    th = "".join(f"<th class='{'l' if i < left_cols else ''}'>{h}</th>" for i, h in enumerate(headers))
    body = "".join(
        "<tr>"
        + "".join(f"<td class='{'l' if i < left_cols else ''}'>{c}</td>" for i, c in enumerate(r))
        + "</tr>"
        for r in rows
    )
    return f"<div class='tablewrap'><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>"


def _delta_class(v, good_when_positive: bool) -> str:
    if pd.isna(v) or abs(v) < 0.005:
        return ""
    return "pos" if (v > 0) == good_when_positive else "neg"


def _breakable(name: str) -> str:
    """Let long model names wrap at underscores and dots instead of mid-word."""
    return html.escape(name).replace("_", "_<wbr>").replace(".", ".<wbr>")


def _card(label: str, value: str, note: str = "") -> str:
    return (
        f"<div class='card'><div class='label'>{label}</div><div class='value'>{value}</div>"
        f"<div class='note'>{note}</div></div>"
    )


def health_section(art: dict, data: dict) -> str:
    ts, k = art["test_status"], art["kinds"]
    failed = ts.get("fail", 0) + ts.get("error", 0)
    test_line = (
        f"<span class='chip good'>✓ {ts.get('pass', 0)} passed</span>"
        f"<span class='chip warn'>⚠ {ts.get('warn', 0)} warning{'' if ts.get('warn', 0) == 1 else 's'}</span>"
        f"<span class='chip {'bad' if failed else 'good'}'>{'✗' if failed else '✓'} {failed} failed</span>"
    )
    fr = art["freshness"]
    if fr:
        age_d = (fr.get("max_loaded_at_time_ago_in_s") or 0) / 86400
        cls = {"pass": "good", "warn": "warn"}.get(fr["status"], "bad")
        fresh = (
            f"<span class='chip {cls}'>{fr['status'].upper()}</span> newest post in the dump is "
            f"{age_d:.0f} days old (dumps are published every few months; warn after 200 days, error after 400)"
        )
    else:
        fresh = "<span class='chip warn'>not checked</span>"
    d = data["dump"].iloc[0]
    load_line = (
        f"archive item <code>{html.escape(str(d['dump_id']))}</code>, loaded "
        f"{pd.Timestamp(d['loaded_at']):%b %d, %Y %H:%M} UTC"
    )
    warn_list = "".join(
        f"<li><code>{html.escape(n)}</code>: {f or 0:,} rows flagged</li>" for n, f in art["warnings"]
    )
    warn_html = (
        f"<p class='muted'>Warnings (logged, not blocking):</p><ul class='small'>{warn_list}</ul>"
        if warn_list
        else ""
    )
    layer_rows = [
        [html.escape(r.layer), f"<code>{r.relation}</code>", _int(r.row_count)]
        for r in data["layers"].itertuples(index=False)
    ]
    lineage = "".join(
        f"<div class='lcol'><div class='lhead'>{name}</div>"
        + "".join(f"<div class='lnode'><span>{_breakable(n)}</span><em>{m}</em></div>" for n, m in nodes)
        + "</div>"
        for name, nodes in art["layers"].items()
        if nodes
    )
    return f"""
<div class='grid2'>
  <div>
    <h3>Latest run</h3>
    <p><b>Data:</b> {load_line}</p>
    <p><b>Data tests:</b> {test_line}</p>
    <p><b>Source freshness:</b> {fresh}</p>
    <p class='muted'>dbt {art["dbt_version"]} · {k.get("model", 0)} models · {k.get("test", 0)} data tests ·
       {k.get("unit_test", 0)} unit tests · build took {art["elapsed"]:.0f}s</p>
    {warn_html}
  </div>
  <div><h3>Rows by layer</h3>{_table(["Layer", "Relation", "Rows"], layer_rows, left_cols=2)}</div>
</div>
<h3>Lineage</h3>
<div class='lineage'>{lineage}</div>
"""


# --------------------------------------------------------------------------- page
CSS = """
:root { --ink:#0b0b0b; --ink2:#52514e; --muted:#898781; --grid:#e1e0d9; --surface:#fcfcfb; --page:#f9f9f7; }
* { box-sizing:border-box; }
body { margin:0; background:var(--page); color:var(--ink); font-family:%FONT%; line-height:1.55; }
header { background:#104281; color:#fff; padding:40px 16px 32px; }
header .wrap, main { max-width:1140px; margin:0 auto; }
header h1 { margin:0 0 6px; font-size:clamp(24px,4vw,34px); letter-spacing:-0.01em; }
header p { margin:0; color:#cde2fb; max-width:820px; }
header a { color:#fff; }
.synthetic { background:#c4352b; color:#fff; text-align:center; padding:8px 16px; font-weight:600; }
main { padding:24px 16px 64px; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:12px; margin-bottom:28px; }
.card { background:var(--surface); border:1px solid rgba(11,11,11,.10); border-radius:12px; padding:14px 16px; }
.card .label { font-size:12px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }
.card .value { font-size:25px; font-weight:650; margin:4px 0 2px; }
.card .note { font-size:12.5px; color:var(--ink2); }
section { background:var(--surface); border:1px solid rgba(11,11,11,.10); border-radius:12px; padding:20px 20px 10px;
          margin-bottom:20px; }
section h2 { margin:0 0 4px; font-size:19px; }
section > p { margin:4px 0 12px; color:var(--ink2); max-width:900px; }
h3 { font-size:15px; margin:14px 0 6px; }
.grid2 { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,480px),1fr)); gap:8px 24px; }
.grid2 > * { min-width:0; }
.tablewrap { overflow-x:auto; }
table { width:100%; border-collapse:collapse; font-size:13.5px; font-variant-numeric:tabular-nums; margin:6px 0 14px; }
th, td { text-align:right; padding:7px 9px; border-bottom:1px solid var(--grid); white-space:nowrap; }
th.l, td.l { text-align:left; white-space:normal; }
th { color:var(--muted); font-weight:600; font-size:11.5px; text-transform:uppercase; letter-spacing:.04em; }
.pos { color:#1a7f37; } .neg { color:#c4352b; }
.muted { color:var(--muted); font-size:13px; }
.small { font-size:13px; color:var(--ink2); }
code { background:#f0efec; border-radius:5px; padding:1px 5px; font-size:12.5px; }
.chip { display:inline-block; border-radius:999px; padding:1px 10px; font-size:12.5px; font-weight:600;
        margin-right:6px; }
.chip.good { background:#e3f3e7; color:#1a7f37; } .chip.warn { background:#fbf0d9; color:#8a5a00; }
.chip.bad { background:#fbe3e1; color:#c4352b; }
.lineage { display:flex; gap:10px; overflow-x:auto; padding-bottom:8px; margin-bottom:10px; }
.lcol { flex:1 0 170px; background:#f4f3ef; border-radius:10px; padding:10px; }
.lhead { font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); font-weight:700;
         margin-bottom:6px; }
.lnode { background:#fff; border:1px solid var(--grid); border-radius:7px; padding:5px 8px; margin-bottom:6px;
         font-size:12.5px; }
.lnode span { display:block; overflow-wrap:anywhere; }
.lnode em { display:block; color:var(--muted); font-style:normal; font-size:11px; }
details summary { cursor:pointer; color:#2a78d6; margin:4px 0 10px; }
ul.method li { margin-bottom:6px; color:var(--ink2); }
.btn { display:inline-block; background:#fff; color:#104281; border-radius:8px; padding:6px 12px; margin:12px 8px 0 0;
       font-weight:600; text-decoration:none; font-size:14px; }
footer { text-align:center; color:var(--muted); font-size:13px; padding:0 16px 40px; }
""".replace("%FONT%", FONT)

LAYOUT_JS = """
window.addEventListener("load", () => document.querySelectorAll(".plotly-graph-div").forEach(d => {
  if (window.innerWidth < 640 && d.layout) {
    const upd = {"title.font.size": 12};
    if (d.layout.showlegend !== false && d.data.length > 1) {
      Object.assign(upd, {"legend.y": -0.22, "legend.yanchor": "top", "legend.x": 0, "legend.xanchor": "left",
                          "margin.t": 50, "margin.b": Math.max((d.layout.margin || {}).b || 0, 130)});
    }
    // Phones: long category labels get less room, and heatmap cell labels are dropped (hover still works).
    if ((d.layout.margin || {}).l > 150) upd["margin.l"] = 150;
    Plotly.relayout(d, upd);
    if (d.data.some(t => t.type === "heatmap")) {
      Plotly.restyle(d, {texttemplate: ""});
      Plotly.relayout(d, {"margin.l": 95, "yaxis.tickfont.size": 8, "xaxis.title.text": ""});
    }
  }
  Plotly.Plots.resize(d);
}));
"""
