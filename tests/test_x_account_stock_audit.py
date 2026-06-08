from __future__ import annotations

from datetime import date
from pathlib import Path
from zipfile import ZipFile

import pytest

from tools.audit.x_account_stock_audit.ai_extract import chunk_posts, extract_mentions
from tools.audit.x_account_stock_audit.fetcher import fetch_posts
from tools.audit.x_account_stock_audit.market import attach_prices_and_build_charts, build_scores
from tools.audit.x_account_stock_audit.models import AuditPost, AuditResult, Candle, StockMention
from tools.audit.x_account_stock_audit.report import build_excel_sheets, write_excel, write_html


def _status(tweet_id: str, created_at: str, *, author: str = "aleabitoreddit", text: str = "$AMD long") -> dict:
    return {
        "id": tweet_id,
        "created_at": created_at,
        "text": text,
        "author": {"screen_name": author, "name": author},
        "url": f"https://x.com/{author}/status/{tweet_id}",
    }


def _post(tweet_id: str, text: str = "$AMD long") -> AuditPost:
    return AuditPost(
        tweet_id=tweet_id,
        author="@aleabitoreddit",
        author_name="Alea",
        text=text,
        published_at="2026-05-20T10:00:00+08:00",
        url=f"https://x.com/aleabitoreddit/status/{tweet_id}",
    )


def _mention(tweet_id: str = "1", stance: str = "bull") -> StockMention:
    return StockMention(
        tweet_id=tweet_id,
        published_at="2026-05-20T10:00:00+08:00",
        stock_name="AMD",
        ticker_or_code="AMD",
        market_hint="NASDAQ",
        stance=stance,  # type: ignore[arg-type]
        direction="positive" if stance == "bull" else "unknown",
        judgment_type="direct",
        confidence=0.9,
        viewpoint="long AMD",
        evidence="$AMD long",
        tweet_url=f"https://x.com/aleabitoreddit/status/{tweet_id}",
        security_key="amd",
        display_name="AMD",
        ticker="AMD",
        market="NASDAQ",
    )


def test_fetch_posts_uses_cursor_date_stop_and_filters_author() -> None:
    pages = {
        None: (
            [
                _status("1", "Wed May 20 10:00:00 +0000 2026"),
                _status("2", "Wed May 20 11:00:00 +0000 2026", author="other"),
            ],
            {"bottom": "cursor2"},
        ),
        "cursor2": (
            [_status("3", "Sat Apr 18 10:00:00 +0000 2026")],
            {"bottom": "cursor3"},
        ),
    }

    def fake_fetch(_username: str, *, count: int, cursor: str | None):
        return pages[cursor]

    posts, raw, summary = fetch_posts(
        username="aleabitoreddit",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
        fetch_statuses=fake_fetch,
        page_pause_sec=0,
    )

    assert [post.tweet_id for post in posts] == ["1"]
    assert len(raw) == 3
    assert summary["stopped_reason"] == "before_start_date"


def test_chunk_posts_respects_max_posts() -> None:
    posts = [_post(str(index)) for index in range(81)]
    chunks = chunk_posts(posts)
    assert [len(chunk) for chunk in chunks] == [40, 40, 1]


def test_extract_mentions_falls_back_to_split_after_batch_failure() -> None:
    posts = [_post(str(index)) for index in range(12)]
    calls: list[int] = []

    def structured(_settings, _model, messages):
        raise RuntimeError("schema unavailable")

    def fallback(_settings, _model, messages):
        payload = messages[-1]["content"]
        batch_size = payload.count("tweet_id")
        calls.append(batch_size)
        if batch_size > 10:
            raise RuntimeError("too large")
        return {
            "mentions": [
                {
                    "tweet_id": "0",
                    "published_at": posts[0].published_at,
                    "stock_name": "AMD",
                    "ticker_or_code": "AMD",
                    "market_hint": "NASDAQ",
                    "stance": "bullish",
                    "direction": "positive",
                    "judgment_type": "direct",
                    "confidence": 0.9,
                    "viewpoint": "long AMD",
                    "evidence": "$AMD long",
                }
            ]
        }

    settings = type("Settings", (), {"api_key": "x"})()
    mentions = extract_mentions(posts, model="gpt-5.4-mini", settings=settings, structured_call=structured, fallback_call=fallback)

    assert calls[0] == 12
    assert 6 in calls
    assert mentions[0].stance == "bull"


def test_market_scoring_uses_directional_forward_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    candles = [
        {"date": "2026-05-20", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100},
        {"date": "2026-05-21", "open": 10, "high": 12, "low": 10, "close": 11, "volume": 100},
        {"date": "2026-05-22", "open": 11, "high": 13, "low": 11, "close": 12, "volume": 100},
        {"date": "2026-05-23", "open": 12, "high": 14, "low": 12, "close": 13, "volume": 100},
        {"date": "2026-05-24", "open": 13, "high": 15, "low": 13, "close": 14, "volume": 100},
        {"date": "2026-05-25", "open": 14, "high": 16, "low": 14, "close": 15, "volume": 100},
    ]
    monkeypatch.setattr(
        "tools.audit.x_account_stock_audit.market.fetch_chart_payload",
        lambda **_kwargs: {"sourceLabel": "test", "sourceSymbol": "AMD", "message": None, "candles": candles},
    )

    mention = _mention("1", "bull")
    charts = attach_prices_and_build_charts([mention])
    scores = build_scores(charts)

    assert mention.price_close == 10
    assert mention.forward_returns["1d"] == pytest.approx(0.1)
    assert scores[0].hit_rate_1d == 1


def test_excel_and_html_outputs(tmp_path: Path) -> None:
    mention = _mention()
    chart = attach_prices_and_build_charts([mention], skip_market=True)[0]
    result = AuditResult(
        profile_url="https://x.com/aleabitoreddit",
        username="aleabitoreddit",
        run_dir=str(tmp_path),
        started_at=__import__("datetime").datetime.now(),
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
        posts=[_post("1")],
        mentions=[mention],
        charts=[chart],
        scores=build_scores([chart]),
        manifest={},
    )
    sheets = build_excel_sheets(result)
    assert "stance_matrix" in sheets
    assert "raw_mentions" in sheets

    excel_path = tmp_path / "audit.xlsx"
    html_path = tmp_path / "report.html"
    write_excel(excel_path, result)
    write_html(html_path, result)

    with ZipFile(excel_path) as archive:
        assert "xl/workbook.xml" in archive.namelist()
    assert "AMD" in html_path.read_text(encoding="utf-8")

