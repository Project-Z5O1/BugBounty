#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regenerate the bounty section of README.md from bounties.csv.

Usage:
    python3 scripts/update_bounty_readme.py

Data format (bounties.csv, UTF-8, header row required):
    date,vendor,report_id,amount_rmb
    2026-08-09,OpenHarmony,OHSA26-080951547,2000

The script:
  1. loads and validates bounties.csv
  2. renders assets/bounty_trend.svg  (cumulative bounty line chart)
     and assets/bounty_vendors.svg (bounty per SRC bar chart)
  3. rewrites everything between <!-- BOUNTY:START --> and
     <!-- BOUNTY:END --> in README.md with badges, the charts
     and markdown tables
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import math
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "bounties.csv"
README_PATH = ROOT / "README.md"
ASSETS_DIR = ROOT / "assets"

START_MARKER = "<!-- BOUNTY:START -->"
END_MARKER = "<!-- BOUNTY:END -->"

PALETTE = [
    "#3fb950", "#58a6ff", "#bc8cff", "#f78166", "#ffa657",
    "#39c5cf", "#ff7b72", "#e3b341", "#7ee787", "#79c0ff",
]
ACCENT = "#3fb950"

SVG_STYLE = """
    text { font-family: -apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif; }
    .title { fill: #1f2328; font-weight: 600; }
    .muted { fill: #57606a; }
    .grid { stroke: #d8dee4; stroke-width: 1; }
    .axis { stroke: #8c959f; stroke-width: 1.2; }
    .track { fill: #eaeef2; }
    .dot  { stroke: #ffffff; stroke-width: 2; }
    @media (prefers-color-scheme: dark) {
      .title { fill: #e6edf3; }
      .muted { fill: #8b949e; }
      .grid  { stroke: #262c36; }
      .axis  { stroke: #6e7681; }
      .track { fill: #21262d; }
      .dot   { stroke: #0d1117; }
    }
"""


def fail(msg: str) -> None:
    sys.exit(f"[update_bounty_readme] error: {msg}")


def load_rows() -> list[dict]:
    if not CSV_PATH.exists():
        fail(f"data file not found: {CSV_PATH}")
    rows = []
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        for i, rec in enumerate(csv.DictReader(f)):
            rec = {(k or "").strip(): (v or "").strip() for k, v in rec.items()}
            date_s = rec.get("date", "")
            vendor = rec.get("vendor", "")
            rid = rec.get("report_id", "")
            amount_s = rec.get("amount_rmb", "")
            if not any((date_s, vendor, rid, amount_s)):
                continue  # blank line
            if date_s.startswith("#"):
                continue  # comment line
            try:
                date = dt.date.fromisoformat(date_s.replace("/", "-"))
            except ValueError:
                fail(f"bounties.csv line {i + 2}: invalid date {date_s!r} (expected YYYY-MM-DD)")
            if not vendor:
                fail(f"bounties.csv line {i + 2}: missing vendor")
            try:
                amount = int(float(amount_s.replace(",", "")))
            except ValueError:
                fail(f"bounties.csv line {i + 2}: invalid amount {amount_s!r}")
            if amount <= 0:
                fail(f"bounties.csv line {i + 2}: amount must be positive: {amount}")
            rows.append({"date": date, "vendor": vendor, "report_id": rid or "-", "amount": amount})
    if not rows:
        fail("bounties.csv contains no data rows")
    rows.sort(key=lambda r: (r["date"], r["report_id"]))
    return rows


def nice_step(x: float) -> float:
    """Round a value up to a "nice" 1/1.5/2/2.5/3/4/5/7.5 x 10^n tick step."""
    if x <= 0:
        return 1.0
    exp = math.floor(math.log10(x))
    for mult in (1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10):
        cand = mult * 10**exp
        if cand >= x:
            return cand
    return 10.0 ** (exp + 1)


def fmt(n: int) -> str:
    return f"{n:,}"


def svg_header(width: int, height: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">\n<style>{SVG_STYLE}</style>\n'
    )


def build_trend_svg(rows: list[dict]) -> str:
    points, run = [], 0
    for r in rows:
        run += r["amount"]
        points.append((r["date"], run))
    total = run

    W, H = 880, 400
    L, R, T, B = 92, 48, 84, 76
    pw, ph = W - L - R, H - T - B

    step = int(nice_step(total / 4))
    top = step * math.ceil(total / step)
    n = len(points)

    def X(i: int) -> float:
        return L + pw / 2 if n == 1 else L + pw * i / (n - 1)

    def Y(v: int) -> float:
        return T + ph * (1 - v / top)

    out = [svg_header(W, H)]
    out.append(
        '  <defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#3fb950" stop-opacity="0.32"/>'
        '<stop offset="1" stop-color="#3fb950" stop-opacity="0.02"/></linearGradient></defs>\n'
    )
    out.append(
        f'  <text class="title" x="{L}" y="36" font-size="18">📈 Cumulative Bounty</text>\n'
        f'  <text class="muted" x="{W - R}" y="36" font-size="13" text-anchor="end">'
        f'{n} reports · {fmt(total)} RMB total</text>\n'
    )

    # horizontal grid lines + y-axis ticks
    y0 = Y(0)
    for tick in range(0, top + 1, step):
        y = Y(tick)
        out.append(
            f'  <line class="grid" x1="{L}" y1="{y:.1f}" x2="{W - R}" y2="{y:.1f}"'
            + (' opacity="0.5"' if tick else "") + "/>\n"
        )
        out.append(
            f'  <text class="muted" x="{L - 10}" y="{y + 4:.1f}" font-size="12" '
            f'text-anchor="end">{fmt(tick)}</text>\n'
        )
    out.append(f'  <line class="axis" x1="{L}" y1="{y0:.1f}" x2="{W - R}" y2="{y0:.1f}"/>\n')

    # area fill + line
    area = " ".join(f"L{x:.1f} {y:.1f}" for x, y in ((X(i), Y(v)) for i, (_, v) in enumerate(points)))
    out.append(
        f'  <path d="M{X(0):.1f} {y0:.1f} {area} L{X(n - 1):.1f} {y0:.1f} Z" '
        f'fill="url(#area)"/>\n'
    )
    poly = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, (_, v) in enumerate(points))
    out.append(
        f'  <polyline points="{poly}" fill="none" stroke="{ACCENT}" '
        f'stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>\n'
    )

    # dots + value labels + date labels (thinned out when crowded)
    label_every = max(1, math.ceil(n / 12))
    for i, (d, v) in enumerate(points):
        x, y = X(i), Y(v)
        out.append(f'  <circle class="dot" cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{ACCENT}"/>\n')
        anchor = "start" if i == 0 else ("end" if i == n - 1 else "middle")
        out.append(
            f'  <text class="muted" x="{x:.1f}" y="{y - 12:.1f}" font-size="12" '
            f'text-anchor="{anchor}" font-weight="600">{fmt(v)}</text>\n'
        )
        if i % label_every == 0 or i == n - 1:
            out.append(
                f'  <text class="muted" x="{x:.1f}" y="{y0 + 22:.1f}" font-size="11" '
                f'text-anchor="{anchor}">{d:%Y-%m-%d}</text>\n'
            )
    out.append("</svg>\n")
    return "".join(out)


def build_vendor_svg(rows: list[dict]) -> str:
    per: dict[str, list] = defaultdict(lambda: [0, 0])
    for r in rows:
        per[r["vendor"]][0] += r["amount"]
        per[r["vendor"]][1] += 1
    total = sum(v[0] for v in per.values())
    items = sorted(per.items(), key=lambda kv: (-kv[1][0], kv[0]))

    W, bar_h, gap, top_pad = 880, 30, 18, 66
    label_w = 150
    bar_x = label_w + 26
    value_w = 150
    plot_w = W - bar_x - value_w
    H = top_pad + len(items) * (bar_h + gap) - gap + 14
    maxv = max(v[0] for _, v in items)

    out = [svg_header(W, H)]
    out.append(
        f'  <text class="title" x="10" y="34" font-size="18">🏢 Bounty by SRC</text>\n'
        f'  <text class="muted" x="{W - 10}" y="34" font-size="13" text-anchor="end">in RMB</text>\n'
    )
    for i, (name, (amount, count)) in enumerate(items):
        y = top_pad + i * (bar_h + gap)
        color = PALETTE[i % len(PALETTE)]
        bar_w = max(6.0, amount / maxv * plot_w)
        share = amount / total * 100
        out.append(
            f'  <text class="muted" x="{label_w}" y="{y + bar_h / 2 + 5:.1f}" font-size="14" '
            f'text-anchor="end">{html.escape(name)} <tspan font-size="11">({count})</tspan></text>\n'
        )
        out.append(f'  <rect class="track" x="{bar_x}" y="{y}" width="{plot_w:.1f}" height="{bar_h}" rx="6"/>\n')
        out.append(
            f'  <rect x="{bar_x}" y="{y}" width="{bar_w:.1f}" height="{bar_h}" rx="6" '
            f'fill="{color}"/>\n'
        )
        out.append(
            f'  <text class="muted" x="{bar_x + bar_w + 10:.1f}" y="{y + bar_h / 2 + 5:.1f}" '
            f'font-size="13" font-weight="600">{fmt(amount)} · {share:.1f}%</text>\n'
        )
    out.append("</svg>\n")
    return "".join(out)


def badge(label: str, message: str, color: str) -> str:
    # shields.io static badges use '-' as the separator between label,
    # message and color; literal dashes must therefore be doubled ('--')
    # or the route fails to parse and renders "404 badge not found".
    def esc(s: str) -> str:
        return quote(s.replace("-", "--"), safe="")
    url = f"https://img.shields.io/badge/{esc(label)}-{esc(message)}-{color}"
    return f"![{html.escape(label)}]({url})"


def build_section(rows: list[dict]) -> str:
    total = sum(r["amount"] for r in rows)
    n = len(rows)
    vendors = sorted({r["vendor"] for r in rows})
    latest = max(r["date"] for r in rows)

    per: dict[str, list] = defaultdict(lambda: [0, 0])
    for r in rows:
        per[r["vendor"]][0] += r["amount"]
        per[r["vendor"]][1] += 1
    per_sorted = sorted(per.items(), key=lambda kv: (-kv[1][0], kv[0]))

    lines = []
    lines.append("## 🏆 Bounty Overview")
    lines.append("")
    lines.append(" ".join([
        badge("Total Bounty", f"{fmt(total)} RMB", "2ea44f"),
        badge("Reports", f"{n}", "0969da"),
        badge("SRCs", f"{len(vendors)}", "8250df"),
        badge("Updated", f"{latest:%Y-%m-%d}", "9a6700"),
    ]))
    lines.append("")
    lines.append('<p align="center"><img src="assets/bounty_trend.svg" alt="Cumulative bounty line chart"></p>')
    lines.append("")
    lines.append('<p align="center"><img src="assets/bounty_vendors.svg" alt="Bounty per SRC bar chart"></p>')
    lines.append("")
    lines.append("### 📊 Earnings by SRC")
    lines.append("")
    lines.append("| SRC | Reports | Bounty (RMB) | Share |")
    lines.append("|:--- | ---: | ---: | ---: |")
    for name, (amount, count) in per_sorted:
        share = amount / total * 100
        lines.append(f"| {html.escape(name)} | {count} | {fmt(amount)} | {share:.1f}% |")
    lines.append(f"| **Total** | **{n}** | **{fmt(total)}** | **100%** |")
    lines.append("")
    lines.append("### 📋 All Reports")
    lines.append("")
    lines.append("| # | Date | SRC | Report ID | Bounty (RMB) |")
    lines.append("| ---: | --- | --- | --- | ---: |")
    for i, r in enumerate(reversed(rows), 1):
        lines.append(
            f"| {i} | {r['date']:%Y-%m-%d} | {html.escape(r['vendor'])} "
            f"| `{html.escape(r['report_id'])}` | {fmt(r['amount'])} |"
        )
    lines.append("")
    lines.append(
        f"<sub>Auto-generated by <code>scripts/update_bounty_readme.py</code> from "
        f"<code>bounties.csv</code> · Generated on {dt.date.today():%Y-%m-%d}</sub>"
    )
    return "\n".join(lines)


def update_readme(section: str) -> None:
    content = README_PATH.read_text(encoding="utf-8") if README_PATH.exists() else ""
    if START_MARKER in content and END_MARKER in content:
        pre = content.split(START_MARKER)[0]
        post = content.split(END_MARKER)[1]
        new = f"{pre}{START_MARKER}\n\n{section}\n\n{END_MARKER}{post}"
    else:
        new = f"{content.rstrip()}\n\n{START_MARKER}\n\n{section}\n\n{END_MARKER}\n"
    README_PATH.write_text(new, encoding="utf-8")


def main() -> None:
    rows = load_rows()
    total = sum(r["amount"] for r in rows)
    ASSETS_DIR.mkdir(exist_ok=True)
    (ASSETS_DIR / "bounty_trend.svg").write_text(build_trend_svg(rows), encoding="utf-8")
    (ASSETS_DIR / "bounty_vendors.svg").write_text(build_vendor_svg(rows), encoding="utf-8")
    update_readme(build_section(rows))
    print(
        f"[update_bounty_readme] done: {len(rows)} reports, "
        f"{len({r['vendor'] for r in rows})} SRCs, {fmt(total)} RMB total; "
        f"updated README.md and assets/*.svg"
    )


if __name__ == "__main__":
    main()
