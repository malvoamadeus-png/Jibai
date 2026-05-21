from __future__ import annotations

from contextlib import contextmanager

from packages.onchain.gmgn_labels import OKXTokenSearchCandidate
from packages.public_app.crypto_asset_narrative import (
    BlockedAssetMatch,
    CandidateDecision,
    CryptoAssetBriefTarget,
    SearchGroup,
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
        "packages.public_app.crypto_asset_narrative._fetch_targets",
        lambda *_args, **_kwargs: [_asset()],
    )
    monkeypatch.setattr(
        "packages.public_app.crypto_asset_narrative._fetch_existing_success",
        lambda *_args, **_kwargs: {"asset_key": "orbiter", "status": "succeeded"},
    )

    assert generate_crypto_asset_briefs_once(force=False) == 0
