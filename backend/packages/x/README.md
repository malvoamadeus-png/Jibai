# X

Minimal X/Twitter account crawler extracted for the local backend.

- Input: full `https://x.com/<username>` profile URLs
- Timeline source: public Nitter pages via Playwright
- Tweet detail source: FxTwitter API
- Output: normalized records written into the shared SQLite store

This package is intentionally scoped to:

- fixed account watchlists
- latest tweets from specific users
- one-shot crawling without login
