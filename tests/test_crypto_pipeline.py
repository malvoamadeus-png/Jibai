from __future__ import annotations

from packages.ai.pipeline import (
    _build_author_day_record,
    _materialize_crypto_timelines,
    _parse_crypto_viewpoint,
)
from packages.common.crypto_aliases import resolve_crypto_identity
from packages.common.models import NoteExtractRecord, RawNoteRecord, ViewpointRecord


def test_resolve_crypto_identity_groups_project_name_and_account() -> None:
    identity = resolve_crypto_identity(
        entity_name="1confirmation",
        entity_code_or_name="@1confirmation",
        entity_identifier_type="project_account",
        raw_identifiers=["1confirmation", "@1confirmation"],
        aliases={},
    )

    assert identity is not None
    assert identity.asset_key == "proj:1confirmation"
    assert identity.resolver_strategy == "project_group"
    assert identity.match_confidence == "medium"


def test_resolve_crypto_identity_groups_symbol_and_meme_ticker() -> None:
    symbol_identity = resolve_crypto_identity(
        entity_name="AEON",
        entity_code_or_name="AEON",
        entity_identifier_type="symbol",
        raw_identifiers=["AEON"],
        aliases={},
    )
    meme_identity = resolve_crypto_identity(
        entity_name="AEON",
        entity_code_or_name="AEON",
        entity_identifier_type="meme_ticker",
        raw_identifiers=["AEON"],
        aliases={},
    )

    assert symbol_identity is not None
    assert meme_identity is not None
    assert symbol_identity.asset_key == "tick:aeon"
    assert meme_identity.asset_key == "tick:aeon"


def test_parse_crypto_viewpoint_marks_generic_terms_as_non_asset() -> None:
    viewpoint = _parse_crypto_viewpoint(
        {
            "entity_type": "crypto_entity",
            "entity_name": "decentralized LLM project",
            "entity_code_or_name": "decentralized LLM",
            "entity_identifier_type": "project_name",
            "raw_identifiers": ["decentralized LLM"],
            "entity_kind": "theme_or_generic",
            "is_generic_term": True,
            "investable_score": 0.1,
            "specificity_score": 0.2,
            "entityness_score": 0.3,
            "signal_type": "mention_signal",
            "judgment_type": "mention_only",
            "direction": "unknown",
            "conviction": "none",
            "evidence_type": "other",
            "logic": "泛主题提及",
            "evidence": "去中心化 LLM 项目",
        },
        order=0,
        aliases={},
    )

    assert viewpoint is not None
    assert viewpoint.metadata["entity_kind"] == "theme_or_generic"
    assert viewpoint.metadata["is_generic_term"] is True
    assert viewpoint.metadata["asset_candidate"] is False


def test_materialize_crypto_timelines_skips_non_asset_candidates() -> None:
    extract = NoteExtractRecord(
        platform="x",
        note_id="n1",
        account_name="alice",
        profile_url="https://example.com/alice",
        note_url="https://example.com/n1",
        date="2026-05-21",
        extracted_at="2026-05-21T10:00:00Z",
        analysis_domain="crypto",
        viewpoints=[
            ViewpointRecord(
                entity_type="crypto_entity",
                entity_key="tick:aeon",
                entity_name="AEON",
                entity_code_or_name="AEON",
                entity_identifier_type="symbol",
                raw_identifiers=["AEON"],
                signal_type="mention_signal",
                judgment_type="mention_only",
                conviction="none",
                metadata={"asset_candidate": True},
            ),
            ViewpointRecord(
                entity_type="crypto_entity",
                entity_key="proj:decentralizedllmproject",
                entity_name="decentralized LLM project",
                entity_code_or_name="decentralized LLM",
                entity_identifier_type="project_name",
                raw_identifiers=["decentralized LLM"],
                signal_type="mention_signal",
                judgment_type="mention_only",
                conviction="none",
                metadata={"asset_candidate": False, "entity_kind": "theme_or_generic"},
            ),
        ],
    )

    records = _materialize_crypto_timelines(store=object(), extracts={"x::n1": extract})

    assert len(records) == 1
    assert records[0].asset_key == "tick:aeon"
    assert records[0].display_name == "AEON"


def test_build_author_day_record_filters_non_asset_crypto_mentions() -> None:
    note = RawNoteRecord(
        platform="x",
        account_name="alice",
        profile_url="https://example.com/alice",
        note_id="n1",
        url="https://example.com/n1",
        fetched_at="2026-05-21T10:00:00Z",
    )
    extract = NoteExtractRecord(
        platform="x",
        note_id="n1",
        account_name="alice",
        profile_url="https://example.com/alice",
        note_url="https://example.com/n1",
        date="2026-05-21",
        extracted_at="2026-05-21T10:00:00Z",
        analysis_domain="crypto",
        viewpoints=[
            ViewpointRecord(
                entity_type="crypto_entity",
                entity_key="tick:aeon",
                entity_name="AEON",
                entity_code_or_name="AEON",
                entity_identifier_type="symbol",
                raw_identifiers=["AEON"],
                signal_type="mention_signal",
                judgment_type="mention_only",
                conviction="none",
                metadata={"asset_candidate": True},
            ),
            ViewpointRecord(
                entity_type="crypto_entity",
                entity_key="proj:decentralizedllmproject",
                entity_name="decentralized LLM project",
                entity_code_or_name="decentralized LLM",
                entity_identifier_type="project_name",
                raw_identifiers=["decentralized LLM"],
                signal_type="mention_signal",
                judgment_type="mention_only",
                conviction="none",
                metadata={"asset_candidate": False, "entity_kind": "theme_or_generic"},
            ),
        ],
    )

    record = _build_author_day_record(
        platform="x",
        account_name="alice",
        profile_url="https://example.com/alice",
        date="2026-05-21",
        status="has_update_today",
        notes=[note],
        extracts=[extract],
        existing=None,
        crawl_error=None,
        analysis_domain="crypto",
    )

    assert record.mentioned_crypto == ["AEON"]
    assert len(record.viewpoints) == 2
