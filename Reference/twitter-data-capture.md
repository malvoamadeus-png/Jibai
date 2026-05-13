# Twitter/X Data Capture Reference

This reference is a project-neutral guide for capturing public Twitter/X post
data. It describes the practical pipeline, failure modes, and a reusable
reference implementation pattern.

## Goals

Capture recent public posts for one or more usernames with:

- Stable tweet IDs
- Author username and display name
- Text
- Original URL
- Created-at timestamp when available
- Public engagement counts when available
- Media URLs when available, without downloading media by default
- Per-account diagnostics that explain why a capture returned no data

## Recommended Source Order

Use multiple sources because public Twitter/X access changes often.

1. FXTwitter-compatible JSON endpoints.
   - User info: `https://api.fxtwitter.com/{username}`
   - Recent statuses: `https://api.fxtwitter.com/2/profile/{username}/statuses`
   - Tweet detail: `https://api.fxtwitter.com/{username}/status/{tweet_id}`
   - This is lightweight and usually much cheaper than browser scraping.
   - Treat it as an unofficial public interface: schemas and availability can
     change without notice.

2. Nitter/XCancel-style public timeline pages as fallback.
   - Open `https://{instance}/{username}`.
   - Parse `.timeline-item` entries.
   - Follow the `cursor` link for pagination.
   - Use a real browser runtime such as Playwright because many instances need
     JavaScript-compatible navigation behavior.

3. Official Twitter/X API when credentials and product limits are acceptable.
   - This is the most policy-stable option, but it requires account setup and
     paid/API-plan constraints in many cases.

## Capture Strategy

Normalize usernames before fetching:

- Accept `x.com/name`, `twitter.com/name`, `https://x.com/name`, or `@name`.
- Require the Twitter/X username pattern: `^[A-Za-z0-9_]{1,15}$`.
- Reject reserved routes such as `home`, `search`, `explore`, `settings`, and
  `i`.

Fetch more candidates than you need:

- If the caller needs 10 new posts, scan 20 to 30 candidates.
- Filter duplicates using a persisted `seen_tweet_ids` set.
- Skip retweets or non-target-author posts unless the product explicitly wants
  them.
- Skip old pinned posts when only recent content is desired.

Enrich candidates with detail calls:

- A timeline result may not contain all fields.
- Fetch tweet detail by ID before storing final records.
- If one detail fetch fails, skip that tweet and continue with the next one.
- Fail the whole account only when no usable tweet remains.

## Bandwidth Controls

For low-bandwidth Linux servers, prefer JSON endpoints first. If browser
fallback is needed:

- Block `font`, `image`, and `media` resource types in Playwright.
- Extract media URLs from HTML instead of downloading media bytes.
- Use `wait_until="domcontentloaded"` rather than waiting for all network
  activity.
- Keep page count low, usually 1 to 3 pages per account.
- Add a small delay between accounts and pages.
- Store debug HTML/screenshots only on failures and keep them temporary.

## Failure Classification

Return structured statuses instead of only returning an empty list.

- `success`: at least one usable tweet was parsed.
- `runtime_failed`: local browser/runtime dependency failed, such as missing
  Playwright Chromium.
- `fetch_failed`: request, navigation, anti-bot, CAPTCHA, Cloudflare, DDoS
  protection, or rate-limit failure.
- `parse_failed`: page loaded but DOM extraction failed.
- `parse_empty`: page/API returned successfully but contained no usable posts.

Useful anti-bot markers:

- `verifying your request`
- `verify you are human`
- `captcha`
- `cloudflare`
- `ddos-guard`
- `access denied`
- `too many requests`
- `rate limit`

## Output Shape

Use a normalized record independent of the source:

```json
{
  "platform": "x",
  "tweet_id": "1234567890",
  "author_username": "example",
  "author_display_name": "Example",
  "url": "https://x.com/example/status/1234567890",
  "text": "Post text",
  "created_at": "2026-05-06T12:34:56+08:00",
  "reply_count": 0,
  "retweet_count": 0,
  "like_count": 0,
  "bookmark_count": 0,
  "view_count": 0,
  "media_urls": [],
  "metadata": {
    "source": "fxtwitter",
    "is_pinned": false
  }
}
```

## Operational Checklist

- Verify connectivity from the target server with one account and one page.
- Log source attempts per account.
- Persist seen tweet IDs after successful storage.
- Keep timeouts short: 15 to 30 seconds per HTTP/browser operation.
- Use per-account isolation so one broken account does not fail the whole run.
- Never store credentials, cookies, or private tokens in code or diagnostics.
- Respect applicable site terms, robots policies, rate limits, and local laws.

See `Reference/twitter_capture_reference.py` for a standalone reference code
template.
