from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import subprocess
import sys
import time
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
SCRIPT_DIR = Path(__file__).resolve().parent
for path in (BACKEND_DIR, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from packages.common.market_data import fetch_eastmoney_daily, fetch_yahoo_daily  # noqa: E402
from packages.public_app import market_top_risk as risk  # noqa: E402

import market_top_risk_availability as availability  # noqa: E402
import market_top_risk_event_review as event_review  # noqa: E402


OUTPUT_DIR = risk.CACHE_DIR.parent / "report"
REPORT_HTML = "market-top-risk-report.html"
REPORT_JSON = "market-top-risk-report.json"
SERVER_HOST = "47.76.243.147"
SERVER_USER = "root"
SVG_WIDTH = 980
SVG_HEIGHT = 560

MARKET_PROXIES = {
    "SOXX": {"label": "SOXX 美国半导体", "color": "#2563eb"},
    "588200.SH": {"label": "588200.SH 科创代理", "color": "#16a34a"},
}
_EASTMONEY_DAILY_CACHE: dict[tuple[str, str], dict[str, object]] = {}
_YAHOO_DAILY_CACHE: dict[str, dict[str, object]] = {}


@dataclass(frozen=True)
class IndicatorSpec:
    key: str
    title: str
    explanation: str
    conclusion: str
    value_key: str
    threshold: float
    source_keys: tuple[str, ...]
    local_name: str
    higher_is_risk: bool = True


INDICATORS = [
    IndicatorSpec(
        key="breadth_weakness_score",
        title="市场宽度恶化",
        explanation="RSP/SPY 与 QQEW/QQQ 的相对表现弱化组合，越高表示上涨越依赖少数权重股。",
        conclusion="近 9 个月里，它对 2025-10、2026-05/06 和 2026-06/07 的风险段有较好提前提示。",
        value_key="breadth_weakness_score",
        threshold=0.70,
        source_keys=("RSP", "SPY", "QQEW", "QQQ"),
        local_name="Financial conditions / credit composite",
    ),
    IndicatorSpec(
        key="rsp_spy_weakness_score",
        title="RSP/SPY 13周相对分位",
        explanation="等权标普相对市值加权标普走弱，越高表示市场参与度下降。",
        conclusion="对中国资产 2026-05/06 下跌和新兴市场 2026-06/07 下跌有提前触发。",
        value_key="rsp_spy_weakness_score",
        threshold=0.80,
        source_keys=("RSP", "SPY"),
        local_name="RSP/SPY 13w relative percentile",
    ),
    IndicatorSpec(
        key="qqew_qqq_weakness_score",
        title="QQEW/QQQ 13周相对分位",
        explanation="等权纳指相对 QQQ 走弱，越高表示科技内部参与度变差。",
        conclusion="这是近期最稳定的提前预警之一，3 月全球下跌和 5/6 月中国资产下跌前都有提示。",
        value_key="qqew_qqq_weakness_score",
        threshold=0.80,
        source_keys=("QQEW", "QQQ"),
        local_name="QQEW/QQQ 13w relative percentile",
    ),
    IndicatorSpec(
        key="breakage_score",
        title="金融条件/信用确认",
        explanation="NFCI 转紧、ANFCI 压力和 BAA10Y 信用利差的组合，越高表示风险扩散到金融条件和信用市场。",
        conclusion="近期不是领先信号，更多是后验确认；这次没有像宽度和轮动指标那样提前亮。",
        value_key="breakage_score",
        threshold=0.70,
        source_keys=("NFCI", "ANFCI", "BAA10Y"),
        local_name="Financial conditions / credit composite",
    ),
    IndicatorSpec(
        key="nfci_13w_chg_pctl",
        title="NFCI 13周转紧分位",
        explanation="Chicago Fed NFCI 的 13 周变化分位，越高表示金融条件快速转紧。",
        conclusion="近期多为观察级别，不是最早的预警来源。",
        value_key="nfci_13w_chg_pctl",
        threshold=0.80,
        source_keys=("NFCI",),
        local_name="NFCI 13w tightening percentile",
    ),
    IndicatorSpec(
        key="anfci_pctl",
        title="ANFCI 压力分位",
        explanation="调整后金融条件指数的绝对压力分位，越高表示金融系统压力更高。",
        conclusion="近期没有明显提前触发，适合作为确认而非预警。",
        value_key="anfci_pctl",
        threshold=0.80,
        source_keys=("ANFCI",),
        local_name="ANFCI pressure percentile",
    ),
    IndicatorSpec(
        key="credit_baa10y_pctl",
        title="BAA10Y 信用利差分位",
        explanation="Baa 公司债相对 10 年期美债利差分位，越高表示信用风险补偿上升。",
        conclusion="近期处在低位，说明这几段下跌不是由传统信用利差提前驱动。",
        value_key="credit_baa10y_pctl",
        threshold=0.80,
        source_keys=("BAA10Y",),
        local_name="BAA10Y credit spread percentile",
    ),
    IndicatorSpec(
        key="hyg_shy_weakness_score",
        title="HYG/SHY 13周相对分位",
        explanation="高收益债相对短债走弱，越高表示信用风险偏好下降。",
        conclusion="近期多是观察级别，有辅助意义，但不如市场宽度和防御轮动明确。",
        value_key="hyg_shy_weakness_score",
        threshold=0.80,
        source_keys=("HYG", "SHY"),
        local_name="HYG/SHY 13w relative percentile",
    ),
    IndicatorSpec(
        key="vix_vix3m_20d_pctl",
        title="VIX/VIX3M 期限结构压力",
        explanation="短期波动率相对三个月波动率的 20 日均值分位，越高表示短期压力被期权市场定价。",
        conclusion="对 2026-05/06 中国资产下跌有较好确认，但通常不是最早的顶部预警。",
        value_key="vix_vix3m_20d_pctl",
        threshold=0.80,
        source_keys=("VIXCLS", "VXVCLS"),
        local_name="VIX/VIX3M term-structure percentile",
    ),
    IndicatorSpec(
        key="xly_xlp_weakness_score",
        title="XLY/XLP 13周相对分位",
        explanation="可选消费相对必需消费走弱，越高表示资金从进攻转向防御。",
        conclusion="对 2026-03 全球下跌和 2026-05/06 中国资产下跌都有提前提示，是新增指标里较有价值的一项。",
        value_key="xly_xlp_weakness_score",
        threshold=0.80,
        source_keys=("XLY", "XLP"),
        local_name="XLY/XLP 13w relative percentile",
    ),
    IndicatorSpec(
        key="iwm_spy_weakness_score",
        title="IWM/SPY 13周相对分位",
        explanation="小盘股相对大盘股走弱，越高表示风险承受能力下降。",
        conclusion="近期没有宽度核心指标那么突出，应放在市场宽度组内而不是独立计票。",
        value_key="iwm_spy_weakness_score",
        threshold=0.80,
        source_keys=("IWM", "SPY"),
        local_name="IWM/SPY 13w relative percentile",
    ),
    IndicatorSpec(
        key="dfii10_13w_chg_pctl",
        title="DFII10 实际利率13周变化分位",
        explanation="10 年期实际利率快速上升分位，越高表示估值折现压力变大。",
        conclusion="当前是强触发，近期更像宏观压力背景和放大器，而不是单独择时信号。",
        value_key="dfii10_13w_chg_pctl",
        threshold=0.80,
        source_keys=("DFII10",),
        local_name="DFII10 13w change percentile",
    ),
    IndicatorSpec(
        key="dtwexbgs_13w_return_pctl",
        title="广义美元13周上涨分位",
        explanation="广义美元指数 13 周涨幅分位，越高表示全球美元流动性压力上升。",
        conclusion="当前接近观察区，适合作为跨资产确认，不应单独作为顶部信号。",
        value_key="dtwexbgs_13w_return_pctl",
        threshold=0.80,
        source_keys=("DTWEXBGS",),
        local_name="DTWEXBGS 13w return percentile",
    ),
]

EXPERIMENTAL_INDICATORS = [
    IndicatorSpec(
        key="china_star100_star50_weakness_score",
        title="实验：科创100/科创50 13周弱化",
        explanation="用科创100ETF 相对科创50ETF 的 13 周表现近似观察科创内部扩散度，越高表示更宽的科创100跑输科创50。",
        conclusion="这是中国侧内部宽度的简化实验版，不等同于等权/市值加权，但比科创相对沪深300更接近结构问题。",
        value_key="china_star100_star50_weakness_score",
        threshold=0.80,
        source_keys=("588120.SS", "588000.SS"),
        local_name="STAR 100 / STAR 50 13w relative weakness",
    ),
    IndicatorSpec(
        key="china_chinext_100_50_weakness_score",
        title="实验：创业板指/创业板50 13周弱化",
        explanation="用创业板ETF 相对创业板50ETF 的 13 周表现近似观察创业板内部扩散度，越高表示更宽的创业板指跑输更窄的创业板50。",
        conclusion="这是创业板内部宽度的简化实验版，适合先看图验证，不建议直接进入核心评分。",
        value_key="china_chinext_100_50_weakness_score",
        threshold=0.80,
        source_keys=("159915.SZ", "159949.SZ"),
        local_name="ChiNext / ChiNext 50 13w relative weakness",
    ),
]

ALL_INDICATORS = [*INDICATORS, *EXPERIMENTAL_INDICATORS]


def _display_value(value: object) -> str:
    parsed = risk._parse_float(value)
    return "-" if parsed is None else f"{parsed:.3f}"


def _normalize(values: list[tuple[dt.date, float]]) -> list[tuple[dt.date, float]]:
    valid = [(day, value) for day, value in values if value not in (None, 0)]
    if not valid:
        return []
    base = valid[0][1]
    return [(day, value / base * 100.0) for day, value in valid]


def _series_from_rows(rows: list[dict[str, object]], key: str, start: dt.date) -> list[tuple[dt.date, float]]:
    out: list[tuple[dt.date, float]] = []
    for row in rows:
        week = row.get("week")
        if not isinstance(week, dt.date) or week < start:
            continue
        value = risk._parse_float(row.get(key))
        if value is not None:
            out.append((week, value))
    return out


def _market_series(start: dt.date) -> dict[str, list[tuple[dt.date, float]]]:
    out: dict[str, list[tuple[dt.date, float]]] = {}
    soxx = event_review._nasdaq_window("SOXX", start, dt.date.today())
    out["SOXX"] = [(day, value) for day, value in soxx.items() if day >= start]
    series = _eastmoney_window("588200", "SSE", start, dt.date.today())
    out["588200.SH"] = [(day, value) for day, value in series.items() if day >= start]
    return out


def _weekly_markets(markets: dict[str, list[tuple[dt.date, float]]], start: dt.date, end: dt.date) -> dict[str, list[tuple[dt.date, float]]]:
    weeks = risk._all_week_ends(start, end)
    out: dict[str, list[tuple[dt.date, float]]] = {}
    for symbol, rows in markets.items():
        series = dict(rows)
        values = risk._weekly_asof(series, weeks, max_stale_days=14)
        out[symbol] = [(week, value) for week, value in zip(weeks, values) if value is not None]
    return out


def _eastmoney_window(ticker: str, market: str, start: dt.date, end: dt.date) -> dict[dt.date, float]:
    payload = _fetch_china_market_daily(ticker=ticker, market=market, days=1000)
    series: dict[dt.date, float] = {}
    for candle in payload.get("candles") or []:
        day = risk._parse_date(str(candle.get("date") or ""))
        close = risk._parse_float(candle.get("close"))
        if day and start <= day <= end and close is not None:
            series[day] = close
    if not series:
        raise RuntimeError(f"No EastMoney daily data parsed for {market}:{ticker}")
    return dict(sorted(series.items()))


def _fetch_china_market_daily(*, ticker: str, market: str, days: int) -> dict[str, object]:
    cache_key = (ticker, market)
    cached = _EASTMONEY_DAILY_CACHE.get(cache_key)
    if cached is not None:
        return cached
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            payload = fetch_eastmoney_daily(ticker=ticker, market=market, days=days)
            if payload.get("candles"):
                payload["sourceLabel"] = "EastMoney"
                _EASTMONEY_DAILY_CACHE[cache_key] = payload
            return payload
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.6 * (attempt + 1))
    yahoo_symbol = f"{ticker}.SS" if market.upper() == "SSE" else f"{ticker}.SZ"
    payload = fetch_yahoo_daily(symbol=yahoo_symbol, days=days)
    if payload.get("candles"):
        payload["sourceLabel"] = "Yahoo Finance A-share"
        payload["message"] = f"EastMoney failed, used {yahoo_symbol}: {last_error}"
        _EASTMONEY_DAILY_CACHE[cache_key] = payload
        return payload
    assert last_error is not None
    raise last_error


def _fetch_yahoo_daily_cached(symbol: str, *, days: int = 1000) -> dict[str, object]:
    cached = _YAHOO_DAILY_CACHE.get(symbol)
    if cached is not None:
        return cached
    payload = fetch_yahoo_daily(symbol=symbol, days=days)
    if payload.get("candles"):
        _YAHOO_DAILY_CACHE[symbol] = payload
    return payload


def _yahoo_window(symbol: str, start: dt.date, end: dt.date, *, days: int = 1000) -> dict[dt.date, float]:
    payload = _fetch_yahoo_daily_cached(symbol, days=days)
    series: dict[dt.date, float] = {}
    for candle in payload.get("candles") or []:
        day = risk._parse_date(str(candle.get("date") or ""))
        close = risk._parse_float(candle.get("close"))
        if day and start <= day <= end and close is not None:
            series[day] = close
    if not series:
        raise RuntimeError(str(payload.get("message") or f"No Yahoo daily data parsed for {symbol}"))
    return dict(sorted(series.items()))


def _add_relative_weakness_score(
    rows: list[dict[str, object]],
    *,
    value_key: str,
    numerator: dict[dt.date, float],
    denominator: dict[dt.date, float],
    lag: int = 13,
) -> None:
    weeks = [row["week"] for row in rows if isinstance(row.get("week"), dt.date)]
    numerator_values = risk._weekly_asof(numerator, weeks, max_stale_days=14)
    denominator_values = risk._weekly_asof(denominator, weeks, max_stale_days=14)
    relative_returns: list[float | None] = []
    for idx, value in enumerate(numerator_values):
        denom = denominator_values[idx]
        prev_value = numerator_values[idx - lag] if idx >= lag else None
        prev_denom = denominator_values[idx - lag] if idx >= lag else None
        if value is None or denom is None or prev_value in (None, 0) or prev_denom in (None, 0):
            relative_returns.append(None)
        else:
            relative_returns.append((value / prev_value - 1) - (denom / prev_denom - 1))
    percentiles = risk._expanding_percentile(relative_returns)
    for row, percentile in zip(rows, percentiles):
        row[value_key] = None if percentile is None else 1 - percentile


def _add_experimental_china_indicators(rows: list[dict[str, object]]) -> None:
    end = dt.date.today()
    history_start = end - dt.timedelta(days=1500)
    for value_key, numerator_symbol, denominator_symbol in [
        ("china_star100_star50_weakness_score", "588120.SS", "588000.SS"),
        ("china_chinext_100_50_weakness_score", "159915.SZ", "159949.SZ"),
    ]:
        numerator = _yahoo_window(numerator_symbol, history_start, end)
        denominator = _yahoo_window(denominator_symbol, history_start, end)
        _add_relative_weakness_score(rows, value_key=value_key, numerator=numerator, denominator=denominator)


def _episodes(markets: dict[str, list[tuple[dt.date, float]]]) -> list[event_review.DrawdownEpisode]:
    episodes: list[event_review.DrawdownEpisode] = []
    for symbol, prices in markets.items():
        label = MARKET_PROXIES.get(symbol, {}).get("label", symbol)
        episodes.extend(event_review._local_drawdown_episodes(symbol, label, prices))
    return episodes


def _x(day: dt.date, start: dt.date, end: dt.date, left: float, width: float) -> float:
    span = max(1, (end - start).days)
    return left + ((day - start).days / span) * width


def _path(
    values: list[tuple[dt.date, float]],
    *,
    start: dt.date,
    end: dt.date,
    top: float,
    height: float,
    left: float,
    width: float,
    min_value: float,
    max_value: float,
) -> str:
    if not values:
        return ""
    spread = max(max_value - min_value, 0.000001)
    points = []
    for day, value in values:
        x = _x(day, start, end, left, width)
        y = top + height - ((value - min_value) / spread) * height
        points.append(f"{x:.1f},{y:.1f}")
    return "M " + " L ".join(points)


def _event_bands(
    episodes: list[event_review.DrawdownEpisode],
    start: dt.date,
    end: dt.date,
    left: float,
    width: float,
    top: float,
    height: float,
) -> str:
    bands = []
    selected = [
        item
        for item in episodes
        if item.symbol in MARKET_PROXIES and item.trough_week >= start
    ]
    for item in selected:
        x1 = _x(item.peak_week, start, end, left, width)
        x2 = _x(item.trough_week, start, end, left, width)
        bands.append(
            f'<rect x="{x1:.1f}" y="{top:.1f}" width="{max(2, x2 - x1):.1f}" height="{height:.1f}" '
            f'fill="#f97316" opacity="0.10"><title>{html.escape(item.symbol)} '
            f'{item.peak_week.isoformat()} to {item.trough_week.isoformat()} '
            f'{item.drawdown * 100:.1f}%</title></rect>'
        )
    return "\n".join(bands)


def _axis_labels(start: dt.date, end: dt.date, left: float, width: float, top: float, height: float) -> str:
    months = []
    current = dt.date(start.year, start.month, 1)
    while current <= end:
        if current >= start:
            x = _x(current, start, end, left, width)
            months.append(
                f'<line x1="{x:.1f}" y1="{top:.1f}" x2="{x:.1f}" y2="{top + height:.1f}" stroke="#e5e7eb" />'
                f'<text x="{x:.1f}" y="{top + height + 24:.1f}" text-anchor="middle" class="axis">{current:%y-%m}</text>'
            )
        next_month = current.month + 1
        year = current.year + (1 if next_month == 13 else 0)
        month = 1 if next_month == 13 else next_month
        current = dt.date(year, month, 1)
    return "\n".join(months)


def _fmt_tick(value: float) -> str:
    return f"{value:.0f}" if abs(value) >= 10 else f"{value:.2f}"


def _svg_chart(
    spec: IndicatorSpec,
    indicator_rows: list[dict[str, object]],
    markets: dict[str, list[tuple[dt.date, float]]],
    episodes: list[event_review.DrawdownEpisode],
    *,
    start: dt.date,
    end: dt.date,
) -> str:
    left = 74
    right = 74
    width = SVG_WIDTH - left - right
    plot_top = 54
    plot_height = 410
    normalized = {symbol: _normalize(values) for symbol, values in markets.items()}
    all_market_values = [value for series in normalized.values() for _, value in series]
    market_min = min(all_market_values) if all_market_values else 80
    market_max = max(all_market_values) if all_market_values else 120
    market_pad = (market_max - market_min) * 0.08 or 5
    market_min -= market_pad
    market_max += market_pad
    indicator = _series_from_rows(indicator_rows, spec.value_key, start)
    market_paths = []
    for symbol, series in normalized.items():
        d = _path(
            series,
            start=start,
            end=end,
            top=plot_top,
            height=plot_height,
            left=left,
            width=width,
            min_value=market_min,
            max_value=market_max,
        )
        if d:
            color = MARKET_PROXIES.get(symbol, {}).get("color", "#64748b")
            market_paths.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.1" />')
    indicator_path = _path(
        indicator,
        start=start,
        end=end,
        top=plot_top,
        height=plot_height,
        left=left,
        width=width,
        min_value=0,
        max_value=1,
    )
    threshold_y = plot_top + plot_height - spec.threshold * plot_height
    latest = indicator[-1][1] if indicator else None
    latest_text = "-" if latest is None else f"{latest:.3f}"
    grid = []
    for fraction in (0, 0.25, 0.5, 0.75, 1):
        y = plot_top + plot_height * fraction
        grid.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + width}" y2="{y:.1f}" stroke="#e5e7eb" />')
    market_ticks = [market_max, (market_min + market_max) / 2, market_min]
    left_ticks = []
    for value in market_ticks:
        y = plot_top + plot_height - ((value - market_min) / max(market_max - market_min, 0.000001)) * plot_height
        left_ticks.append(f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" class="axis">{_fmt_tick(value)}</text>')
    right_ticks = []
    for value in sorted({0.0, spec.threshold, 1.0}, reverse=True):
        y = plot_top + plot_height - value * plot_height
        right_ticks.append(f'<text x="{left + width + 8}" y="{y + 4:.1f}" class="axis">{value:.2f}</text>')
    legend = " / ".join(
        f'<tspan fill="{html.escape(str(meta["color"]))}">{html.escape(str(meta["label"]))}</tspan>'
        for meta in MARKET_PROXIES.values()
    )
    return f"""
<svg viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}" role="img" aria-label="{html.escape(spec.title)} chart">
  <rect width="{SVG_WIDTH}" height="{SVG_HEIGHT}" fill="#ffffff" rx="6" />
  {_event_bands(episodes, start, end, left, width, plot_top, plot_height)}
  {"".join(grid)}
  {_axis_labels(start, end, left, width, plot_top, plot_height)}
  <line x1="{left}" y1="{plot_top}" x2="{left}" y2="{plot_top + plot_height}" stroke="#94a3b8" />
  <line x1="{left + width}" y1="{plot_top}" x2="{left + width}" y2="{plot_top + plot_height}" stroke="#94a3b8" />
  <line x1="{left}" y1="{plot_top + plot_height}" x2="{left + width}" y2="{plot_top + plot_height}" stroke="#94a3b8" />
  <text x="{left}" y="25" class="legend">{legend}，左轴起点=100</text>
  <text x="{SVG_WIDTH - 18}" y="24" text-anchor="end" class="legend">最新指标 {latest_text}</text>
  <text x="{left - 46}" y="{plot_top - 14}" class="axis">左轴行情</text>
  <text x="{left + width - 8}" y="{plot_top - 14}" text-anchor="end" class="axis">右轴指标</text>
  {"".join(left_ticks)}
  {"".join(right_ticks)}
  {"".join(market_paths)}
  <line x1="{left}" y1="{threshold_y:.1f}" x2="{left + width}" y2="{threshold_y:.1f}" stroke="#ef4444" stroke-dasharray="5 5" />
  <text x="{left + width - 4}" y="{threshold_y - 5:.1f}" text-anchor="end" class="threshold">触发线 {spec.threshold:.2f}</text>
  <path d="{indicator_path}" fill="none" stroke="#111827" stroke-width="2.3" />
</svg>
"""


def _fetch_local_availability() -> tuple[list[availability.SourceResult], list[availability.IndicatorResult]]:
    source_results: list[availability.SourceResult] = []
    for key in ["NFCI", "ANFCI", "BAA10Y", "VIXCLS", "VXVCLS", "DFII10", "DTWEXBGS"]:
        source_results.append(availability._fetch_fred(key))
    for symbol, assetclass in [
        ("NDX", "index"),
        ("SPY", "etf"),
        ("RSP", "etf"),
        ("QQQ", "etf"),
        ("QQEW", "etf"),
        ("SOXX", "etf"),
        ("HYG", "etf"),
        ("SHY", "etf"),
        ("XLY", "etf"),
        ("XLP", "etf"),
        ("IWM", "etf"),
        ("ACWI", "etf"),
        ("EEM", "etf"),
    ]:
        source_results.append(availability._fetch_nasdaq(symbol, assetclass))
    for key, ticker, market in [("588200.SH", "588200", "SSE")]:
        source_results.append(_fetch_eastmoney_source(key, ticker, market))
    for key, note in [
        ("588120.SS", "科创100ETF，实验性科创内部宽度分子"),
        ("588000.SS", "科创50ETF，实验性科创内部宽度分母"),
        ("159915.SZ", "创业板ETF，实验性创业板内部宽度分子"),
        ("159949.SZ", "创业板50ETF，实验性创业板内部宽度分母"),
    ]:
        source_results.append(_fetch_yahoo_source(key, note))
    source_results.append(availability._fetch_finra_margin())
    sources = {item.key: item for item in source_results}
    latest_week = availability._latest_week()
    indicator_results = [
        availability._indicator_status(spec.title, "report indicator", list(spec.source_keys), sources, latest_week, max_stale_days=75 if spec.key == "finra_margin" else risk.FRED_CACHE_MAX_STALE_DAYS if any(key in {"NFCI", "ANFCI", "BAA10Y", "VIXCLS", "VXVCLS", "DFII10", "DTWEXBGS"} for key in spec.source_keys) else 14, note="visual report input")
        for spec in ALL_INDICATORS
    ]
    indicator_results.extend(
        [
            availability.IndicatorResult(
                name="FINRA margin debt",
                role="slow leverage background",
                sources=["FINRA_MARGIN_DEBT"],
                status=sources.get("FINRA_MARGIN_DEBT", availability.SourceResult("FINRA_MARGIN_DEBT", "FINRA", "fail")).status,
                latest_week=latest_week.isoformat(),
                latest_dates=[sources.get("FINRA_MARGIN_DEBT", availability.SourceResult("FINRA_MARGIN_DEBT", "FINRA", "fail")).latest_date or "-"],
                min_rows=sources.get("FINRA_MARGIN_DEBT", availability.SourceResult("FINRA_MARGIN_DEBT", "FINRA", "fail")).rows,
                note="monthly and delayed; not plotted in v1 charts",
            ),
            availability.IndicatorResult(
                name="AAII Sentiment Survey",
                role="sentiment candidate",
                sources=["AAII"],
                status="blocked",
                latest_week=latest_week.isoformat(),
                latest_dates=["-"],
                min_rows=None,
                note="official source triggers Incapsula/Imperva; excluded from automatic v1",
            ),
        ]
    )
    return source_results, indicator_results


def _fetch_eastmoney_source(key: str, ticker: str, market: str) -> availability.SourceResult:
    started = time.time()
    try:
        payload = _fetch_china_market_daily(ticker=ticker, market=market, days=1000)
        candles = payload.get("candles") or []
        series = {
            day: close
            for candle in candles
            if (day := risk._parse_date(str(candle.get("date") or ""))) is not None
            and (close := risk._parse_float(candle.get("close"))) is not None
        }
        if not series:
            raise RuntimeError(str(payload.get("message") or f"No EastMoney candles for {key}"))
        latest = max(series)
        return availability.SourceResult(
            key=key,
            source=str(payload.get("sourceLabel") or "EastMoney"),
            status="ok",
            rows=len(series),
            first_date=min(series).isoformat(),
            latest_date=latest.isoformat(),
            latest_value=series[latest],
            seconds=round(time.time() - started, 2),
            note=str(payload.get("message") or "A-share/ETF daily candles; EastMoney primary, Yahoo A-share fallback"),
        )
    except Exception as exc:
        return availability.SourceResult(
            key=key,
            source="EastMoney",
            status="fail",
            seconds=round(time.time() - started, 2),
            error=str(exc),
        )


def _fetch_yahoo_source(key: str, note: str) -> availability.SourceResult:
    started = time.time()
    try:
        payload = _fetch_yahoo_daily_cached(key, days=1000)
        candles = payload.get("candles") or []
        series = {
            day: close
            for candle in candles
            if (day := risk._parse_date(str(candle.get("date") or ""))) is not None
            and (close := risk._parse_float(candle.get("close"))) is not None
        }
        if not series:
            raise RuntimeError(str(payload.get("message") or f"No Yahoo candles for {key}"))
        latest = max(series)
        return availability.SourceResult(
            key=key,
            source="Yahoo Finance",
            status="ok",
            rows=len(series),
            first_date=min(series).isoformat(),
            latest_date=latest.isoformat(),
            latest_value=series[latest],
            seconds=round(time.time() - started, 2),
            note=note,
        )
    except Exception as exc:
        return availability.SourceResult(
            key=key,
            source="Yahoo Finance",
            status="fail",
            seconds=round(time.time() - started, 2),
            error=str(exc),
        )


def _source_probe_commands() -> dict[str, str]:
    fred = "curl -L --silent --max-time 18 --connect-timeout 6 'https://fred.stlouisfed.org/graph/fredgraph.csv?id={key}&cosd=2026-01-01' | head -2"
    nasdaq = "curl -L --silent --max-time 18 --connect-timeout 6 --user-agent 'Mozilla/5.0' -H 'Origin: https://www.nasdaq.com' -H 'Referer: https://www.nasdaq.com/' 'https://api.nasdaq.com/api/quote/{key}/historical?assetclass=etf&fromdate=2026-07-01&todate=2026-07-10&limit=10' | head -1"
    china_yahoo = "curl -L --silent --max-time 18 --connect-timeout 6 --user-agent 'Mozilla/5.0' 'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1mo' | head -1"
    finra = "curl -L --silent --max-time 18 --connect-timeout 6 'https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics' | head -3"
    aaii = "curl -L --silent --max-time 18 --connect-timeout 6 --user-agent 'Mozilla/5.0' 'https://www.aaii.com/sentimentsurvey/sent_results' | head -3"
    commands: dict[str, str] = {}
    for key in ["NFCI", "ANFCI", "BAA10Y", "VIXCLS", "VXVCLS", "DFII10", "DTWEXBGS"]:
        commands[key] = fred.format(key=key)
    for key in ["SPY", "RSP", "QQQ", "QQEW", "SOXX", "HYG", "SHY", "XLY", "XLP", "IWM", "ACWI", "EEM"]:
        commands[key] = nasdaq.format(key=key)
    for key in ["588200.SH", "588120.SS", "588000.SS", "159915.SZ", "159949.SZ"]:
        symbol = "588200.SS" if key == "588200.SH" else key
        commands[key] = china_yahoo.format(symbol=symbol)
    commands["FINRA_MARGIN_DEBT"] = finra
    commands["AAII"] = aaii
    return commands


def _ssh_command() -> list[str] | None:
    candidates = [Path("C:/Windows/System32/OpenSSH/ssh.exe"), Path("ssh")]
    ssh = next((item for item in candidates if str(item) == "ssh" or item.exists()), None)
    if ssh is None:
        return None
    command = [
        str(ssh),
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=20",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]
    key_path = Path("C:/Users/Windows/.ssh/id_ed25519")
    if key_path.exists():
        command.extend(["-i", str(key_path)])
    command.append(f"{SERVER_USER}@{SERVER_HOST}")
    return command


def _probe_linux_sources() -> dict[str, dict[str, object]]:
    ssh = _ssh_command()
    if ssh is None:
        return {"__error__": {"status": "unknown", "note": "ssh executable not found"}}
    script_lines = ["set -u"]
    for key, command in _source_probe_commands().items():
        script_lines.extend(
            [
                f"echo '__BEGIN__{key}'",
                f"{{ {command}; }} 2>&1 | sed -n '1,5p'",
                f"echo '__END__{key}'",
            ]
        )
    script = "\n".join(script_lines)
    try:
        result = subprocess.run(
            [*ssh, "bash -s"],
            input=script.encode("utf-8"),
            capture_output=True,
            timeout=180,
            check=False,
        )
    except Exception as exc:
        return {"__error__": {"status": "unknown", "note": str(exc)}}
    output = result.stdout.decode("utf-8", errors="replace") + "\n" + result.stderr.decode("utf-8", errors="replace")
    probes: dict[str, dict[str, object]] = {}
    for key in _source_probe_commands():
        begin = f"__BEGIN__{key}"
        end = f"__END__{key}"
        if begin not in output or end not in output:
            probes[key] = {"status": "unknown", "note": "missing probe output"}
            continue
        text = output.split(begin, 1)[1].split(end, 1)[0].strip()
        lowered = text.lower()
        if not text:
            status = "unknown"
        elif key == "AAII":
            status = "blocked" if "incapsula" in lowered or "pardon our interruption" in lowered else "ok"
        elif key in {"588200.SH", "588120.SS", "588000.SS", "159915.SZ", "159949.SZ"} and '"chart"' in lowered and '"result"' in lowered:
            status = "ok"
        else:
            status = "fail" if "curl:" in lowered or "error" in lowered and key not in {"FINRA_MARGIN_DEBT"} else "ok"
        if key == "FINRA_MARGIN_DEBT" and ("margin" in lowered or "<!doctype html" in lowered or "<html" in lowered):
            status = "ok"
        probes[key] = {"status": status, "note": " ".join(text.split())[:220]}
    return probes


def _linux_status_for(spec: IndicatorSpec, probes: dict[str, dict[str, object]]) -> str:
    statuses = [str(probes.get(key, {}).get("status", "unknown")) for key in spec.source_keys]
    if any(status in {"fail", "blocked"} for status in statuses):
        return "fail"
    if any(status == "unknown" for status in statuses):
        return "unknown"
    return "ok"


def _availability_html(
    indicators: list[availability.IndicatorResult],
    probes: dict[str, dict[str, object]],
    sources: list[availability.SourceResult],
) -> str:
    by_name = {item.name: item for item in indicators}
    by_source = {item.key: item for item in sources}
    rows = []
    for spec in ALL_INDICATORS:
        local = by_name.get(spec.title)
        rows.append(
            "<tr>"
            f"<td>{html.escape(spec.title)}</td>"
            f"<td><span class='pill ok'>{html.escape(local.status if local else 'unknown')}</span></td>"
            f"<td><span class='pill {_linux_status_for(spec, probes)}'>{html.escape(_linux_status_for(spec, probes))}</span></td>"
            f"<td>{html.escape(', '.join(spec.source_keys))}</td>"
            f"<td>{html.escape(local.note if local else '')}</td>"
            "</tr>"
        )
    for key, label, note in [
        ("SOXX", "美国半导体代理 SOXX", "Nasdaq ETF 日线，用于报告里的美国半导体走势，不作为风险指标计分项"),
        ("588200.SH", "科创代理 588200.SH", "东方财富 A 股/ETF 日线，Yahoo A 股代码兜底；用于报告里的中国科创走势，不作为风险指标计分项"),
    ]:
        local = by_source.get(key)
        linux = str(probes.get(key, {}).get("status", "unknown"))
        rows.append(
            "<tr>"
            f"<td>{html.escape(label)}</td>"
            f"<td><span class='pill {html.escape(local.status if local else 'unknown')}'>{html.escape(local.status if local else 'unknown')}</span></td>"
            f"<td><span class='pill {html.escape(linux)}'>{html.escape(linux)}</span></td>"
            f"<td>{html.escape(key)}</td>"
            f"<td>{html.escape(note)}</td>"
            "</tr>"
        )
    rows.append(
        "<tr><td>FINRA margin debt</td><td><span class='pill ok'>ok</span></td>"
        f"<td><span class='pill {probes.get('FINRA_MARGIN_DEBT', {}).get('status', 'unknown')}'>"
        f"{html.escape(str(probes.get('FINRA_MARGIN_DEBT', {}).get('status', 'unknown')))}</span></td>"
        "<td>FINRA_MARGIN_DEBT</td><td>月频滞后，作为杠杆背景，不进 v1 图组</td></tr>"
    )
    rows.append(
        "<tr><td>AAII Sentiment Survey</td><td><span class='pill blocked'>blocked</span></td>"
        f"<td><span class='pill {probes.get('AAII', {}).get('status', 'unknown')}'>"
        f"{html.escape(str(probes.get('AAII', {}).get('status', 'unknown')))}</span></td>"
        "<td>AAII</td><td>官方源触发反爬挑战，不纳入自动指标</td></tr>"
    )
    return "\n".join(rows)


def _episode_summary(episodes: list[event_review.DrawdownEpisode]) -> list[dict[str, object]]:
    buckets = [
        ("2026-03 美国半导体/全球下跌", dt.date(2026, 3, 1), dt.date(2026, 3, 31)),
        ("2026-05/06 中国科创回撤", dt.date(2026, 5, 1), dt.date(2026, 6, 30)),
        ("2026-06/07 半导体与科创回撤", dt.date(2026, 6, 1), dt.date(2026, 7, 10)),
    ]
    out = []
    for label, start, end in buckets:
        matched = [item for item in episodes if start <= item.trough_week <= end]
        out.append(
            {
                "label": label,
                "episodes": [
                    {
                        "symbol": item.symbol,
                        "peak_week": item.peak_week.isoformat(),
                        "trough_week": item.trough_week.isoformat(),
                        "drawdown_pct": round(item.drawdown * 100, 2),
                    }
                    for item in matched
                ],
            }
        )
    return out


def _episode_html(summary: list[dict[str, object]]) -> str:
    rows = []
    for bucket in summary:
        episodes = bucket["episodes"]
        if not episodes:
            text = "未识别到 5% 以上局部回撤"
        else:
            text = "; ".join(
                f"{item['symbol']} {item['peak_week']}→{item['trough_week']} {item['drawdown_pct']}%"
                for item in episodes[:6]
            )
        rows.append(f"<tr><td>{html.escape(str(bucket['label']))}</td><td>{html.escape(text)}</td></tr>")
    return "\n".join(rows)


def _html_report(
    indicator_rows: list[dict[str, object]],
    sources: list[availability.SourceResult],
    indicators: list[availability.IndicatorResult],
    probes: dict[str, dict[str, object]],
    markets: dict[str, list[tuple[dt.date, float]]],
    episodes: list[event_review.DrawdownEpisode],
    *,
    start: dt.date,
    end: dt.date,
) -> str:
    latest_row = max(indicator_rows, key=lambda row: row["week"])
    sections = []
    for spec in ALL_INDICATORS:
        value = _display_value(latest_row.get(spec.value_key))
        sections.append(
            f"""
<section class="indicator">
  <div class="indicator-head">
    <div>
      <h2>{html.escape(spec.title)}</h2>
      <p>{html.escape(spec.explanation)}</p>
      <p class="verdict">{html.escape(spec.conclusion)}</p>
    </div>
    <div class="metric"><span>最新</span><strong>{value}</strong></div>
  </div>
  {_svg_chart(spec, indicator_rows, markets, episodes, start=start, end=end)}
</section>
"""
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>顶部风险指标图文报告</title>
  <style>
    body {{ margin: 0; background: #f8fafc; color: #111827; font-family: Arial, "Microsoft YaHei", sans-serif; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 32px 22px 56px; }}
    header {{ margin-bottom: 24px; }}
    h1 {{ margin: 0 0 10px; font-size: 30px; }}
    h2 {{ margin: 0 0 8px; font-size: 20px; }}
    p {{ line-height: 1.65; }}
    .summary, .indicator, .table-card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin: 18px 0; box-shadow: 0 1px 2px #0000000d; }}
    .lead {{ font-size: 17px; font-weight: 700; color: #0f172a; }}
    .muted {{ color: #64748b; }}
    .indicator-head {{ display: flex; justify-content: space-between; gap: 18px; align-items: flex-start; }}
    .indicator-head p {{ margin: 6px 0; }}
    .verdict {{ color: #b45309; font-weight: 700; }}
    .metric {{ min-width: 92px; text-align: right; border-left: 1px solid #e5e7eb; padding-left: 16px; }}
    .metric span {{ display: block; color: #64748b; font-size: 12px; }}
    .metric strong {{ font-size: 24px; }}
    svg {{ width: 100%; height: auto; margin-top: 12px; border: 1px solid #e5e7eb; border-radius: 6px; }}
    .axis {{ fill: #64748b; font-size: 12px; }}
    .legend {{ fill: #334155; font-size: 13px; font-weight: 700; }}
    .threshold {{ fill: #ef4444; font-size: 12px; font-weight: 700; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ padding: 10px 9px; border-bottom: 1px solid #e5e7eb; vertical-align: top; text-align: left; }}
    th {{ background: #f1f5f9; color: #334155; }}
    .pill {{ display: inline-block; min-width: 52px; text-align: center; padding: 2px 8px; border-radius: 999px; font-weight: 700; font-size: 12px; background: #e2e8f0; }}
    .pill.ok {{ background: #dcfce7; color: #166534; }}
    .pill.fail, .pill.blocked {{ background: #fee2e2; color: #991b1b; }}
    .pill.unknown {{ background: #fef3c7; color: #92400e; }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>顶部风险指标图文报告</h1>
    <p class="muted">生成时间：{dt.datetime.now().isoformat(timespec="seconds")}；图表区间：{start.isoformat()} 至 {end.isoformat()}。</p>
  </header>
  <section class="summary">
    <p class="lead">近期真正提前预警较好的指标是市场宽度、QQEW/QQQ、XLY/XLP 与 VIX 期限结构；实际利率更多是宏观压力背景；传统信用条件在近期不是领先信号。</p>
    <p>图里的美国市场走势已从 QQQ 换成 SOXX，美国半导体行情可通过 Nasdaq 公共历史接口获取；中国市场只保留 588200.SH 作为科创方向代理。</p>
    <p>中国内部宽度先做实验观察：科创100ETF/科创50ETF、创业板ETF/创业板50ETF。它们不是严格等权口径，只用于看“更宽的一侧是否开始跑输更窄核心”。</p>
    <p class="muted">图表从 2026-01-01 起展示；行情线使用日线以保留转折，指标仍为周频分位/压力。左轴为行情（起点=100），右轴为指标，橙色阴影为周频局部回撤窗口。</p>
  </section>
  <section class="table-card">
    <h2>指标可用性</h2>
    <table>
      <thead><tr><th>指标</th><th>本地</th><th>Linux</th><th>依赖源</th><th>说明</th></tr></thead>
      <tbody>{_availability_html(indicators, probes, sources)}</tbody>
    </table>
  </section>
  <section class="table-card">
    <h2>近期下跌段摘要</h2>
    <table>
      <thead><tr><th>阶段</th><th>自动识别的局部回撤</th></tr></thead>
      <tbody>{_episode_html(_episode_summary(episodes))}</tbody>
    </table>
  </section>
  {"".join(sections)}
</main>
</body>
</html>
"""


def run(output_dir: Path, *, probe_linux: bool = True) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    start = dt.date(2026, 1, 1)
    end = dt.date.today()
    local_sources, local_indicators = _fetch_local_availability()
    indicator_rows = event_review._build_indicator_rows()
    for row in indicator_rows:
        rsp = risk._parse_float(row.get("rsp_spy_13w_rel_pctl"))
        qqew = risk._parse_float(row.get("qqew_qqq_13w_rel_pctl"))
        row["rsp_spy_weakness_score"] = None if rsp is None else 1 - rsp
        row["qqew_qqq_weakness_score"] = None if qqew is None else 1 - qqew
    _add_experimental_china_indicators(indicator_rows)
    markets = _market_series(start)
    episodes = _episodes(_weekly_markets(markets, start, end))
    probes = _probe_linux_sources() if probe_linux else {"__error__": {"status": "unknown", "note": "linux probe skipped"}}
    html_report = _html_report(
        indicator_rows,
        local_sources,
        local_indicators,
        probes,
        markets,
        episodes,
        start=start,
        end=end,
    )
    html_path = output_dir / REPORT_HTML
    json_path = output_dir / REPORT_JSON
    html_path.write_text(html_report, encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
                "market_chart_frequency": "daily",
                "indicator_frequency": "weekly",
                "local_sources": [asdict(item) for item in local_sources],
                "local_indicators": [asdict(item) for item in local_indicators],
                "linux_probes": probes,
                "episodes": [
                    {
                        "symbol": item.symbol,
                        "label": item.label,
                        "peak_week": item.peak_week.isoformat(),
                        "trough_week": item.trough_week.isoformat(),
                        "drawdown_pct": round(item.drawdown * 100, 2),
                    }
                    for item in episodes
                ],
                "indicators": [asdict(item) for item in ALL_INDICATORS],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {html_path}")
    print(f"Wrote {json_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a visual HTML report for market top-risk indicators.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--probe-linux", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    return run(args.output_dir, probe_linux=args.probe_linux)


if __name__ == "__main__":
    raise SystemExit(main())
