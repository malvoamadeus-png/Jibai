from __future__ import annotations

import sys
import types
from contextlib import contextmanager

import pytest

from packages.onchain.gmgn_labels import OKXTokenSearchCandidate
from packages.public_app.crypto_asset_narrative import (
    BlockedAssetMatch,
    CandidateDecision,
    CryptoAssetBriefTarget,
    ExistingCAResolution,
    SearchGroup,
    _assess_identity_status,
    _candidate_group_overlap,
    _decide_candidate_pass,
    _decision_rank_key,
    _extract_existing_resolution,
    _find_blocked_match,
    _match_candidate_with_ai,
    generate_crypto_asset_briefs_once,
)
from packages.public_app.x_search import XSearchTweet


def _asset() -> CryptoAssetBriefTarget:
    return CryptoAssetBriefTarget(
        asset_key="orbiter",
        display_name="Orbiter",
        symbol="OBT",
        chain="Ethereum",
        identifier_type="project_name",
        aliases=["Orbiter Finance", "OBT"],
        raw_identifiers=[],
        contract_addresses=[],
        x_accounts=["@Orbiter_Finance"],
        first_seen_date="2026-05-01",
        latest_seen_date="2026-05-21",
        mention_count=12,
    )


def _tweet(
    url: str,
    *,
    author: str,
    text: str,
    likes: int = 0,
    replies: int = 0,
    views: int = 0,
) -> XSearchTweet:
    return XSearchTweet(
        url=url,
        author=author,
        author_name=author.lstrip("@"),
        text=text,
        created_at="2026-05-21T10:00:00Z",
        tweet_id=url.rsplit("/", 1)[-1],
        likes=likes,
        retweets=0,
        replies=replies,
        views=views,
        title="",
        snippet="",
        query_variant="",
    )


def _candidate(contract_address: str, *, community: bool = False, liquidity: float | None = None) -> OKXTokenSearchCandidate:
    return OKXTokenSearchCandidate(
        contract_address=contract_address,
        chain_index="1",
        display_name="Orbiter",
        symbol="OBT",
        chain_name="Ethereum",
        community_recognized=community,
        holder_count=1500.0,
        liquidity=liquidity,
        market_cap=2_000_000.0,
        raw={},
    )


def test_extract_existing_resolution_uses_known_contracts() -> None:
    base = _asset()
    asset = CryptoAssetBriefTarget(
        asset_key=base.asset_key,
        display_name=base.display_name,
        symbol=base.symbol,
        chain=base.chain,
        identifier_type=base.identifier_type,
        aliases=base.aliases,
        raw_identifiers=["something", "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"],
        contract_addresses=base.contract_addresses,
        x_accounts=base.x_accounts,
        first_seen_date=base.first_seen_date,
        latest_seen_date=base.latest_seen_date,
        mention_count=base.mention_count,
    )

    resolution = _extract_existing_resolution(asset)

    assert resolution is not None
    assert resolution.contract_address == "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
    assert resolution.status == "existing_identifier"


def test_candidate_overlap_detects_shared_accounts_and_keywords() -> None:
    name_group = SearchGroup(
        label="name",
        queries=["Orbiter"],
        tweets=[
            _tweet("https://x.com/a/status/1", author="@alice", text="Orbiter bridge volume is picking up"),
            _tweet("https://x.com/b/status/2", author="@bob", text="OBT community keeps talking about bridge incentives"),
        ],
        warning_messages=[],
        error_messages=[],
    )
    candidate_group = SearchGroup(
        label="candidate",
        queries=["0x123"],
        tweets=[
            _tweet("https://x.com/a/status/3", author="@alice", text="0x123 looks like the Orbiter bridge token"),
            _tweet("https://x.com/c/status/4", author="@carol", text="Orbiter Finance bridge campaign is getting traction"),
        ],
        warning_messages=[],
        error_messages=[],
    )

    overlap = _candidate_group_overlap(_asset(), name_group, candidate_group)

    assert overlap["has_overlap"] is True
    assert overlap["shared_accounts"] == ["alice"]
    assert "bridge" in overlap["shared_keywords"]


def test_low_sample_match_caps_confidence() -> None:
    class FakeClient:
        def generate_json(self, *_args, **_kwargs):
            class Result:
                parsed = {
                    "same_project": True,
                    "confidence": 0.95,
                    "shared_signals": ["bridge", "@orbiter_finance"],
                    "reason": "same project",
                }
                usage = {"input_tokens": 10, "output_tokens": 10}
                model_name = "gpt-5.4-mini"

            return Result()

    name_group = SearchGroup(
        label="name",
        queries=["Orbiter"],
        tweets=[_tweet(f"https://x.com/a/status/{i}", author="@alice", text=f"Orbiter bridge update {i}") for i in range(1, 5)],
        warning_messages=[],
        error_messages=[],
    )
    candidate_group = SearchGroup(
        label="candidate",
        queries=["0x123"],
        tweets=[_tweet(f"https://x.com/b/status/{i}", author="@bob", text=f"0x123 Orbiter bridge post {i}") for i in range(5, 9)],
        warning_messages=[],
        error_messages=[],
    )
    usage = {"input_tokens": 0, "output_tokens": 0}

    same_project, confidence, shared_signals, reason = _match_candidate_with_ai(
        FakeClient(),
        asset=_asset(),
        name_group=name_group,
        candidate_group=candidate_group,
        overlap={"shared_accounts": [], "shared_aliases": [], "shared_keywords": ["bridge"], "shared_project_fragments": [], "has_overlap": True},
        usage_totals=usage,
    )

    assert same_project is True
    assert confidence == 0.74
    assert shared_signals == ["bridge", "@orbiter_finance"]
    assert reason == "same project"
    assert usage["input_tokens"] == 10


def test_candidate_pass_requires_threshold_and_shared_signal() -> None:
    overlap = {
        "shared_accounts": [],
        "shared_aliases": [],
        "shared_keywords": ["bridge", "campaign"],
        "shared_project_fragments": [],
        "has_overlap": True,
    }

    assert _decide_candidate_pass(overlap=overlap, same_project=True, confidence=0.8) is True
    assert _decide_candidate_pass(overlap=overlap, same_project=True, confidence=0.74) is False
    assert _decide_candidate_pass(overlap=overlap, same_project=False, confidence=0.95) is False


def test_decision_rank_prefers_confidence_then_strength() -> None:
    base_overlap = {
        "shared_accounts": ["alice"],
        "shared_aliases": [],
        "shared_keywords": ["bridge"],
        "shared_project_fragments": [],
        "has_overlap": True,
    }
    weaker = CandidateDecision(
        candidate=_candidate("0x111", community=False, liquidity=1000),
        overlap=base_overlap,
        same_project=True,
        confidence=0.81,
        shared_signals=["bridge"],
        reason="",
        passes=True,
        name_sample_count=8,
        candidate_sample_count=8,
    )
    stronger = CandidateDecision(
        candidate=_candidate("0x222", community=True, liquidity=100000),
        overlap=base_overlap,
        same_project=True,
        confidence=0.92,
        shared_signals=["bridge"],
        reason="",
        passes=True,
        name_sample_count=8,
        candidate_sample_count=8,
    )

    ranked = sorted([weaker, stronger], key=_decision_rank_key, reverse=True)

    assert ranked[0].candidate.contract_address == "0x222"


def test_blocked_term_matches_display_name_and_skips() -> None:
    asset = _asset()
    match = _find_blocked_match(asset, ["base", "solana"])
    assert match is None

    base_asset = CryptoAssetBriefTarget(
        asset_key="proj:base",
        display_name="Base",
        symbol="",
        chain="Base",
        identifier_type="project_name",
        aliases=["Base chain"],
        raw_identifiers=[],
        contract_addresses=[],
        x_accounts=[],
        first_seen_date="2026-05-01",
        latest_seen_date="2026-05-21",
        mention_count=10,
    )
    blocked = _find_blocked_match(base_asset, ["base"])
    assert blocked == BlockedAssetMatch(term="base", source_field="asset_key")


def test_generate_skips_existing_success_without_force(monkeypatch) -> None:
    class FakeConn:
        pass

    @contextmanager
    def fake_postgres_connection():
        yield FakeConn()

    monkeypatch.setattr(
        "packages.public_app.crypto_asset_narrative.postgres_connection",
        fake_postgres_connection,
    )
    monkeypatch.setattr(
        "packages.public_app.crypto_asset_narrative.is_domain_pipeline_enabled",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "packages.public_app.crypto_asset_narrative._fetch_targets",
        lambda *_args, **_kwargs: [_asset()],
    )
    monkeypatch.setattr(
        "packages.public_app.crypto_asset_narrative._fetch_existing_success",
        lambda *_args, **_kwargs: {"asset_key": "orbiter", "status": "succeeded"},
    )

    assert generate_crypto_asset_briefs_once(force=False) == 0


def test_identity_status_is_anchored_when_resolution_exists() -> None:
    identity = _assess_identity_status(
        _asset(),
        name_group=SearchGroup(
            label="name",
            queries=["Orbiter"],
            tweets=[_tweet("https://x.com/orbiter_finance/status/1", author="@orbiter_finance", text="Orbiter bridge update")],
            warning_messages=[],
            error_messages=[],
        ),
        resolution=ExistingCAResolution(
            contract_address="0x123",
            chain_index="1",
            status="existing_identifier",
            resolved_by="existing_identifier",
        ),
        decisions=[],
    )

    assert identity.status == "anchored"


def test_identity_status_is_fuzzy_for_official_account_single_cluster() -> None:
    asset = CryptoAssetBriefTarget(
        asset_key="proj:aeon",
        display_name="AEON",
        symbol="AEON",
        chain="Base",
        identifier_type="project_name",
        aliases=["OnchainOS"],
        raw_identifiers=[],
        contract_addresses=[],
        x_accounts=["@aeon_xyz"],
        first_seen_date="2026-05-01",
        latest_seen_date="2026-05-21",
        mention_count=20,
    )
    name_group = SearchGroup(
        label="name",
        queries=["AEON", "@aeon_xyz", "OnchainOS"],
        tweets=[
            _tweet("https://x.com/aeon_xyz/status/1", author="@aeon_xyz", text="AEON / OnchainOS agent framework update"),
            _tweet("https://x.com/bob/status/2", author="@bob", text="OnchainOS is the AEON agent framework people are testing"),
            _tweet("https://x.com/carol/status/3", author="@carol", text="AEON builders keep shipping new OnchainOS agent tooling"),
        ],
        warning_messages=[],
        error_messages=[],
    )

    identity = _assess_identity_status(asset, name_group=name_group, resolution=None, decisions=[])

    assert identity.status == "fuzzy"
    assert identity.official_account_match is True


@pytest.mark.parametrize(
    ("asset", "tweets"),
    [
        (
            CryptoAssetBriefTarget(
                asset_key="tick:aeon",
                display_name="AEON",
                symbol="AEON",
                chain="Base",
                identifier_type="symbol",
                aliases=["OnchainOS"],
                raw_identifiers=[],
                contract_addresses=[],
                x_accounts=[],
                first_seen_date="2026-05-01",
                latest_seen_date="2026-05-21",
                mention_count=20,
            ),
            [
                _tweet("https://x.com/alice/status/11", author="@alice", text="AEON agent framework / OnchainOS shipped a new tool"),
                _tweet("https://x.com/bob/status/12", author="@bob", text="Builders keep trying AEON with the OnchainOS agent stack"),
                _tweet("https://x.com/carl/status/13", author="@carl", text="AEON meme ticker is ripping on Base today"),
                _tweet("https://x.com/dan/status/14", author="@dan", text="Watching the AEON meme token chart on Base"),
            ],
        ),
        (
            CryptoAssetBriefTarget(
                asset_key="tick:pitch",
                display_name="PITCH",
                symbol="PITCH",
                chain="Base",
                identifier_type="symbol",
                aliases=[],
                raw_identifiers=[],
                contract_addresses=[],
                x_accounts=[],
                first_seen_date="2026-05-01",
                latest_seen_date="2026-05-21",
                mention_count=20,
            ),
            [
                _tweet("https://x.com/alice/status/21", author="@alice", text="PITCH token community is rotating back on Base"),
                _tweet("https://x.com/bob/status/22", author="@bob", text="New catalyst for PITCH meme traders"),
                _tweet("https://x.com/carl/status/23", author="@carl", text="Great pitch from the founder at today's startup demo day"),
                _tweet("https://x.com/dan/status/24", author="@dan", text="The baseball pitch count is getting wild tonight"),
            ],
        ),
        (
            CryptoAssetBriefTarget(
                asset_key="tick:surplus",
                display_name="Surplus",
                symbol="SURPLUS",
                chain="Base",
                identifier_type="project_name",
                aliases=[],
                raw_identifiers=[],
                contract_addresses=[],
                x_accounts=[],
                first_seen_date="2026-05-01",
                latest_seen_date="2026-05-21",
                mention_count=20,
            ),
            [
                _tweet("https://x.com/alice/status/31", author="@alice", text="Surplus protocol fee switch is back in focus"),
                _tweet("https://x.com/bob/status/32", author="@bob", text="Surplus token holders are debating the protocol treasury"),
                _tweet("https://x.com/carl/status/33", author="@carl", text="China's trade surplus beat expectations again this month"),
                _tweet("https://x.com/dan/status/34", author="@dan", text="Budget surplus headlines are everywhere this morning"),
            ],
        ),
    ],
)
def test_identity_status_regression_samples_are_ambiguous(asset: CryptoAssetBriefTarget, tweets: list[XSearchTweet]) -> None:
    identity = _assess_identity_status(
        asset,
        name_group=SearchGroup(
            label="name",
            queries=[asset.display_name],
            tweets=tweets,
            warning_messages=[],
            error_messages=[],
        ),
        resolution=None,
        decisions=[],
    )

    assert identity.status == "ambiguous"


def test_generate_failure_persists_query_and_source_stats(monkeypatch) -> None:
    captured: list[dict[str, object]] = []

    class FakeConn:
        pass

    @contextmanager
    def fake_postgres_connection():
        yield FakeConn()

    def fake_upsert(_conn, **kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(
        "packages.public_app.crypto_asset_narrative.postgres_connection",
        fake_postgres_connection,
    )
    monkeypatch.setattr(
        "packages.public_app.crypto_asset_narrative.is_domain_pipeline_enabled",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "packages.public_app.crypto_asset_narrative._fetch_targets",
        lambda *_args, **_kwargs: [_asset()],
    )
    monkeypatch.setattr(
        "packages.public_app.crypto_asset_narrative._fetch_existing_success",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "packages.public_app.crypto_asset_narrative._fetch_blocked_terms",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "packages.public_app.crypto_asset_narrative._generate_expanded_keywords",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "packages.public_app.crypto_asset_narrative._search_group",
        lambda label, queries, **_kwargs: SearchGroup(
            label=label,
            queries=list(queries),
            tweets=[],
            warning_messages=[],
            error_messages=["Orbiter: x search runtime unavailable: Playwright Chromium is not installed"],
        ),
    )
    monkeypatch.setattr(
        "packages.public_app.crypto_asset_narrative._resolve_candidate_via_similarity",
        lambda *_args, **_kwargs: (None, [], {}),
    )
    monkeypatch.setattr(
        "packages.public_app.crypto_asset_narrative._upsert_brief",
        fake_upsert,
    )
    sys.modules["packages.ai.client"] = types.SimpleNamespace(LLMJsonClient=lambda *_args, **_kwargs: object())

    assert generate_crypto_asset_briefs_once(force=True) == 1
    failed = captured[-1]

    assert failed["status"] == "failed"
    assert failed["query_set"] == {
        "name_queries": ["Orbiter", "OBT", "@Orbiter_Finance", "Orbiter Finance"],
        "expanded_keywords": [],
        "candidate_queries": {},
    }
    assert failed["source_stats"]["name_group_errors"]
    assert "not enough X samples for summary" in failed["error_text"]
