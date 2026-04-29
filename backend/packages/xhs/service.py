from __future__ import annotations

import json
import random
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import BrowserContext, Page, sync_playwright

from packages.common.io import read_json, write_json
from packages.common.models import CrawlAccountResult, RawNoteRecord
from packages.common.paths import AppPaths
from packages.common.time_utils import is_older_than_days, now_iso

from .config import AccountTarget, WatchlistConfig
from .detail import NoteFetchError, NoteText, create_client, fetch_note_text

NOTE_ID_PATTERN = re.compile(r"/(?:discovery/item|explore)/([0-9a-z]+)")
USER_POSTED_API = "/api/sns/web/v1/user_posted"
HUMAN_DWELL_MIN_MS = 2000
HUMAN_DWELL_MAX_MS = 5000
HUMAN_POST_ACTION_WAIT_MIN_MS = 600
HUMAN_POST_ACTION_WAIT_MAX_MS = 1200


@dataclass(slots=True)
class NoteCandidate:
    note_id: str
    url: str
    title: str
    source: str


@dataclass(slots=True)
class CrawlRunSummary:
    exit_code: int
    account_results: list[CrawlAccountResult]
    new_notes: list[RawNoteRecord]
    errors: list[str]


def _load_state(path: Path) -> dict[str, Any]:
    return read_json(path, default={"accounts": {}})


def _save_state(path: Path, payload: dict[str, Any]) -> None:
    write_json(path, payload)


def _ensure_state_bucket(state: dict[str, Any], account_name: str) -> dict[str, Any]:
    accounts = state.setdefault("accounts", {})
    bucket = accounts.setdefault(
        account_name,
        {"seen_note_ids": [], "last_run_at": None, "last_error": None},
    )
    bucket.setdefault("seen_note_ids", [])
    return bucket


def note_id_from_url(url: str) -> str:
    match = NOTE_ID_PATTERN.search(url)
    return match.group(1) if match else ""


def build_detail_url(site: str, note_id: str, xsec_token: str) -> str:
    query = urlencode(
        {
            "source": "webshare",
            "xhsshare": "pc_web",
            "xsec_token": xsec_token,
            "xsec_source": "pc_share",
        }
    )
    return f"https://www.{site}.com/discovery/item/{note_id}?{query}"


def is_security_restriction(page: Page) -> bool:
    title = page.title()
    return (
        "安全限制" in title
        or "瀹夊叏闄愬埗" in title
        or "website-login/error" in page.url
    )


def wait_for_initial_state(page: Page) -> None:
    page.wait_for_function("() => Boolean(window.__INITIAL_STATE__)", timeout=20000)


def close_blocking_popups(page: Page) -> None:
    selectors = [
        ".icon-btn-wrapper.close-button",
        "button.close-icon",
        ".close-icon",
    ]
    for _ in range(5):
        closed = False
        for selector in selectors:
            locator = page.locator(selector)
            count = min(locator.count(), 5)
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    if candidate.is_visible():
                        candidate.click(timeout=1000, force=True)
                        page.wait_for_timeout(400)
                        closed = True
                        break
                except Exception:
                    continue
            if closed:
                break
        if not closed:
            break


def random_human_dwell_ms() -> int:
    return random.randint(HUMAN_DWELL_MIN_MS, HUMAN_DWELL_MAX_MS)


def maybe_find_blank_click_point(page: Page) -> dict[str, int] | None:
    try:
        payload = page.evaluate(
            """
            () => {
              const points = [
                [24, 24],
                [window.innerWidth - 24, 24],
                [window.innerWidth - 36, Math.min(window.innerHeight - 36, 220)],
                [Math.floor(window.innerWidth * 0.92), Math.floor(window.innerHeight * 0.45)],
                [Math.floor(window.innerWidth * 0.08), Math.floor(window.innerHeight * 0.82)],
              ];
              const interactiveTags = new Set(["A", "BUTTON", "INPUT", "TEXTAREA", "SELECT", "LABEL", "IMG", "SVG", "PATH"]);
              for (const [x, y] of points) {
                const element = document.elementFromPoint(x, y);
                if (!element) continue;
                const tag = String(element.tagName || "").toUpperCase();
                if (tag === "BODY" || tag === "HTML") {
                  return { x, y };
                }
                if (interactiveTags.has(tag)) continue;
                const role = String(element.getAttribute?.("role") || "").toLowerCase();
                if (role === "button" || role === "link") continue;
                const style = window.getComputedStyle(element);
                if (style.cursor === "pointer") continue;
                return { x, y };
              }
              return null;
            }
            """
        )
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        return {"x": int(payload["x"]), "y": int(payload["y"])}
    except (KeyError, TypeError, ValueError):
        return None


def perform_light_human_actions(page: Page) -> None:
    page.wait_for_timeout(random_human_dwell_ms())
    try:
        page.mouse.move(
            random.randint(180, 420),
            random.randint(140, 260),
            steps=random.randint(8, 16),
        )
    except Exception:
        pass
    try:
        page.mouse.wheel(0, random.randint(260, 520))
    except Exception:
        pass
    page.wait_for_timeout(random.randint(HUMAN_POST_ACTION_WAIT_MIN_MS, HUMAN_POST_ACTION_WAIT_MAX_MS))
    if random.random() < 0.7:
        try:
            page.mouse.wheel(0, -random.randint(80, 180))
        except Exception:
            pass
        page.wait_for_timeout(
            random.randint(HUMAN_POST_ACTION_WAIT_MIN_MS, HUMAN_POST_ACTION_WAIT_MAX_MS)
        )
    if random.random() < 0.35:
        click_point = maybe_find_blank_click_point(page)
        if click_point is not None:
            try:
                page.mouse.click(
                    click_point["x"],
                    click_point["y"],
                    delay=random.randint(40, 120),
                )
                page.wait_for_timeout(
                    random.randint(
                        HUMAN_POST_ACTION_WAIT_MIN_MS,
                        HUMAN_POST_ACTION_WAIT_MAX_MS,
                    )
                )
            except Exception:
                pass
    page.wait_for_timeout(random.randint(500, 1000))


def normalize_candidate(
    site: str,
    source: str,
    note_id: str = "",
    url: str = "",
    title: str = "",
    xsec_token: str = "",
) -> NoteCandidate | None:
    final_url = url.strip()
    final_note_id = note_id.strip()
    if final_url and not final_note_id:
        final_note_id = note_id_from_url(final_url)
    if not final_url and final_note_id:
        if xsec_token.strip():
            final_url = build_detail_url(site, final_note_id, xsec_token.strip())
        else:
            final_url = f"https://www.{site}.com/explore/{final_note_id}"
    if not final_note_id or not final_url:
        return None
    return NoteCandidate(
        note_id=final_note_id,
        url=final_url,
        title=title.strip(),
        source=source,
    )


def read_initial_state_entries(page: Page) -> list[dict[str, str]]:
    try:
        return page.evaluate(
            """
            () => {
              const notes = window.__INITIAL_STATE__?.user?.notes;
              const groups = Array.isArray(notes) ? notes : notes?._rawValue;
              const group = Array.isArray(groups?.[0]) ? groups[0] : [];
              return group.map(item => {
                const card = item?.noteCard ?? {};
                return {
                  note_id: String(item?.id || item?.noteId || card?.noteId || ""),
                  xsec_token: String(item?.xsecToken || card?.xsecToken || ""),
                  title: String(card?.displayTitle || item?.displayTitle || "")
                };
              });
            }
            """
        )
    except Exception:
        return []


def extract_candidates_from_initial_state(page: Page, site: str) -> list[NoteCandidate]:
    payload = read_initial_state_entries(page)
    result: list[NoteCandidate] = []
    for item in payload:
        candidate = normalize_candidate(
            site=site,
            source="initial_state",
            note_id=str(item.get("note_id") or ""),
            title=str(item.get("title") or ""),
            xsec_token=str(item.get("xsec_token") or ""),
        )
        if candidate:
            result.append(candidate)
    return result


def read_response_entries(payloads: list[dict[str, Any]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for payload in payloads:
        data = payload.get("data") or {}
        notes = data.get("notes") or []
        if not isinstance(notes, list):
            continue
        for item in notes:
            if not isinstance(item, dict):
                continue
            result.append(
                {
                    "note_id": str(item.get("note_id") or item.get("noteId") or ""),
                    "xsec_token": str(item.get("xsec_token") or item.get("xsecToken") or ""),
                    "title": str(
                        item.get("display_title")
                        or item.get("displayTitle")
                        or item.get("title")
                        or ""
                    ),
                }
            )
    return result


def extract_candidates_from_responses(
    payloads: list[dict[str, Any]],
    site: str,
) -> list[NoteCandidate]:
    result: list[NoteCandidate] = []
    for item in read_response_entries(payloads):
        candidate = normalize_candidate(
            site=site,
            source="user_posted_response",
            note_id=item["note_id"],
            title=item["title"],
            xsec_token=item["xsec_token"],
        )
        if candidate:
            result.append(candidate)
    return result


def read_dom_entries(page: Page) -> list[dict[str, str]]:
    try:
        return page.evaluate(
            """
            () => Array.from(document.querySelectorAll("section.note-item a[href]")).map(a => ({
              href: String(a.getAttribute("href") || ""),
              text: String((a.innerText || a.textContent || "").trim())
            }))
            """
        )
    except Exception:
        return []


def extract_candidates_from_dom(page: Page, site: str) -> list[NoteCandidate]:
    payload = read_dom_entries(page)
    result: list[NoteCandidate] = []
    for item in payload:
        href = str(item.get("href") or "").strip()
        if not href:
            continue
        absolute = urljoin(page.url, href)
        candidate = normalize_candidate(
            site=site,
            source="dom_card",
            url=absolute,
            title=str(item.get("text") or ""),
        )
        if candidate:
            result.append(candidate)
    return result


def dedupe_candidates(candidates: list[NoteCandidate]) -> list[NoteCandidate]:
    result: list[NoteCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.note_id or candidate.url
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def logged_in_homepage_pause_seconds(cfg: WatchlistConfig) -> float:
    return cfg.inter_account_delay_sec + random.uniform(0.0, cfg.inter_account_delay_jitter_sec)


def write_debug_snapshot(
    page: Page,
    paths: AppPaths,
    account: AccountTarget,
    label: str,
    payload: dict[str, Any],
) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    target_dir = paths.xhs_debug_dir / account.safe_name
    target_dir.mkdir(parents=True, exist_ok=True)
    prefix = target_dir / f"{label}-{timestamp}"
    page.screenshot(path=str(prefix.with_suffix(".png")), full_page=True)
    prefix.with_suffix(".html").write_text(page.content(), encoding="utf-8")
    prefix.with_suffix(".json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return prefix


def remove_page_listener(page: Page, event: str, listener: Any) -> None:
    remove = getattr(page, "remove_listener", None)
    if callable(remove):
        try:
            remove(event, listener)
        except Exception:
            return


def collect_note_candidates(
    page: Page,
    paths: AppPaths,
    account: AccountTarget,
    debug_label: str,
) -> list[NoteCandidate]:
    response_payloads: list[dict[str, Any]] = []
    response_urls: list[str] = []

    def on_response(response: Any) -> None:
        if USER_POSTED_API not in response.url:
            return
        try:
            payload = response.json()
        except Exception:
            return
        if isinstance(payload, dict):
            response_payloads.append(payload)
            response_urls.append(response.url)

    page.on("response", on_response)
    try:
        page.goto(account.profile_url, wait_until="domcontentloaded", timeout=120000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeoutError:
            pass
        page.wait_for_timeout(1200)
        if is_security_restriction(page):
            raise RuntimeError(
                "Playwright hit Xiaohongshu security restriction. "
                "Try headed Chrome with a fresh login on a trusted network."
            )

        try:
            wait_for_initial_state(page)
        except PlaywrightTimeoutError:
            pass

        close_blocking_popups(page)
        perform_light_human_actions(page)
        close_blocking_popups(page)
        page.wait_for_timeout(800)

        state_entries = read_initial_state_entries(page)
        response_entries = read_response_entries(response_payloads)
        dom_entries = read_dom_entries(page)
        state_candidates = extract_candidates_from_initial_state(page, account.site)
        response_candidates = extract_candidates_from_responses(response_payloads, account.site)
        dom_candidates = extract_candidates_from_dom(page, account.site)
        merged = dedupe_candidates(state_candidates + response_candidates + dom_candidates)[
            : account.limit
        ]

        debug_payload = {
            "account_name": account.name,
            "profile_url": account.profile_url,
            "page_title": page.title(),
            "page_url": page.url,
            "state_entries": state_entries,
            "state_candidates": [asdict(item) for item in state_candidates],
            "response_entries": response_entries,
            "response_candidates": [asdict(item) for item in response_candidates],
            "dom_entries": dom_entries,
            "dom_candidates": [asdict(item) for item in dom_candidates],
            "captured_user_posted_urls": response_urls,
            "captured_user_posted_count": len(response_payloads),
        }
        if not merged:
            prefix = write_debug_snapshot(page, paths, account, debug_label, debug_payload)
            raise RuntimeError(
                "Could not resolve any real note links from the first screen. "
                f"Debug snapshot written to {prefix.parent}"
            )
        return merged
    finally:
        remove_page_listener(page, "response", on_response)


def has_persistent_login(paths: AppPaths) -> bool:
    if not paths.xhs_user_data_dir.exists():
        return False
    try:
        next(paths.xhs_user_data_dir.iterdir())
    except (StopIteration, OSError):
        return False
    return True


def build_cookie_header_for_url(context: BrowserContext, url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        return ""
    try:
        cookies = context.cookies([f"{parsed.scheme or 'https'}://{host}"])
    except Exception:
        try:
            cookies = context.cookies()
        except Exception:
            return ""
    pairs: list[str] = []
    for cookie in cookies:
        domain = str(cookie.get("domain") or "").lstrip(".").lower()
        if domain and host != domain and not host.endswith(f".{domain}"):
            continue
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        if not name:
            continue
        pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def get_reusable_page(context: BrowserContext) -> Page:
    pages = context.pages
    if pages:
        page = pages[0]
        for extra_page in pages[1:]:
            try:
                extra_page.close()
            except Exception:
                continue
        return page
    return context.new_page()


def minimize_browser_window(context: BrowserContext, page: Page) -> None:
    try:
        session = context.new_cdp_session(page)
        window = session.send("Browser.getWindowForTarget")
        session.send(
            "Browser.setWindowBounds",
            {
                "windowId": window["windowId"],
                "bounds": {"windowState": "minimized"},
            },
        )
    except Exception:
        return


def fetch_candidate_notes(
    cfg: WatchlistConfig,
    account: AccountTarget,
    candidates: list[NoteCandidate],
    login_cookie_header: str = "",
) -> tuple[list[RawNoteRecord], list[str]]:
    rows: list[RawNoteRecord] = []
    errors: list[str] = []
    fallback_used = 0
    with create_client() as anonymous_client:
        with create_client(cookie=login_cookie_header) as login_client:
            total = len(candidates)
            for index, candidate in enumerate(candidates, start=1):
                detail_fetch_mode = "anonymous"
                anonymous_detail_error: str | None = None
                used_login_fallback = False
                note: NoteText | None = None
                row: RawNoteRecord | None = None
                try:
                    note = fetch_note_text(anonymous_client, candidate.url)
                except NoteFetchError as exc:
                    anonymous_detail_error = exc.context.anonymous_detail_error
                    if (
                        exc.is_anonymous_access_restricted
                        and login_cookie_header
                        and cfg.detail_fallback_enabled
                        and fallback_used < cfg.detail_fallback_limit_per_account
                    ):
                        try:
                            note = fetch_note_text(login_client, candidate.url)
                            detail_fetch_mode = "login_cookie_fallback"
                            used_login_fallback = True
                            print(
                                f"[{account.name}] [{index}/{total}] fallback "
                                f"{anonymous_detail_error or exc.code} -> success",
                                file=sys.stderr,
                            )
                        except Exception as fallback_exc:
                            message = (
                                f"[{account.name}] [{index}/{total}] FAIL {candidate.url} "
                                f"{exc} | login fallback failed: {fallback_exc}"
                            )
                            print(message, file=sys.stderr)
                            errors.append(message)
                    else:
                        if exc.is_anonymous_access_restricted and not login_cookie_header:
                            suffix = " | login fallback unavailable: missing login cookie"
                        elif exc.is_anonymous_access_restricted and not cfg.detail_fallback_enabled:
                            suffix = " | login fallback disabled"
                        elif exc.is_anonymous_access_restricted:
                            suffix = " | login fallback skipped: budget exhausted"
                        else:
                            suffix = ""
                        message = f"[{account.name}] [{index}/{total}] FAIL {candidate.url} {exc}{suffix}"
                        print(message, file=sys.stderr)
                        errors.append(message)
                except Exception as exc:
                    message = f"[{account.name}] [{index}/{total}] FAIL {candidate.url} {exc}"
                    print(message, file=sys.stderr)
                    errors.append(message)

                if note is not None:
                    metadata = {"detail_fetch_mode": detail_fetch_mode}
                    if anonymous_detail_error:
                        metadata["anonymous_detail_error"] = anonymous_detail_error
                    row = RawNoteRecord(
                        **(
                            asdict(note)
                            | {
                                "platform": "xiaohongshu",
                                "account_name": account.name,
                                "profile_url": account.profile_url,
                                "fetched_at": now_iso(),
                                "metadata": metadata,
                            }
                        )
                    )
                    if cfg.exclude_old_posts and is_older_than_days(
                        row.publish_time,
                        days=cfg.max_post_age_days,
                        reference_time=row.fetched_at,
                    ):
                        print(
                            f"[{account.name}] [{index}/{total}] skip old note {row.note_id} "
                            f"older than {cfg.max_post_age_days} days",
                            file=sys.stderr,
                        )
                        row = None
                if row is not None:
                    if used_login_fallback:
                        fallback_used += 1
                    rows.append(row)
                    print(
                        f"[{account.name}] [{index}/{total}] {note.note_id} "
                        f"{note.title[:40]} ({candidate.source}, {detail_fetch_mode})",
                        file=sys.stderr,
                    )
                if cfg.detail_delay_sec > 0 and index < total:
                    time.sleep(cfg.detail_delay_sec)
    return rows, errors


def _new_context(
    playwright: Any,
    cfg: WatchlistConfig,
    user_data_dir: Path,
    *,
    headless_override: bool | None = None,
    start_minimized: bool = True,
) -> BrowserContext:
    headless = cfg.headless if headless_override is None else headless_override
    launch_kwargs: dict[str, Any] = {
        "headless": headless,
        "locale": "zh-CN",
        "viewport": {"width": 1440, "height": 1200},
    }
    if start_minimized and not headless:
        launch_kwargs["args"] = ["--start-minimized"]
    if cfg.browser_channel:
        launch_kwargs["channel"] = cfg.browser_channel
    return playwright.chromium.launch_persistent_context(
        str(user_data_dir),
        **launch_kwargs,
    )


def validate_saved_login(cfg: WatchlistConfig, paths: AppPaths) -> int:
    if not has_persistent_login(paths):
        print(
            f"ERROR: persistent Xiaohongshu user data not found: {paths.xhs_user_data_dir}",
            file=sys.stderr,
        )
        return 1

    first_account = cfg.accounts[0]
    with sync_playwright() as playwright:
        context = _new_context(
            playwright,
            cfg,
            paths.xhs_user_data_dir,
            headless_override=False,
        )
        page = get_reusable_page(context)
        minimize_browser_window(context, page)
        try:
            candidates = collect_note_candidates(
                page,
                paths,
                first_account,
                debug_label="login-validation-failed",
            )
            validation_candidates = candidates[: min(len(candidates), 3)]
            login_cookie_header = ""
            for candidate in validation_candidates:
                login_cookie_header = build_cookie_header_for_url(context, candidate.url)
                if login_cookie_header:
                    break
            if not login_cookie_header:
                print(
                    "ERROR: login validation failed. Could not extract login cookie from persistent context.",
                    file=sys.stderr,
                )
                return 1
            with create_client(cookie=login_cookie_header) as client:
                for candidate in validation_candidates:
                    try:
                        fetch_note_text(client, candidate.url)
                        print(
                            f"Login validation succeeded with account '{first_account.name}'.",
                            file=sys.stderr,
                        )
                        return 0
                    except Exception:
                        continue
            print(
                "ERROR: saved login state failed validation. No parseable note detail "
                "was fetched with login cookie HTTP.",
                file=sys.stderr,
            )
            return 1
        finally:
            context.close()


def login_and_validate(cfg: WatchlistConfig, paths: AppPaths) -> int:
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = _new_context(
            playwright,
            cfg,
            paths.xhs_user_data_dir,
            headless_override=False,
            start_minimized=False,
        )
        page = get_reusable_page(context)
        try:
            page.goto("https://www.xiaohongshu.com/", wait_until="domcontentloaded", timeout=120000)
            print(
                "Finish Xiaohongshu login in the opened browser, then press Enter here "
                "to keep the persistent Chrome user data directory and run validation.",
                file=sys.stderr,
            )
            input()
        finally:
            context.close()
    print(f"Persistent user data directory: {paths.xhs_user_data_dir}", file=sys.stderr)
    return validate_saved_login(cfg, paths)


def run_once(cfg: WatchlistConfig, paths: AppPaths) -> CrawlRunSummary:
    if not has_persistent_login(paths):
        message = (
            f"missing persistent Xiaohongshu login at {paths.xhs_user_data_dir}. "
            "Run login first."
        )
        print(f"ERROR: {message}", file=sys.stderr)
        return CrawlRunSummary(exit_code=1, account_results=[], new_notes=[], errors=[message])

    state = _load_state(paths.xhs_state_path)
    exit_code = 0
    account_results: list[CrawlAccountResult] = []
    new_notes: list[RawNoteRecord] = []
    errors: list[str] = []

    with sync_playwright() as playwright:
        context = _new_context(playwright, cfg, paths.xhs_user_data_dir)
        page = get_reusable_page(context)
        if not cfg.headless:
            minimize_browser_window(context, page)
        try:
            for index, account in enumerate(cfg.accounts):
                run_at = now_iso()
                if index > 0:
                    pause_sec = logged_in_homepage_pause_seconds(cfg)
                    print(
                        f"[wait] sleep {pause_sec:.1f}s before opening next logged-in profile page",
                        file=sys.stderr,
                    )
                    time.sleep(pause_sec)
                bucket = _ensure_state_bucket(state, account.name)
                seen_note_ids = set(bucket.get("seen_note_ids", []))
                try:
                    candidates = collect_note_candidates(
                        page,
                        paths,
                        account,
                        debug_label="run-once-failed",
                    )
                    fresh_candidates = [
                        item for item in candidates if item.note_id not in seen_note_ids
                    ]
                    login_cookie_header = ""
                    if fresh_candidates:
                        login_cookie_header = build_cookie_header_for_url(
                            context,
                            fresh_candidates[0].url,
                        )
                    rows, row_errors = fetch_candidate_notes(
                        cfg,
                        account,
                        fresh_candidates,
                        login_cookie_header=login_cookie_header,
                    )
                    for row in rows:
                        seen_note_ids.add(row.note_id)
                    bucket["seen_note_ids"] = list(seen_note_ids)[-5000:]
                    bucket["last_run_at"] = run_at
                    bucket["last_error"] = "; ".join(row_errors)[:2000] if row_errors else None
                    if row_errors:
                        exit_code = 1
                        errors.extend(row_errors)
                    result = CrawlAccountResult(
                        platform="xiaohongshu",
                        account_name=account.name,
                        profile_url=account.profile_url,
                        run_at=run_at,
                        status="success",
                        candidate_count=len(candidates),
                        new_note_count=len(rows),
                        fetched_note_ids=[row.note_id for row in rows],
                        error=bucket["last_error"],
                    )
                    account_results.append(result)
                    new_notes.extend(rows)
                    print(
                        f"[{account.name}] resolved={len(candidates)} new={len(rows)} "
                        f"seen={len(bucket['seen_note_ids'])}",
                        file=sys.stderr,
                    )
                except Exception as exc:
                    exit_code = 1
                    error_message = str(exc)
                    bucket["last_run_at"] = run_at
                    bucket["last_error"] = error_message
                    errors.append(f"[{account.name}] {error_message}")
                    account_results.append(
                        CrawlAccountResult(
                            platform="xiaohongshu",
                            account_name=account.name,
                            profile_url=account.profile_url,
                            run_at=run_at,
                            status="failed",
                            error=error_message,
                        )
                    )
                    print(f"[{account.name}] ERROR {exc}", file=sys.stderr)
        finally:
            _save_state(paths.xhs_state_path, state)
            context.close()
    return CrawlRunSummary(
        exit_code=exit_code,
        account_results=account_results,
        new_notes=new_notes,
        errors=errors,
    )
