#!/usr/bin/env python3
"""Generate a self-contained HTML demo dashboard from Supabase offer data."""

from __future__ import annotations

import html
import json
import math
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import mean

from dotenv import load_dotenv
from supabase import create_client


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "demo" / "dashboard.html"


@dataclass
class MetricCard:
    label: str
    value: str
    sublabel: str


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value[:10])


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def euro(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"EUR {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def compact_int(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def fetch_offers() -> list[dict]:
    load_dotenv(PROJECT_ROOT / ".env")
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    # The dataset is still small enough to fetch in one paged sweep.
    rows: list[dict] = []
    start = 0
    page_size = 1000
    while True:
        batch = (
            sb.table("offers")
            .select(
                "external_id,title,store,category,price,original_price,discount_percent,"
                "valid_from,valid_to,is_upcoming,scraped_at,is_active"
            )
            .order("scraped_at", desc=False)
            .range(start, start + page_size - 1)
            .execute()
            .data
            or []
        )
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows


def build_bar_chart_svg(
    items: list[tuple[str, int]],
    width: int = 840,
    height: int = 320,
    color: str = "#0f766e",
) -> str:
    if not items:
        return ""

    left_pad = 140
    right_pad = 24
    top_pad = 16
    bottom_pad = 18
    gap = 10
    bar_area = height - top_pad - bottom_pad
    bar_height = max(16, (bar_area - gap * (len(items) - 1)) // len(items))
    max_value = max(value for _, value in items) or 1

    parts = [
        f'<svg viewBox="0 0 {width} {height}" class="chart-svg" role="img" '
        f'aria-label="Horizontal bar chart">'
    ]
    for idx, (label, value) in enumerate(items):
        y = top_pad + idx * (bar_height + gap)
        usable_width = width - left_pad - right_pad
        bar_width = max(2, int((value / max_value) * usable_width))
        safe_label = html.escape(label[:28] + ("..." if len(label) > 28 else ""))
        parts.append(
            f'<text x="{left_pad - 10}" y="{y + bar_height / 2 + 4}" class="axis-label" '
            f'text-anchor="end">{safe_label}</text>'
        )
        parts.append(
            f'<rect x="{left_pad}" y="{y}" width="{usable_width}" height="{bar_height}" '
            f'rx="7" fill="#dcefeb"></rect>'
        )
        parts.append(
            f'<rect x="{left_pad}" y="{y}" width="{bar_width}" height="{bar_height}" '
            f'rx="7" fill="{color}"></rect>'
        )
        parts.append(
            f'<text x="{left_pad + bar_width + 10}" y="{y + bar_height / 2 + 4}" '
            f'class="value-label">{value}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def build_timeline_svg(labels: list[str], values: list[int], width: int = 980, height: int = 320) -> str:
    if not values:
        return ""

    top_pad = 24
    bottom_pad = 50
    left_pad = 42
    right_pad = 24
    max_value = max(values) or 1
    min_value = 0
    plot_w = width - left_pad - right_pad
    plot_h = height - top_pad - bottom_pad

    points: list[tuple[float, float]] = []
    for idx, value in enumerate(values):
        x = left_pad + (plot_w * idx / max(1, len(values) - 1))
        y = top_pad + plot_h - ((value - min_value) / (max_value - min_value or 1) * plot_h)
        points.append((x, y))

    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    area_points = f"{left_pad},{top_pad + plot_h} " + polyline + f" {left_pad + plot_w},{top_pad + plot_h}"

    parts = [
        f'<svg viewBox="0 0 {width} {height}" class="chart-svg" role="img" aria-label="Offers over time">'
    ]
    for tick in range(5):
        value = int(max_value * tick / 4)
        y = top_pad + plot_h - plot_h * tick / 4
        parts.append(f'<line x1="{left_pad}" y1="{y:.1f}" x2="{left_pad + plot_w}" y2="{y:.1f}" class="grid-line"></line>')
        parts.append(f'<text x="{left_pad - 8}" y="{y + 4:.1f}" class="axis-label" text-anchor="end">{value}</text>')

    parts.append(f'<polygon points="{area_points}" fill="rgba(15,118,110,0.12)"></polygon>')
    parts.append(f'<polyline points="{polyline}" fill="none" stroke="#0f766e" stroke-width="4" stroke-linecap="round"></polyline>')

    for idx, (x, y) in enumerate(points):
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#0f766e"></circle>')
        parts.append(
            f'<text x="{x:.1f}" y="{top_pad + plot_h + 24}" class="axis-label" text-anchor="middle">'
            f'{html.escape(labels[idx])}</text>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{y - 12:.1f}" class="value-label" text-anchor="middle">{values[idx]}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def build_table(rows: list[dict], columns: list[tuple[str, str]]) -> str:
    head = "".join(f"<th>{html.escape(label)}</th>" for _, label in columns)
    body_parts: list[str] = []
    for row in rows:
        cells = []
        for key, _ in columns:
            value = row.get(key, "")
            cells.append(f"<td>{html.escape(str(value))}</td>")
        body_parts.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_parts)}</tbody></table>"


def is_current_offer(row: dict, today: date) -> bool:
    valid_from = parse_date(row.get("valid_from"))
    valid_to = parse_date(row.get("valid_to"))
    if valid_from and valid_from > today:
        return False
    if valid_to and valid_to < today:
        return False
    return True


def build_dashboard(offers: list[dict]) -> str:
    now = datetime.now(UTC)
    today = now.date()
    scraped_dates = [parse_dt(row.get("scraped_at")) for row in offers]
    scraped_dates = [dt for dt in scraped_dates if dt]
    first_seen = min(scraped_dates) if scraped_dates else now
    last_seen = max(scraped_dates) if scraped_dates else now

    active_offers = [row for row in offers if row.get("is_active", True)]
    current_offers = [row for row in active_offers if is_current_offer(row, today)]
    upcoming_offers = [row for row in active_offers if row.get("is_upcoming")]
    discount_offers = [row for row in active_offers if row.get("discount_percent") is not None]
    discount_offers.sort(key=lambda row: (row.get("discount_percent") or 0), reverse=True)

    stores = Counter(row.get("store") or "Unknown" for row in active_offers)
    categories = Counter(row.get("category") or "Unknown" for row in active_offers)
    scraped_by_day: dict[date, int] = defaultdict(int)
    for row in active_offers:
        dt = parse_dt(row.get("scraped_at"))
        if dt:
            scraped_by_day[dt.date()] += 1

    day_labels: list[str] = []
    day_values: list[int] = []
    start_day = min(scraped_by_day) if scraped_by_day else today
    for offset in range((today - start_day).days + 1):
        cur = start_day + timedelta(days=offset)
        day_labels.append(cur.strftime("%d %b"))
        day_values.append(scraped_by_day.get(cur, 0))

    expiring_soon = []
    for row in current_offers:
        valid_to = parse_date(row.get("valid_to"))
        if valid_to and valid_to <= today + timedelta(days=2):
            expiring_soon.append(row)
    expiring_soon.sort(key=lambda row: (row.get("valid_to") or "", -(row.get("discount_percent") or 0)))

    next_week_start = today + timedelta(days=(7 - today.weekday()))
    next_week_end = next_week_start + timedelta(days=6)
    next_week_offers = []
    for row in active_offers:
        valid_from = parse_date(row.get("valid_from"))
        if valid_from and next_week_start <= valid_from <= next_week_end:
            next_week_offers.append(row)

    avg_discount = mean(row["discount_percent"] for row in discount_offers) if discount_offers else 0.0
    cards = [
        MetricCard("Total offers", compact_int(len(active_offers)), "All currently stored rows"),
        MetricCard("Current this week", compact_int(len(current_offers)), "Valid now in the market"),
        MetricCard("Upcoming", compact_int(len(upcoming_offers)), "Preview inventory for later validity"),
        MetricCard("Stores covered", compact_int(len(stores)), "Distinct retailers in the dataset"),
        MetricCard("Discounted offers", compact_int(len(discount_offers)), f"Average discount {avg_discount:.1f}%"),
        MetricCard("Trend window", f"{len(day_values)} days", f"{first_seen.date().isoformat()} to {last_seen.date().isoformat()}"),
    ]

    top_deals_rows = []
    for row in discount_offers[:10]:
        top_deals_rows.append(
            {
                "title": row.get("title") or "-",
                "store": row.get("store") or "-",
                "price": euro(row.get("price")),
                "discount": f"{row.get('discount_percent'):.1f}%" if row.get("discount_percent") is not None else "-",
                "valid_to": row.get("valid_to") or "-",
            }
        )

    expiry_rows = []
    for row in expiring_soon[:10]:
        expiry_rows.append(
            {
                "title": row.get("title") or "-",
                "store": row.get("store") or "-",
                "discount": f"{row.get('discount_percent'):.1f}%" if row.get("discount_percent") is not None else "-",
                "valid_to": row.get("valid_to") or "-",
            }
        )

    next_week_rows = []
    for row in sorted(next_week_offers, key=lambda item: (item.get("valid_from") or "", item.get("store") or ""))[:10]:
        next_week_rows.append(
            {
                "title": row.get("title") or "-",
                "store": row.get("store") or "-",
                "valid_from": row.get("valid_from") or "-",
                "price": euro(row.get("price")),
            }
        )

    latest_rows = []
    for row in sorted(
        active_offers,
        key=lambda item: item.get("scraped_at") or "",
        reverse=True,
    )[:12]:
        latest_rows.append(
            {
                "external_id": row.get("external_id") or "-",
                "store": row.get("store") or "-",
                "title": row.get("title") or "-",
                "valid_to": row.get("valid_to") or "-",
            }
        )

    cards_html = "".join(
        f"""
        <section class="metric-card">
          <div class="metric-label">{html.escape(card.label)}</div>
          <div class="metric-value">{html.escape(card.value)}</div>
          <div class="metric-note">{html.escape(card.sublabel)}</div>
        </section>
        """
        for card in cards
    )

    top_stores_chart = build_bar_chart_svg(stores.most_common(10), color="#0f766e")
    top_categories_chart = build_bar_chart_svg(categories.most_common(10), color="#c2410c")
    timeline_chart = build_timeline_svg(day_labels, day_values)

    next_week_note = (
        f"{len(next_week_offers)} offers already start next week."
        if next_week_offers
        else "No next-week start dates are currently published in the live source."
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AngebotsBot Demo Dashboard</title>
  <style>
    :root {{
      --bg: #f7f3ea;
      --panel: rgba(255,255,255,0.84);
      --ink: #10231c;
      --muted: #5c6f67;
      --line: rgba(16,35,28,0.10);
      --teal: #0f766e;
      --orange: #c2410c;
      --gold: #d6a229;
      --shadow: 0 18px 50px rgba(16,35,28,0.10);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(214,162,41,0.18), transparent 24%),
        radial-gradient(circle at 85% 10%, rgba(15,118,110,0.14), transparent 22%),
        linear-gradient(180deg, #fbf8f1 0%, var(--bg) 100%);
    }}
    .wrap {{
      max-width: 1240px;
      margin: 0 auto;
      padding: 36px 20px 56px;
    }}
    .hero {{
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 20px;
      align-items: stretch;
      margin-bottom: 24px;
    }}
    .hero-card, .panel {{
      background: var(--panel);
      border: 1px solid rgba(255,255,255,0.5);
      backdrop-filter: blur(10px);
      box-shadow: var(--shadow);
      border-radius: 24px;
    }}
    .hero-card {{
      padding: 28px 28px 26px;
      position: relative;
      overflow: hidden;
    }}
    .hero-card::after {{
      content: "";
      position: absolute;
      inset: auto -8% -45% auto;
      width: 260px;
      height: 260px;
      background: radial-gradient(circle, rgba(15,118,110,0.18), transparent 60%);
      pointer-events: none;
    }}
    .eyebrow {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.16em;
      color: var(--teal);
      margin-bottom: 12px;
      font-weight: 700;
      font-family: "Helvetica Neue", Arial, sans-serif;
    }}
    h1 {{
      font-size: clamp(36px, 6vw, 64px);
      line-height: 0.95;
      margin: 0 0 14px;
      letter-spacing: -0.04em;
    }}
    .hero-copy {{
      font-size: 17px;
      line-height: 1.6;
      color: var(--muted);
      max-width: 58ch;
      margin: 0 0 20px;
    }}
    .hero-chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .chip {{
      border-radius: 999px;
      padding: 10px 14px;
      background: rgba(16,35,28,0.06);
      color: var(--ink);
      font-size: 13px;
      font-family: "Helvetica Neue", Arial, sans-serif;
    }}
    .snapshot {{
      padding: 24px;
      display: grid;
      gap: 16px;
      align-content: start;
    }}
    .snapshot-stat {{
      padding-bottom: 14px;
      border-bottom: 1px solid var(--line);
    }}
    .snapshot-stat:last-child {{
      border-bottom: 0;
      padding-bottom: 0;
    }}
    .snapshot-label {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--muted);
      font-family: "Helvetica Neue", Arial, sans-serif;
    }}
    .snapshot-value {{
      font-size: 34px;
      line-height: 1;
      margin: 8px 0 6px;
    }}
    .snapshot-note {{
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}
    .metric-card {{
      background: var(--panel);
      border: 1px solid rgba(255,255,255,0.5);
      box-shadow: var(--shadow);
      border-radius: 22px;
      padding: 20px;
    }}
    .metric-label {{
      font-family: "Helvetica Neue", Arial, sans-serif;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      margin-bottom: 12px;
    }}
    .metric-value {{
      font-size: clamp(28px, 5vw, 42px);
      line-height: 1;
      margin-bottom: 10px;
    }}
    .metric-note {{
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
    }}
    .layout {{
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 18px;
      margin-bottom: 18px;
    }}
    .stack {{
      display: grid;
      gap: 18px;
    }}
    .panel {{
      padding: 24px;
    }}
    h2 {{
      margin: 0 0 8px;
      font-size: 26px;
      letter-spacing: -0.03em;
    }}
    .panel-copy {{
      color: var(--muted);
      font-size: 14px;
      line-height: 1.6;
      margin: 0 0 16px;
    }}
    .chart-svg {{
      width: 100%;
      height: auto;
      display: block;
    }}
    .grid-line {{
      stroke: rgba(16,35,28,0.12);
      stroke-width: 1;
    }}
    .axis-label {{
      fill: #667a72;
      font-size: 11px;
      font-family: "Helvetica Neue", Arial, sans-serif;
    }}
    .value-label {{
      fill: #10231c;
      font-size: 12px;
      font-family: "Helvetica Neue", Arial, sans-serif;
      font-weight: 700;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      text-align: left;
      padding: 12px 10px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }}
    th {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--muted);
      font-family: "Helvetica Neue", Arial, sans-serif;
    }}
    tr:last-child td {{
      border-bottom: 0;
    }}
    .footnote {{
      margin-top: 22px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
      font-family: "Helvetica Neue", Arial, sans-serif;
    }}
    @media (max-width: 960px) {{
      .hero, .layout, .metric-grid {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <article class="hero-card">
        <div class="eyebrow">AngebotsBot Demo Dashboard</div>
        <h1>Live retail promo intelligence for a convincing product demo.</h1>
        <p class="hero-copy">
          This dashboard turns the current Supabase scrape into a market snapshot:
          volume, store coverage, discount intensity, expiring offers, and the earliest
          signal for next-week inventory.
        </p>
        <div class="hero-chips">
          <span class="chip">Last refresh: {html.escape(now.strftime("%Y-%m-%d %H:%M UTC"))}</span>
          <span class="chip">Data window starts: {html.escape(first_seen.date().isoformat())}</span>
          <span class="chip">Next-week preview: {html.escape(next_week_note)}</span>
        </div>
      </article>
      <aside class="hero-card snapshot">
        <div class="snapshot-stat">
          <div class="snapshot-label">Current market stance</div>
          <div class="snapshot-value">{compact_int(len(current_offers))}</div>
          <div class="snapshot-note">Offers valid right now, useful for showing immediate search and alert value.</div>
        </div>
        <div class="snapshot-stat">
          <div class="snapshot-label">High-discount pool</div>
          <div class="snapshot-value">{compact_int(sum(1 for row in discount_offers if (row.get("discount_percent") or 0) >= 25))}</div>
          <div class="snapshot-note">Offers at 25%+ discount, the easiest story for a demo narrative.</div>
        </div>
        <div class="snapshot-stat">
          <div class="snapshot-label">Next-week preview</div>
          <div class="snapshot-value">{compact_int(len(next_week_offers))}</div>
          <div class="snapshot-note">{html.escape(next_week_note)}</div>
        </div>
      </aside>
    </section>

    <section class="metric-grid">
      {cards_html}
    </section>

    <section class="layout">
      <article class="panel">
        <h2>Ingestion Trend</h2>
        <p class="panel-copy">
          This is the cleanest trend we can show today: how many live offers were added to the
          dataset each day as the crawl expanded.
        </p>
        {timeline_chart}
      </article>
      <div class="stack">
        <article class="panel">
          <h2>Top Stores</h2>
          <p class="panel-copy">Retailer mix across the current active dataset.</p>
          {top_stores_chart}
        </article>
        <article class="panel">
          <h2>Top Categories</h2>
          <p class="panel-copy">Keyword/category density from kaufda inventory.</p>
          {top_categories_chart}
        </article>
      </div>
    </section>

    <section class="layout">
      <article class="panel">
        <h2>Best Discounts Right Now</h2>
        <p class="panel-copy">A fast demo section for “what are the strongest deals today?”</p>
        {build_table(top_deals_rows, [("title", "Offer"), ("store", "Store"), ("price", "Price"), ("discount", "Discount"), ("valid_to", "Valid To")])}
      </article>
      <div class="stack">
        <article class="panel">
          <h2>Expiring Soon</h2>
          <p class="panel-copy">Useful for urgency-based alerts and recap messaging.</p>
          {build_table(expiry_rows, [("title", "Offer"), ("store", "Store"), ("discount", "Discount"), ("valid_to", "Valid To")])}
        </article>
        <article class="panel">
          <h2>Next Week Preview</h2>
          <p class="panel-copy">Preview rows only appear when the source publishes future validity windows.</p>
          {build_table(next_week_rows, [("title", "Offer"), ("store", "Store"), ("valid_from", "Valid From"), ("price", "Price")]) if next_week_rows else '<div class="footnote">No next-week start dates are currently available from the live source. The schema is ready for them as soon as kaufda publishes preview inventory.</div>'}
        </article>
      </div>
    </section>

    <section class="layout">
      <article class="panel">
        <h2>Live Data Proof</h2>
        <p class="panel-copy">
          This section is intentionally raw. These rows come directly from the live Supabase
          <code>offers</code> table at dashboard generation time, with no mock data layer.
        </p>
        {build_table(latest_rows, [("external_id", "External ID"), ("store", "Store"), ("title", "Title"), ("valid_to", "Valid To")])}
      </article>
      <article class="panel">
        <h2>Source Reality</h2>
        <p class="panel-copy">
          The dashboard is generated from production scrape data already stored in Supabase.
          It is not based on hardcoded examples.
        </p>
        <div class="footnote">
          <strong>Rows in dataset:</strong> {compact_int(len(active_offers))}<br>
          <strong>First scraped row in this dataset:</strong> {html.escape(first_seen.isoformat())}<br>
          <strong>Latest scraped row in this dataset:</strong> {html.escape(last_seen.isoformat())}<br>
          <strong>Current offers valid now:</strong> {compact_int(len(current_offers))}<br>
          <strong>Upcoming offers:</strong> {compact_int(len(upcoming_offers))}<br>
          <strong>Next-week starts currently visible:</strong> {compact_int(len(next_week_offers))}
        </div>
      </article>
    </section>

    <div class="footnote">
      Built from the live Supabase <code>offers</code> table. Historical backfill before the first scrape date is not available from the current source path, so trend lines begin when collection started.
    </div>
  </div>
</body>
</html>
"""


def main() -> int:
    offers = fetch_offers()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(build_dashboard(offers), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
