from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .models import AuditResult, ScoreRow, StockChart, StockMention
from .xlsx_writer import write_xlsx


def _pct(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value * 100:.1f}%"


def _num(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.4f}"


def _dates(mentions: list[StockMention]) -> list[str]:
    return sorted({mention.date for mention in mentions})


def _stocks(charts: list[StockChart]) -> list[StockChart]:
    return sorted(charts, key=lambda chart: (chart.display_name.casefold(), chart.security_key))


def _matrix_cell(items: list[StockMention]) -> str:
    if not items:
        return ""
    counts = Counter(item.stance for item in items)
    parts = []
    for stance, label in (("bull", "bull"), ("bear", "bear"), ("mention_only", "仅提及"), ("mixed", "mixed")):
        if counts.get(stance):
            parts.append(f"{label} x{counts[stance]}")
    return "; ".join(parts)


def _evidence_cell(items: list[StockMention]) -> str:
    return "\n".join(
        f"[{item.stance}] {item.viewpoint or item.evidence} | {item.evidence} | {item.tweet_url} | close={item.price_close or ''}"
        for item in items
    )


def build_excel_sheets(result: AuditResult) -> dict[str, list[list[Any]]]:
    dates = _dates(result.mentions)
    by_stock_date: dict[tuple[str, str], list[StockMention]] = defaultdict(list)
    for mention in result.mentions:
        by_stock_date[(mention.security_key, mention.date)].append(mention)

    stance_rows: list[list[Any]] = [["stock", "ticker", "market", *dates]]
    evidence_rows: list[list[Any]] = [["stock", "ticker", "market", *dates]]
    for chart in _stocks(result.charts):
        stance_rows.append(
            [
                chart.display_name,
                chart.ticker or "",
                chart.market or "",
                *[_matrix_cell(by_stock_date[(chart.security_key, date)]) for date in dates],
            ]
        )
        evidence_rows.append(
            [
                chart.display_name,
                chart.ticker or "",
                chart.market or "",
                *[_evidence_cell(by_stock_date[(chart.security_key, date)]) for date in dates],
            ]
        )

    raw_rows: list[list[Any]] = [[
        "tweet_id",
        "published_at",
        "stock",
        "ticker",
        "market",
        "stance",
        "confidence",
        "price_date",
        "price_close",
        "return_1d",
        "return_5d",
        "return_20d",
        "viewpoint",
        "evidence",
        "tweet_url",
    ]]
    for mention in result.mentions:
        raw_rows.append([
            mention.tweet_id,
            mention.published_at,
            mention.display_name or mention.stock_name,
            mention.ticker or mention.ticker_or_code or "",
            mention.market or mention.market_hint or "",
            mention.stance,
            mention.confidence,
            mention.price_date or "",
            mention.price_close if mention.price_close is not None else "",
            mention.forward_returns.get("1d"),
            mention.forward_returns.get("5d"),
            mention.forward_returns.get("20d"),
            mention.viewpoint,
            mention.evidence,
            mention.tweet_url,
        ])

    score_rows: list[list[Any]] = [[
        "stock",
        "ticker",
        "market",
        "signals",
        "mention_only",
        "hit_rate_1d",
        "hit_rate_5d",
        "hit_rate_20d",
        "avg_return_1d",
        "avg_return_5d",
        "avg_return_20d",
    ]]
    for score in result.scores:
        score_rows.append([
            score.display_name,
            score.ticker or "",
            score.market or "",
            score.signal_count,
            score.mention_only_count,
            _pct(score.hit_rate_1d),
            _pct(score.hit_rate_5d),
            _pct(score.hit_rate_20d),
            _pct(score.avg_return_1d),
            _pct(score.avg_return_5d),
            _pct(score.avg_return_20d),
        ])

    return {
        "stance_matrix": stance_rows,
        "evidence_matrix": evidence_rows,
        "raw_mentions": raw_rows,
        "score_summary": score_rows,
    }


def write_excel(path: Path, result: AuditResult) -> None:
    write_xlsx(path, build_excel_sheets(result))


def _chart_payload(chart: StockChart) -> dict[str, Any]:
    return {
        "securityKey": chart.security_key,
        "displayName": chart.display_name,
        "ticker": chart.ticker,
        "market": chart.market,
        "sourceLabel": chart.source_label,
        "message": chart.message,
        "candles": [
            {
                "date": candle.date,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
            }
            for candle in chart.candles
        ],
        "mentions": [
            {
                "date": mention.date,
                "tweetId": mention.tweet_id,
                "url": mention.tweet_url,
                "stance": mention.stance,
                "viewpoint": mention.viewpoint,
                "evidence": mention.evidence,
                "priceClose": mention.price_close,
                "returns": mention.forward_returns,
            }
            for mention in chart.mentions
        ],
    }


def write_html(path: Path, result: AuditResult) -> None:
    charts_payload = [_chart_payload(chart) for chart in _stocks(result.charts)]
    charts_json = json.dumps(charts_payload, ensure_ascii=False).replace("<", "\\u003c")
    counts = Counter(mention.stance for mention in result.mentions)
    chart_nav = "\n".join(
        f'<a href="#stock-{html.escape(chart.security_key)}">{html.escape(chart.display_name)} <span>{len(chart.mentions)}</span></a>'
        for chart in _stocks(result.charts)
    )
    score_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(score.display_name)}</td><td>{html.escape(score.ticker or '')}</td><td>{score.signal_count}</td>"
        f"<td>{_pct(score.hit_rate_5d)}</td><td>{_pct(score.avg_return_5d)}</td>"
        "</tr>"
        for score in result.scores
    )
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>X Account Stock Audit - {html.escape(result.username)}</title>
  <style>
    :root {{ color-scheme: light; --ink:#1f2933; --muted:#657282; --line:#d9e1e8; --paper:#ffffff; --soft:#f5f7f9; --bull:#227a52; --bear:#b33f3f; --mention:#6d7785; }}
    body {{ margin:0; font-family: Arial, "Microsoft YaHei", sans-serif; color:var(--ink); background:#eef2f5; }}
    header {{ padding:28px 32px; background:#10202f; color:white; }}
    h1 {{ margin:0 0 8px; font-size:28px; }}
    h2 {{ margin:0 0 14px; font-size:20px; }}
    main {{ padding:24px 32px 48px; }}
    .grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:12px; margin-top:18px; }}
    .metric, section {{ background:var(--paper); border:1px solid var(--line); border-radius:8px; }}
    .metric {{ padding:14px; }}
    .metric b {{ display:block; font-size:24px; margin-top:6px; }}
    section {{ padding:18px; margin-top:18px; }}
    nav {{ display:flex; flex-wrap:wrap; gap:8px; }}
    nav a {{ color:#173b59; text-decoration:none; border:1px solid var(--line); padding:7px 10px; border-radius:6px; background:var(--soft); }}
    nav span {{ color:var(--muted); }}
    .chart {{ overflow-x:auto; border:1px solid var(--line); border-radius:8px; background:white; }}
    svg {{ min-width:860px; width:100%; height:auto; display:block; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th, td {{ border-bottom:1px solid var(--line); padding:8px; text-align:left; vertical-align:top; }}
    .note {{ color:var(--muted); line-height:1.6; }}
    .tooltip {{ margin-top:10px; padding:10px; border:1px solid var(--line); background:var(--soft); border-radius:6px; min-height:44px; }}
  </style>
</head>
<body>
<header>
  <h1>@{html.escape(result.username)} 股票喊单审计</h1>
  <div>{result.start_date.isoformat()} 至 {result.end_date.isoformat()} · 日线价格近似，不代表发言时刻逐笔价格</div>
  <div class="grid">
    <div class="metric">抓取发言 <b>{len(result.posts)}</b></div>
    <div class="metric">股票提及 <b>{len(result.mentions)}</b></div>
    <div class="metric">股票数 <b>{len(result.charts)}</b></div>
    <div class="metric">bull/bear/仅提及 <b>{counts.get('bull', 0)}/{counts.get('bear', 0)}/{counts.get('mention_only', 0)}</b></div>
  </div>
</header>
<main>
  <section>
    <h2>股票列表</h2>
    <nav>{chart_nav}</nav>
  </section>
  <section>
    <h2>评分摘要</h2>
    <table><thead><tr><th>股票</th><th>Ticker</th><th>方向样本</th><th>5D 命中率</th><th>5D 平均方向收益</th></tr></thead><tbody>{score_rows}</tbody></table>
  </section>
  <div id="charts"></div>
</main>
<script id="chart-data" type="application/json">{charts_json}</script>
<script>
const charts = JSON.parse(document.getElementById('chart-data').textContent);
const root = document.getElementById('charts');
function yFor(price, min, max) {{ return 32 + ((max - price) / Math.max(max - min, 0.0001)) * 300; }}
function markerColor(stance) {{ return stance === 'bull' ? 'var(--bull)' : stance === 'bear' ? 'var(--bear)' : 'var(--mention)'; }}
function markerShape(m, x, yHigh, yLow, i) {{
  const c = markerColor(m.stance), dx = (i % 5 - 2) * 7;
  const x2 = x + dx;
  if (m.stance === 'bull') return `<path d="M ${{x2}} ${{yLow+11}} L ${{x2-6}} ${{yLow+19}} H ${{x2-2}} V ${{yLow+26}} H ${{x2+2}} V ${{yLow+19}} H ${{x2+6}} Z" fill="${{c}}"><title>${{m.date}} ${{m.stance}} ${{m.viewpoint}}</title></path>`;
  if (m.stance === 'bear') return `<path d="M ${{x2}} ${{yHigh-11}} L ${{x2-6}} ${{yHigh-19}} H ${{x2-2}} V ${{yHigh-26}} H ${{x2+2}} V ${{yHigh-19}} H ${{x2+6}} Z" fill="${{c}}"><title>${{m.date}} ${{m.stance}} ${{m.viewpoint}}</title></path>`;
  return `<path d="M ${{x2}} 338 V 320 L ${{x2+13}} 324 L ${{x2}} 329 Z" fill="${{c}}"><title>${{m.date}} ${{m.stance}} ${{m.viewpoint}}</title></path>`;
}}
function renderChart(chart) {{
  const candles = chart.candles || [];
  const lows = candles.map(c => c.low), highs = candles.map(c => c.high);
  const min = lows.length ? Math.min(...lows) * 0.98 : 0, max = highs.length ? Math.max(...highs) * 1.02 : 1;
  const width = 1120, left = 54, right = 18, step = (width-left-right) / Math.max(candles.length, 1);
  const byDate = new Map();
  for (const m of chart.mentions) {{ if (!byDate.has(m.date)) byDate.set(m.date, []); byDate.get(m.date).push(m); }}
  let nodes = '';
  candles.forEach((c, i) => {{
    const x = left + i * step + step/2;
    const openY = yFor(c.open, min, max), closeY = yFor(c.close, min, max), highY = yFor(c.high, min, max), lowY = yFor(c.low, min, max);
    const up = c.close >= c.open, bodyY = Math.min(openY, closeY), bodyH = Math.max(Math.abs(closeY-openY), 1.5), bodyW = Math.max(2, Math.min(9, step*0.58));
    nodes += `<line x1="${{x}}" y1="${{highY}}" x2="${{x}}" y2="${{lowY}}" stroke="${{up ? '#227a52' : '#b33f3f'}}" stroke-width="1.4"/>`;
    nodes += `<rect x="${{x-bodyW/2}}" y="${{bodyY}}" width="${{bodyW}}" height="${{bodyH}}" fill="${{up ? '#2b8a5f' : '#fff'}}" stroke="${{up ? '#227a52' : '#b33f3f'}}"><title>${{c.date}} O ${{c.open}} H ${{c.high}} L ${{c.low}} C ${{c.close}}</title></rect>`;
    (byDate.get(c.date) || []).forEach((m, j) => nodes += markerShape(m, x, highY, lowY, j));
  }});
  const mentions = chart.mentions.map(m => `<li><a href="${{m.url}}" target="_blank" rel="noreferrer">${{m.date}}</a> <b>${{m.stance}}</b> close=${{m.priceClose ?? ''}} · ${{m.viewpoint || m.evidence}}<br><span class="note">${{m.evidence}}</span></li>`).join('');
  return `<section id="stock-${{chart.securityKey}}"><h2>${{chart.displayName}} ${{chart.ticker ? '('+chart.ticker+')' : ''}}</h2><p class="note">${{chart.sourceLabel || ''}} ${{chart.message || ''}}</p><div class="chart"><svg viewBox="0 0 1120 380" role="img" aria-label="${{chart.displayName}} K line"><rect x="0" y="0" width="1120" height="380" fill="#fff"/><line x1="54" y1="332" x2="1102" y2="332" stroke="#d9e1e8"/>${{nodes}}<text x="54" y="366" font-size="12" fill="#657282">${{candles[0]?.date || ''}}</text><text x="1102" y="366" font-size="12" text-anchor="end" fill="#657282">${{candles[candles.length-1]?.date || ''}}</text></svg></div><ul>${{mentions}}</ul></section>`;
}}
root.innerHTML = charts.map(renderChart).join('');
</script>
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text, encoding="utf-8")
