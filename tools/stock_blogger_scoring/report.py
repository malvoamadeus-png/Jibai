from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .io import to_jsonable
from .models import AuthorScore, ScoringRunResult, SignalEvent, StockAuthorScore
from .xlsx_writer import write_xlsx


def _fmt(value: float | None, digits: int = 2) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def _pct(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value * 100:.1f}%"


def _score(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.1f}"


def _horizon_labels(result: ScoringRunResult) -> list[str]:
    return [f"{horizon}d" for horizon in result.config.horizons]


def _dist(values: dict[str, int]) -> str:
    return ", ".join(f"{key}:{value}" for key, value in sorted(values.items()) if value)


def _event_horizon_cells(event: SignalEvent, labels: list[str]) -> list[Any]:
    cells: list[Any] = []
    for label in labels:
        horizon_score = event.horizon_scores.get(label)
        if horizon_score is None:
            cells.extend(["", "", "", ""])
            continue
        cells.extend(
            [
                horizon_score.status,
                horizon_score.target_date or "",
                horizon_score.directional_excess,
                horizon_score.score,
            ]
        )
    return cells


def build_excel_sheets(result: ScoringRunResult) -> dict[str, list[list[Any]]]:
    labels = _horizon_labels(result)
    author_rows: list[list[Any]] = [[
        "author",
        "author_name",
        "overall_score",
        *[f"score_{label}" for label in labels],
        "scored_day_count",
        "event_count",
        "scored_event_count",
        *[f"scored_days_{label}" for label in labels],
        *[f"matured_{label}" for label in labels],
        *[f"pending_{label}" for label in labels],
        "pending_count",
        "positive_count",
        "negative_count",
        "direction_distribution",
        "conviction_distribution",
        "best_horizon",
        "worst_horizon",
    ]]
    for row in result.author_scores:
        pending_count = sum(row.pending_count_by_horizon.values())
        author_rows.append([
            row.author,
            row.author_name,
            row.overall_score,
            *[row.score_by_horizon.get(label) for label in labels],
            row.scored_day_count,
            row.event_count,
            row.scored_event_count,
            *[row.scored_day_count_by_horizon.get(label) for label in labels],
            *[row.matured_count_by_horizon.get(label) for label in labels],
            *[row.pending_count_by_horizon.get(label) for label in labels],
            pending_count,
            row.positive_count,
            row.negative_count,
            f"positive:{row.positive_count}, negative:{row.negative_count}",
            _dist(row.conviction_counts),
            row.best_horizon or "",
            row.worst_horizon or "",
        ])

    event_rows: list[list[Any]] = [[
        "event_id",
        "author",
        "published_at",
        "event_trading_day",
        "stock",
        "ticker",
        "market",
        "direction",
        "signal_type",
        "judgment_type",
        "conviction",
        "status",
        "status_reason",
        "anchor_trading_day",
        "anchor_price",
        "anchor_price_kind",
        "benchmark_symbol",
        "benchmark_anchor_price",
        *[item for label in labels for item in (f"{label}_status", f"{label}_target_date", f"{label}_directional_excess", f"{label}_score")],
        "logic",
        "evidence",
        "source_urls",
    ]]
    for event in result.events:
        event_rows.append([
            event.event_id,
            event.author,
            event.published_at,
            event.event_trading_day,
            event.display_name,
            event.ticker or "",
            event.market or "",
            event.direction,
            event.signal_type,
            event.judgment_type,
            event.conviction,
            event.status,
            event.status_reason or "",
            event.anchor_trading_day or "",
            event.anchor_price,
            event.anchor_price_kind or "",
            event.benchmark_symbol or "",
            event.benchmark_anchor_price,
            *_event_horizon_cells(event, labels),
            event.logic,
            "\n".join(event.evidence),
            "\n".join(event.source_urls),
        ])

    returns_rows: list[list[Any]] = [[
        "event_id",
        "author",
        "stock",
        "direction",
        "horizon",
        "status",
        "anchor_date",
        "anchor_price",
        "target_date",
        "target_price",
        "benchmark_symbol",
        "benchmark_anchor_price",
        "benchmark_target_price",
        "stock_return",
        "benchmark_return",
        "excess_return",
        "directional_excess",
        "score",
    ]]
    for event in result.events:
        for label in labels:
            horizon_score = event.horizon_scores.get(label)
            if horizon_score is None:
                continue
            returns_rows.append([
                event.event_id,
                event.author,
                event.display_name,
                event.direction,
                label,
                horizon_score.status,
                event.anchor_trading_day or "",
                event.anchor_price,
                horizon_score.target_date or "",
                horizon_score.target_price,
                event.benchmark_symbol or "",
                event.benchmark_anchor_price,
                horizon_score.benchmark_target_price,
                horizon_score.stock_return,
                horizon_score.benchmark_return,
                horizon_score.excess_return,
                horizon_score.directional_excess,
                horizon_score.score,
            ])

    stock_author_rows: list[list[Any]] = [["author", "security_key", "stock", "event_count", *[f"score_{label}" for label in labels], *[f"avg_directional_excess_{label}" for label in labels]]]
    for row in result.stock_author_scores:
        stock_author_rows.append([
            row.author,
            row.security_key,
            row.display_name,
            row.event_count,
            *[row.score_by_horizon.get(label) for label in labels],
            *[row.avg_directional_excess_by_horizon.get(label) for label in labels],
        ])

    return {
        "author_scores": author_rows,
        "signal_events": event_rows,
        "forward_returns": returns_rows,
        "stock_author_scores": stock_author_rows,
    }


def write_excel(path: Path, result: ScoringRunResult) -> None:
    write_xlsx(path, build_excel_sheets(result))


def _author_row(row: AuthorScore, labels: list[str]) -> str:
    score_cells = "".join(f"<td>{html.escape(_score(row.score_by_horizon.get(label)))}</td>" for label in labels)
    day_cells = "".join(f"<td>{row.scored_day_count_by_horizon.get(label, 0)}</td>" for label in labels)
    pending_count = sum(row.pending_count_by_horizon.values())
    return (
        "<tr>"
        f"<td>{html.escape(row.author)}</td>"
        f"<td>{html.escape(_score(row.overall_score))}</td>"
        f"{score_cells}"
        f"<td>{row.scored_day_count}</td>"
        f"<td>{row.event_count}</td>"
        f"<td>{row.scored_event_count}</td>"
        f"{day_cells}"
        f"<td>{pending_count}</td>"
        f"<td>+{row.positive_count} / -{row.negative_count}</td>"
        f"<td>{html.escape(_dist(row.conviction_counts))}</td>"
        f"<td>{html.escape(row.best_horizon or '')}</td>"
        "</tr>"
    )


def _event_row(event: SignalEvent, labels: list[str]) -> str:
    horizon_cells: list[str] = []
    for label in labels:
        horizon_score = event.horizon_scores.get(label)
        if horizon_score is None:
            horizon_cells.append("<td></td>")
            continue
        title = (
            f"stock={_pct(horizon_score.stock_return)} benchmark={_pct(horizon_score.benchmark_return)} "
            f"excess={_pct(horizon_score.excess_return)}"
        )
        horizon_cells.append(
            f'<td title="{html.escape(title, quote=True)}">{html.escape(horizon_score.status)} / {html.escape(_score(horizon_score.score))}</td>'
        )
    urls = " ".join(f'<a href="{html.escape(url, quote=True)}">link</a>' for url in event.source_urls[:3])
    return (
        "<tr>"
        f"<td>{html.escape(event.author)}</td>"
        f"<td>{html.escape(event.published_at)}</td>"
        f"<td>{html.escape(event.display_name)}</td>"
        f"<td>{html.escape(event.direction)}</td>"
        f"<td>{html.escape(event.conviction)}</td>"
        f"<td>{html.escape(event.status)}</td>"
        f"<td>{html.escape(event.anchor_trading_day or '')}<br>{html.escape(event.anchor_price_kind or '')}</td>"
        + "".join(horizon_cells)
        + f"<td>{html.escape(event.logic)}</td>"
        + f"<td>{urls}</td>"
        + "</tr>"
    )


def write_html(path: Path, result: ScoringRunResult) -> None:
    labels = _horizon_labels(result)
    counts = Counter(event.status for event in result.events)
    score_headers = "".join(f"<th>score {html.escape(label)}</th>" for label in labels)
    day_headers = "".join(f"<th>days {html.escape(label)}</th>" for label in labels)
    event_headers = "".join(f"<th>{html.escape(label)}</th>" for label in labels)
    authors_html = "\n".join(_author_row(row, labels) for row in result.author_scores)
    events_html = "\n".join(_event_row(event, labels) for event in result.events)
    manifest_json = json.dumps(to_jsonable(result.manifest), ensure_ascii=False, indent=2).replace("<", "\\u003c")
    market_manifest = result.manifest.get("market", {}) if isinstance(result.manifest.get("market"), dict) else {}
    global_benchmark = str(market_manifest.get("benchmark_symbol") or "")
    a_share_benchmark = str(market_manifest.get("a_share_benchmark_symbol") or "")
    benchmark_label = " / ".join(item for item in (global_benchmark, f"A股 {a_share_benchmark}" if a_share_benchmark else "") if item)

    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>股票博主观点验证评分</title>
  <style>
    :root {{ color-scheme: light; --ink:#202833; --muted:#637083; --line:#d8e0e7; --paper:#fff; --soft:#f5f7f9; --good:#216e4e; --bad:#b42318; }}
    body {{ margin:0; font-family: Arial, "Microsoft YaHei", sans-serif; color:var(--ink); background:#edf1f4; }}
    header {{ padding:28px 34px; background:#182635; color:#fff; }}
    h1 {{ margin:0 0 8px; font-size:28px; }}
    main {{ padding:24px 34px 48px; }}
    section {{ background:var(--paper); border:1px solid var(--line); border-radius:8px; padding:18px; margin-top:18px; }}
    .grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap:12px; margin-top:18px; }}
    .metric {{ background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.18); border-radius:8px; padding:12px; }}
    .metric b {{ display:block; margin-top:5px; font-size:24px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th, td {{ border-bottom:1px solid var(--line); padding:8px; text-align:left; vertical-align:top; }}
    th {{ position:sticky; top:0; background:var(--soft); z-index:1; }}
    .table-wrap {{ overflow:auto; max-height:72vh; border:1px solid var(--line); border-radius:8px; }}
    .note {{ color:var(--muted); line-height:1.6; }}
    pre {{ white-space:pre-wrap; background:var(--soft); border:1px solid var(--line); border-radius:8px; padding:12px; }}
    a {{ color:#174f7c; }}
  </style>
</head>
<body>
<header>
  <h1>股票博主观点验证评分</h1>
  <div>{result.start_date.isoformat()} 至 {result.end_date.isoformat()} · 基准 {html.escape(benchmark_label)} · 日线近似</div>
  <div class="grid">
    <div class="metric">账号 <b>{len(result.config.accounts)}</b></div>
    <div class="metric">抓取发言 <b>{len(result.posts)}</b></div>
    <div class="metric">股票观点 <b>{len(result.mentions)}</b></div>
    <div class="metric">事件 <b>{len(result.events)}</b></div>
    <div class="metric">可评分/未评分 <b>{counts.get("scoreable", 0)}/{counts.get("unscored", 0)}</b></div>
  </div>
</header>
<main>
  <section>
    <h2>作者评分</h2>
    <p class="note">综合分按作者观点日归一化后计算；评分天数、事件数和待成熟数量只作为样本提示，不参与排序分。</p>
    <div class="table-wrap"><table>
      <thead><tr><th>作者</th><th>综合分</th>{score_headers}<th>评分天数</th><th>事件</th><th>已评分事件</th>{day_headers}<th>待成熟</th><th>方向</th><th>强度</th><th>最佳周期</th></tr></thead>
      <tbody>{authors_html}</tbody>
    </table></div>
  </section>
  <section>
    <h2>观点事件明细</h2>
    <p class="note">每个周期单元格为 status / score；悬停可看个股收益、基准收益和超额收益。</p>
    <div class="table-wrap"><table>
      <thead><tr><th>作者</th><th>发布时间</th><th>股票</th><th>方向</th><th>强度</th><th>状态</th><th>锚点</th>{event_headers}<th>逻辑</th><th>链接</th></tr></thead>
      <tbody>{events_html}</tbody>
    </table></div>
  </section>
  <section>
    <h2>运行信息</h2>
    <pre>{html.escape(manifest_json)}</pre>
  </section>
</main>
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text, encoding="utf-8")
