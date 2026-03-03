#!/usr/bin/env python3
"""Fetch Twitter/X bookmarks using twikit (internal GraphQL API).

Usage:
    # First run — extract cookies from your Chrome browser session:
    python3 scripts/fetch_twitter_bookmarks.py --extract-cookies

    # Or manually paste cookies from browser devtools:
    python3 scripts/fetch_twitter_bookmarks.py --paste-cookies

    # Subsequent runs — uses saved cookies:
    python3 scripts/fetch_twitter_bookmarks.py --save

    # Fetch only N most recent:
    python3 scripts/fetch_twitter_bookmarks.py --limit 50 --save

    # Search bookmarks by keyword:
    python3 scripts/fetch_twitter_bookmarks.py --search "knowledge management"

Cookies are saved to ~/.config/twikit/cookies.json
Bookmarks are saved to data/twitter_bookmarks.json
"""

import argparse
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

# Use the petrarca venv
VENV_SITE = str(Path(__file__).parent.parent / ".venv/lib/python3.12/site-packages")
if os.path.exists(VENV_SITE):
    sys.path.insert(0, VENV_SITE)

from twikit import Client, TooManyRequests, Unauthorized

COOKIES_DIR = Path.home() / ".config" / "twikit"
COOKIES_PATH = COOKIES_DIR / "cookies.json"
DATA_DIR = Path(__file__).parent.parent / "data"


def extract_cookies_from_browser() -> dict:
    """Extract Twitter cookies from Chrome using browser-cookie3."""
    try:
        import browser_cookie3
    except ImportError:
        print("browser-cookie3 not installed. Run:", file=sys.stderr)
        print("  .venv/bin/pip install browser-cookie3", file=sys.stderr)
        sys.exit(1)

    print("Extracting cookies from Chrome...", file=sys.stderr)
    print("(You may see a macOS Keychain prompt — allow access)", file=sys.stderr)
    try:
        cj = browser_cookie3.chrome(domain_name=".x.com")
    except Exception:
        # Try twitter.com as fallback
        cj = browser_cookie3.chrome(domain_name=".twitter.com")

    cookies = {}
    for cookie in cj:
        cookies[cookie.name] = cookie.value

    if "auth_token" not in cookies or "ct0" not in cookies:
        print("ERROR: Could not find auth_token/ct0 cookies.", file=sys.stderr)
        print("Make sure you're logged into Twitter/X in Chrome.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(cookies)} cookies (auth_token, ct0 present)", file=sys.stderr)
    return cookies


def paste_cookies() -> dict:
    """Manually paste cookie values from browser devtools."""
    print("Go to x.com in your browser, open DevTools > Application > Cookies", file=sys.stderr)
    print("Copy the values for these cookies:\n", file=sys.stderr)

    auth_token = input("auth_token: ").strip()
    ct0 = input("ct0: ").strip()

    if not auth_token or not ct0:
        print("Both auth_token and ct0 are required.", file=sys.stderr)
        sys.exit(1)

    return {"auth_token": auth_token, "ct0": ct0}


async def get_client(extract: bool = False, paste: bool = False) -> Client:
    client = Client("en-US")
    COOKIES_DIR.mkdir(parents=True, exist_ok=True)

    if extract:
        cookies = extract_cookies_from_browser()
        client.set_cookies(cookies)
        client.save_cookies(str(COOKIES_PATH))
        print(f"Cookies saved to {COOKIES_PATH}", file=sys.stderr)
    elif paste:
        cookies = paste_cookies()
        client.set_cookies(cookies)
        client.save_cookies(str(COOKIES_PATH))
        print(f"Cookies saved to {COOKIES_PATH}", file=sys.stderr)
    elif COOKIES_PATH.exists():
        client.load_cookies(str(COOKIES_PATH))
    else:
        print(f"No cookies found at {COOKIES_PATH}", file=sys.stderr)
        print("Run with --extract-cookies or --paste-cookies first", file=sys.stderr)
        sys.exit(1)

    # Light validation — try fetching 1 bookmark to confirm cookies work
    if not extract and not paste:
        try:
            test = await client.get_bookmarks(count=1)
            print("Authenticated (cookies valid)", file=sys.stderr)
        except Unauthorized:
            print("Cookies expired. Re-run with --extract-cookies or --paste-cookies", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Warning: validation returned {e}, proceeding anyway", file=sys.stderr)
    else:
        print("Cookies set, will validate on first fetch", file=sys.stderr)

    return client


def tweet_to_dict(tweet) -> dict:
    author = tweet.user
    media = []
    for m in (tweet.media or []):
        item = {"type": m.type, "url": m.media_url}
        if m.type == "video" and hasattr(m, "streams") and m.streams:
            best = max(m.streams, key=lambda s: s.bitrate or 0)
            item["video_url"] = best.url
        media.append(item)

    result = {
        "id": tweet.id,
        "text": tweet.full_text,
        "created_at": tweet.created_at,
        "url": f"https://twitter.com/{author.screen_name}/status/{tweet.id}",
        "author_username": author.screen_name,
        "author_name": author.name,
        "media": media,
        "urls": tweet.urls or [],
        "hashtags": tweet.hashtags or [],
        "likes": tweet.favorite_count,
        "retweets": tweet.retweet_count,
        "lang": tweet.lang,
    }

    if tweet.quote:
        q = tweet.quote
        result["quoted_tweet"] = {
            "id": q.id,
            "text": q.full_text,
            "author_username": q.user.screen_name if q.user else None,
            "url": f"https://twitter.com/{q.user.screen_name}/status/{q.id}" if q.user else None,
        }

    return result


async def fetch_bookmarks(client: Client, limit: int | None = None) -> list[dict]:
    all_tweets = []
    seen_ids = set()
    prev_count = -1
    stall_count = 0

    page = await client.get_bookmarks(count=20)

    while True:
        new_in_page = 0
        for tweet in page:
            if tweet.id in seen_ids:
                continue
            seen_ids.add(tweet.id)
            all_tweets.append(tweet_to_dict(tweet))
            new_in_page += 1
            if limit and len(all_tweets) >= limit:
                return all_tweets

        # Detect stall (empty pages or no new tweets)
        if new_in_page == 0:
            stall_count += 1
            if stall_count >= 3:
                print(f"  ...no new tweets for 3 pages, stopping", file=sys.stderr)
                break
        else:
            stall_count = 0

        if page.next_cursor is None:
            break

        print(f"  ...fetched {len(all_tweets)} so far", file=sys.stderr)
        await asyncio.sleep(random.uniform(1.5, 3.0))

        try:
            page = await page.next()
        except TooManyRequests as e:
            reset = e.rate_limit_reset or (time.time() + 60)
            wait = reset - time.time()
            print(f"  Rate limited, sleeping {wait:.0f}s", file=sys.stderr)
            await asyncio.sleep(max(wait, 1))
            page = await page.next()

    return all_tweets


def search_bookmarks(bookmarks: list[dict], query: str) -> list[dict]:
    terms = query.lower().split()
    results = []
    for bm in bookmarks:
        text = f"{bm['text']} {bm['author_username']} {bm['author_name']}".lower()
        if all(t in text for t in terms):
            results.append(bm)
    return results


async def main():
    parser = argparse.ArgumentParser(description="Fetch Twitter/X bookmarks")
    parser.add_argument("--extract-cookies", action="store_true",
                        help="Extract cookies from Chrome automatically")
    parser.add_argument("--paste-cookies", action="store_true",
                        help="Manually paste auth_token and ct0 from browser devtools")
    parser.add_argument("--limit", type=int, help="Max bookmarks to fetch")
    parser.add_argument("--search", type=str, help="Filter bookmarks by keyword")
    parser.add_argument("--format", choices=["json", "jsonl"], default="json")
    parser.add_argument("--output", type=str, help="Output file path (default: stdout)")
    parser.add_argument("--save", action="store_true",
                        help="Save to data/twitter_bookmarks.json")
    args = parser.parse_args()

    client = await get_client(
        extract=args.extract_cookies,
        paste=args.paste_cookies,
    )

    bookmarks = await fetch_bookmarks(client, limit=args.limit)
    print(f"Fetched {len(bookmarks)} bookmarks", file=sys.stderr)

    if args.search:
        bookmarks = search_bookmarks(bookmarks, args.search)
        print(f"  {len(bookmarks)} match '{args.search}'", file=sys.stderr)

    # Determine output
    if args.save:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DATA_DIR / f"twitter_bookmarks.{args.format}"
        args.output = str(out_path)

    if args.format == "jsonl":
        lines = "\n".join(json.dumps(bm, ensure_ascii=False) for bm in bookmarks)
        output = lines
    else:
        output = json.dumps(bookmarks, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    asyncio.run(main())
