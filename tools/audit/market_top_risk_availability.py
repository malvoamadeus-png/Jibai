from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import re
import sys
import time
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from packages.public_app import market_top_risk as risk  # noqa: E402


FINRA_MARGIN_URL = "https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics"
FINRA_DOWNLOAD_RE = re.compile(r'href="([^"]*margin-statistics\.xlsx)"', re.IGNORECASE)
FINRA_ROW_RE = re.compile(
    r"<tr><td>([A-Za-z]{3}-\d{2})</td><td>([\d,]+)</td><td>([\d,]+)</td><td>([\d,]+)</td></tr>",
    re.IGNORECASE,
)


@dataclass
class SourceResult:
    key: str
    source: str
    status: str
    rows: int | None = None
    first_date: str | None = None
    latest_date: str | None = None
    latest_value: float | None = None
    seconds: float | None = None
    error: str | None = None
    note: str | None = None


@dataclass
class IndicatorResult:
    name: str
    role: str
    sources: list[str]
    status: str
    latest_week: str
    latest_dates: list[str]
    min_rows: int | None
    note: str


def _month_end(month_key: str) -> dt.date:
    parsed = dt.datetime.strptime(month_key, "%b-%y").date()
    return parsed.replace(day=calendar.monthrange(parsed.year, parsed.month)[1])


def _fetch_finra_margin() -> SourceResult:
    started = time.time()
    try:
        raw = risk._download_url(FINRA_MARGIN_URL).decode("utf-8", errors="replace")
        rows: dict[dt.date, float] = {}
        for month_key, debit, *_rest in FINRA_ROW_RE.findall(raw):
            rows[_month_end(month_key)] = float(debit.replace(",", ""))
        download_match = FINRA_DOWNLOAD_RE.search(raw)
        note = "recent HTML table parsed"
        if download_match:
            href = download_match.group(1)
            url = urllib.parse.urljoin(FINRA_MARGIN_URL, href)
            data = risk._download_url(url)
            note = f"recent HTML table parsed; xlsx downloadable bytes={len(data)}"
        if not rows:
            raise RuntimeError("No FINRA margin rows parsed from page")
        latest = max(rows)
        return SourceResult(
            key="FINRA_MARGIN_DEBT",
            source="FINRA",
            status="ok",
            rows=len(rows),
            first_date=min(rows).isoformat(),
            latest_date=latest.isoformat(),
            latest_value=rows[latest],
            seconds=round(time.time() - started, 2),
            note=note,
        )
    except Exception as exc:
        return SourceResult(
            key="FINRA_MARGIN_DEBT",
            source="FINRA",
            status="fail",
            seconds=round(time.time() - started, 2),
            error=str(exc),
        )


def _summarize_series(key: str, source: str, series: dict[dt.date, float], seconds: float, note: str | None = None) -> SourceResult:
    latest = max(series)
    return SourceResult(
        key=key,
        source=source,
        status="ok",
        rows=len(series),
        first_date=min(series).isoformat(),
        latest_date=latest.isoformat(),
        latest_value=series[latest],
        seconds=round(seconds, 2),
        note=note,
    )


def _fetch_fred(key: str) -> SourceResult:
    started = time.time()
    try:
        series = risk._fetch_fred_series(key)
        return _summarize_series(key, "FRED", series, time.time() - started)
    except Exception as exc:
        return SourceResult(key=key, source="FRED", status="fail", seconds=round(time.time() - started, 2), error=str(exc))


def _fetch_nasdaq(symbol: str, assetclass: str = "etf") -> SourceResult:
    started = time.time()
    try:
        series = risk._fetch_nasdaq_price(symbol, assetclass, dt.date.today())
        note = "Nasdaq public ETF history currently returns about 10 years" if assetclass == "etf" else None
        return _summarize_series(symbol, "Nasdaq", series, time.time() - started, note=note)
    except Exception as exc:
        return SourceResult(key=symbol, source="Nasdaq", status="fail", seconds=round(time.time() - started, 2), error=str(exc))


def _latest_week() -> dt.date:
    weeks = risk._all_week_ends(risk.START_DATE, dt.date.today())
    return weeks[-1]


def _indicator_status(
    name: str,
    role: str,
    keys: list[str],
    sources: dict[str, SourceResult],
    latest_week: dt.date,
    *,
    max_stale_days: int,
    note: str,
) -> IndicatorResult:
    required = [sources[key] for key in keys]
    failures = [item for item in required if item.status != "ok"]
    latest_dates: list[str] = [item.latest_date or "-" for item in required]
    rows = [item.rows for item in required if item.rows is not None]
    stale = []
    for item in required:
        if not item.latest_date:
            continue
        latest = dt.date.fromisoformat(item.latest_date)
        if (latest_week - latest).days > max_stale_days:
            stale.append(item.key)
    status = "ok"
    if failures:
        status = "fail"
    elif stale:
        status = "stale"
    return IndicatorResult(
        name=name,
        role=role,
        sources=keys,
        status=status,
        latest_week=latest_week.isoformat(),
        latest_dates=latest_dates,
        min_rows=min(rows) if rows else None,
        note=(f"stale sources: {', '.join(stale)}; {note}" if stale else note),
    )


def _markdown_report(sources: list[SourceResult], indicators: list[IndicatorResult]) -> str:
    lines = [
        "# Market Top Risk Source Availability",
        "",
        f"Generated at: {dt.datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Indicator Checks",
        "",
        "| Indicator | Role | Status | Sources | Latest dates | Min rows | Note |",
        "| --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for item in indicators:
        lines.append(
            "| "
            + " | ".join(
                [
                    item.name,
                    item.role,
                    item.status,
                    ", ".join(item.sources),
                    ", ".join(item.latest_dates),
                    str(item.min_rows or "-"),
                    item.note.replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Raw Source Checks",
            "",
            "| Key | Source | Status | Rows | First | Latest | Latest value | Seconds | Note / Error |",
            "| --- | --- | --- | ---: | --- | --- | ---: | ---: | --- |",
        ]
    )
    for item in sources:
        lines.append(
            "| "
            + " | ".join(
                [
                    item.key,
                    item.source,
                    item.status,
                    str(item.rows or "-"),
                    item.first_date or "-",
                    item.latest_date or "-",
                    "-" if item.latest_value is None else f"{item.latest_value:g}",
                    "-" if item.seconds is None else f"{item.seconds:.2f}",
                    (item.note or item.error or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def run(output_dir: Path) -> int:
    source_results: list[SourceResult] = []
    for key in ["NFCI", "ANFCI", "BAA10Y", "VIXCLS", "VXVCLS", "DFII10", "DTWEXBGS"]:
        source_results.append(_fetch_fred(key))
    for symbol, assetclass in [
        ("NDX", "index"),
        ("SPY", "etf"),
        ("RSP", "etf"),
        ("QQQ", "etf"),
        ("QQEW", "etf"),
        ("HYG", "etf"),
        ("SHY", "etf"),
        ("XLY", "etf"),
        ("XLP", "etf"),
        ("IWM", "etf"),
    ]:
        source_results.append(_fetch_nasdaq(symbol, assetclass))
    source_results.append(_fetch_finra_margin())

    sources = {item.key: item for item in source_results}
    latest_week = _latest_week()
    indicators = [
        _indicator_status("RSP/SPY 13w relative percentile", "old breadth warning", ["RSP", "SPY"], sources, latest_week, max_stale_days=14, note="ETF pair can be aligned to weekly Friday prices."),
        _indicator_status("QQEW/QQQ 13w relative percentile", "old breadth warning", ["QQEW", "QQQ"], sources, latest_week, max_stale_days=14, note="ETF pair can be aligned to weekly Friday prices."),
        _indicator_status("NFCI 13w tightening percentile", "old financial confirmation", ["NFCI"], sources, latest_week, max_stale_days=risk.FRED_CACHE_MAX_STALE_DAYS, note="Weekly FRED series; use as-of weekly alignment."),
        _indicator_status("ANFCI pressure percentile", "old financial confirmation", ["ANFCI"], sources, latest_week, max_stale_days=risk.FRED_CACHE_MAX_STALE_DAYS, note="Weekly FRED series; use as-of weekly alignment."),
        _indicator_status("BAA10Y credit spread percentile", "old credit confirmation", ["BAA10Y"], sources, latest_week, max_stale_days=risk.FRED_CACHE_MAX_STALE_DAYS, note="Daily FRED series; use as-of weekly alignment."),
        _indicator_status("Financial conditions / credit composite", "old confirmation group", ["NFCI", "ANFCI", "BAA10Y"], sources, latest_week, max_stale_days=risk.FRED_CACHE_MAX_STALE_DAYS, note="Composite is available when the three raw FRED series are available."),
        _indicator_status("HYG/SHY 13w relative percentile", "new credit proxy", ["HYG", "SHY"], sources, latest_week, max_stale_days=14, note="Daily ETF proxy; no macro revision issue."),
        _indicator_status("VIX/VIX3M term-structure percentile", "new volatility confirmation", ["VIXCLS", "VXVCLS"], sources, latest_week, max_stale_days=risk.FRED_CACHE_MAX_STALE_DAYS, note="FRED VIXCLS and VXVCLS can support 5d/20d smoothing."),
        _indicator_status("XLY/XLP 13w relative percentile", "new defensive rotation warning", ["XLY", "XLP"], sources, latest_week, max_stale_days=14, note="Daily ETF pair; low implementation cost."),
        _indicator_status("IWM/SPY 13w relative percentile", "new breadth proxy", ["IWM", "SPY"], sources, latest_week, max_stale_days=14, note="Overlaps with breadth group, so should not be counted independently."),
        _indicator_status("DFII10 13w change percentile", "new real-rate pressure", ["DFII10"], sources, latest_week, max_stale_days=risk.FRED_CACHE_MAX_STALE_DAYS, note="Daily FRED series; use 13-week change."),
        _indicator_status("DTWEXBGS 13w return percentile", "new dollar liquidity pressure", ["DTWEXBGS"], sources, latest_week, max_stale_days=risk.FRED_CACHE_MAX_STALE_DAYS, note="Daily FRED broad dollar index."),
        _indicator_status("FINRA margin debt rollover", "new slow leverage confirmation", ["FINRA_MARGIN_DEBT"], sources, latest_week, max_stale_days=75, note="Monthly and delayed; useful as background, not precise timing."),
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    report = _markdown_report(source_results, indicators)
    (output_dir / "availability-report.md").write_text(report, encoding="utf-8")
    (output_dir / "availability-report.json").write_text(
        json.dumps(
            {
                "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
                "latest_week": latest_week.isoformat(),
                "indicators": [asdict(item) for item in indicators],
                "sources": [asdict(item) for item in source_results],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(report)
    print(f"Wrote {output_dir / 'availability-report.md'}")
    print(f"Wrote {output_dir / 'availability-report.json'}")
    return 1 if any(item.status == "fail" for item in indicators) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check old and candidate market top-risk indicator data availability.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=risk.CACHE_DIR.parent / "availability",
        help="Directory for markdown/json reports. Defaults to data/runtime/market_top_risk/availability.",
    )
    args = parser.parse_args()
    return run(args.output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
