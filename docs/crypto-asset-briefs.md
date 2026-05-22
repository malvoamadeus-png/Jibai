# Crypto Asset Briefs

## Purpose

This module generates one short narrative brief per visible crypto asset for
`/crypto/assets/overview`.

Each brief must answer two questions in 1-2 Chinese sentences:

- what the project or token does
- what the current X narrative or crowd perception is

The frontend only shows the final summary text and status. It must not expose
candidate contract addresses or internal CA-matching evidence.

## Storage

Supabase migrations:

- `supabase/migrations/023_crypto_asset_narrative_briefs.sql`
- `supabase/migrations/025_crypto_matrix_identity_filters.sql`

Primary table: `public.crypto_asset_narrative_briefs`

Uniqueness:

- one row per `asset_key`

Important fields:

- `summary_text`
- `contract_address`
- `chain_index`
- `ca_resolution_status`
- `resolved_by`
- `candidate_contracts_json`
- `query_set_json`
- `source_urls_json`
- `source_stats_json`
- `model_name`
- `prompt_version`
- `status`
- `error_text`
- `identity_status`

`get_visible_crypto_matrix(...)` merges these frontend-safe fields into each
asset payload:

- `summary`
- `summary_status`
- `identity_status`
- `summary_updated_at`

The frontend must treat `summary_status` and `identity_status` as two different
axes:

- `summary_status` answers whether a brief exists
- `identity_status` answers how confidently the project identity was pinned

## Resolution Flow

X search is now a backend-owned runtime under
`backend/packages/public_app/x_search.py`. Mainline code must not import or
execute scripts from `Reference/`.

Search behavior is fixed to browser-only:

- Playwright + Chromium
- backend-internal search/fetch code
- no Nitter dependency for this brief pipeline
- `PUBLIC_X_SEARCH_BACKEND` is compatibility-read only; non-`browser` values are
  downgraded to `browser` with a warning

The backend builds explicit error reasons for:

- Playwright import failure
- Chromium missing or launch failure
- search page open failure
- zero search hits
- tweet detail fetch failure

The CA flow is fixed to four stages:

1. Reuse `crypto_entities.contract_addresses_json` and stored raw identifiers first.
2. If unresolved, query OKX Onchain OS `token/search` for up to five CA candidates.
3. Build two X-search corpora:
   - a name-group using display name, symbol, aliases, project accounts, and AI-expanded short keywords
   - one candidate-group per CA using `CA`, `"CA" + display_name`, and `"CA" + symbol`
4. Compare the name-group and each candidate-group, then bind only the best candidate that passes the similarity rules.

CA is helpful for disambiguation and extra recall, but it is not a hard
prerequisite for generating the brief.

## Identity Status

Brief generation now separates "can we summarize" from "did we fully pin the
project identity".

Status values:

- `anchored`: existing identifier or CA candidate passed the match rules
- `fuzzy`: no hard CA anchor, but official account / alias / dominant cluster
  still points to one likely project
- `ambiguous`: samples contain multi-project or generic-word noise, so the
  summary must stay conservative

High-ambiguity triggers include:

- short tickers
- common English words
- project names that overlap with generic terms
- multiple candidate projects
- tweets split across unrelated account/topic clusters

Frontend behavior:

- `anchored`: show normal summary
- `fuzzy`: show normal summary with `模糊说明`
- `ambiguous`: show conservative summary with `高歧义`, and the text itself must
  explicitly mention that project identity is not fully confirmed or may be
  mixed with same-name discussions

## Similarity Rules

Cheap filter first:

- dedupe by tweet URL
- compare shared accounts
- compare shared aliases
- compare shared keywords
- compare shared project-name fragments

AI match second:

- model: `gpt-5.4-mini`
- max representative samples: 8 tweets from each side
- output shape:
  - `same_project`
  - `confidence`
  - `shared_signals`
  - `reason`

Acceptance rules:

- `same_project=true`
- `confidence >= 0.75`
- and at least one of:
  - same project account appears on both sides
  - at least two stable shared keywords
  - an alias or shorthand from the name-group also appears in the candidate-group

Low-sample behavior:

- if either side has fewer than 3 tweets, mark unresolved
- if either side has fewer than 5 tweets, AI confidence is capped below the pass threshold

Tie-break order when multiple candidates pass:

1. higher AI confidence
2. more shared signals
3. stronger OKX metadata such as `communityRecognized`, holders, liquidity, and market cap

## Search Limits

- name-group target: up to 20 deduped tweets
- each candidate-group target: up to 20 deduped tweets
- final summary input: up to 50 merged tweets

AI keyword expansion is used only on the name-group and should return 3-5 short
terms from these categories:

- project alias
- sector term
- community shorthand
- mechanism term

Do not output full sentences as expansion keywords.

## Model And Freeze Rules

- model is pinned to `gpt-5.4-mini`
- successful rows are skipped on later runs unless `--force` is passed
- unresolved CA is allowed as long as the name-group has enough X samples for summary generation
- backend search requires Playwright Chromium to be installed in the runtime

## Commands

Manual run:

```bash
python backend/src/main.py public-generate-crypto-asset-briefs
```

Target a subset:

```bash
python backend/src/main.py public-generate-crypto-asset-briefs --asset-key orbiter --asset-key aeon
```

Force refresh:

```bash
python backend/src/main.py public-generate-crypto-asset-briefs --asset-key orbiter --force
```

Worker schedule env:

```bash
PUBLIC_WORKER_CRYPTO_ASSET_BRIEF_TIME=22:50
```

## Failure Handling

If all CA candidates fail:

- keep `contract_address` empty
- set `ca_resolution_status='unresolved'`
- still generate a summary from name-group tweets when possible

If summary generation itself fails:

- write `status='failed'`
- keep `error_text`
- keep `query_set_json`, `source_stats_json`, and collected source URLs when
  available
- allow a later rerun with `--force`

`error_text` should preserve the real cause when possible, instead of collapsing
everything into a generic sample-shortage message. Common examples include:

- search runtime unavailable
- search returned zero matching X URLs
- tweet detail fetch failed
- not enough usable X samples after dedupe/filtering

## Admin Controls

`supabase/migrations/024_crypto_admin_controls.sql` adds two admin-only control
paths:

- `crypto_asset_blocklist`
- `crypto_asset_admin_deletions`

Blocked term behavior:

- if `asset_key`, `display_name`, `symbol`, or aliases match a blocked term, the
  brief job writes `status='skipped'`
- the asset is skipped before all later X-search / CA-search / AI-summary work
- the same blocked asset is hidden from visible crypto asset list, detail, and
  overview RPC results

The first default blocked term is:

- `base`

Admin delete behavior:

- deleting an asset marks the `asset_key` in `crypto_asset_admin_deletions`
- the asset is hidden from crypto list, detail, and overview surfaces,
  including `get_visible_crypto_matrix(...)`
- existing brief rows for that asset are removed immediately
- later brief runs no longer pick that asset as a target

## Validation

Backend checks:

```bash
$env:PYTHONPATH='backend'
python -m pytest tests/test_crypto_asset_narrative.py tests/test_public_x_search.py tests/test_gmgn_labels.py tests/test_stock_narrative.py tests/test_public_api.py -q
python -m compileall backend/packages backend/src tests
```

Frontend check:

```bash
cd public-web
npm run build
```
