"""
Reddit sublet scraper — public RSS feeds (no API key required).

Reddit's per-subreddit RSS feeds (/new/.rss) are public and don't require
authentication. We use them instead of PRAW so we don't have to fight
Reddit's developer app creation flow.

Trade-offs vs PRAW:
  - No fine-grained rate limit info (we just go slow — 1.5s between subs)
  - Slightly less metadata per post (no comment counts etc) — we don't need it
"""

from __future__ import annotations

import re
import time
import logging
from datetime import datetime, timezone

import requests
import feedparser

import config
from models import Listing

logger = logging.getLogger(__name__)

USER_AGENT = "sublet-agent/0.1 (RSS reader)"

FEED_TEMPLATE = "https://www.reddit.com/r/{sub}/new/.rss"


def _make_id(entry_id: str) -> str:
    # Reddit entry IDs look like "t3_abc123" or full URLs — extract a stable suffix
    m = re.search(r"t3_(\w+)", entry_id)
    if m:
        return f"rd_{m.group(1)}"
    m = re.search(r"/comments/(\w+)/", entry_id)
    if m:
        return f"rd_{m.group(1)}"
    return f"rd_{abs(hash(entry_id)) % 10**10}"


def _parse_price(text: str) -> int | None:
    m = re.search(r"\$\s*(\d[\d,]{2,5})\s*(?:/?\s*mo|per\s+month|monthly)?", text, re.IGNORECASE)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_duration_months(text: str) -> int | None:
    m = re.search(r"(\d+)\s*(?:-|to|–)?\s*month", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def _matches_sublet_keyword(text: str) -> bool:
    text_low = text.lower()
    return any(kw in text_low for kw in config.REDDIT_SUBLET_KEYWORDS)


def _strip_html(html: str) -> str:
    """Very lightweight HTML → text. RSS descriptions are HTML-wrapped."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = (text.replace("&amp;", "&").replace("&lt;", "<")
                .replace("&gt;", ">").replace("&quot;", '"')
                .replace("&#39;", "'").replace("&nbsp;", " "))
    return re.sub(r"\s+", " ", text).strip()


def _fetch_subreddit(sub_name: str) -> list[Listing]:
    url = FEED_TEMPLATE.format(sub=sub_name)
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"r/{sub_name} RSS: HTTP {resp.status_code}")
            return []

        feed = feedparser.parse(resp.text)
        out: list[Listing] = []

        for entry in feed.entries[:50]:
            entry_id  = entry.get("id", "") or entry.get("link", "")
            title     = (entry.get("title") or "")[:160]
            link      = entry.get("link", "")
            body_html = entry.get("summary", "") or entry.get("description", "")
            body      = _strip_html(body_html)

            full_text = title + " " + body

            # On r/AskNYC most posts aren't sublets — filter hard.
            # On the others, also require keyword match to skip pure questions/news.
            if not _matches_sublet_keyword(full_text):
                continue

            posted_at = None
            if entry.get("published_parsed"):
                posted_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()

            out.append(Listing(
                id=_make_id(entry_id),
                source=f"reddit_{sub_name}",
                url=link,
                title=title,
                price=_parse_price(full_text),
                duration_months=_parse_duration_months(full_text),
                body_snippet=body[:300],
                posted_at=posted_at,
            ))

        return out

    except Exception as exc:
        logger.warning(f"r/{sub_name} RSS failed: {exc}")
        return []


def fetch() -> list[Listing]:
    """Pull recent sublet posts from configured subreddits via public RSS."""
    out: list[Listing] = []
    for sub_name in config.REDDIT_SUBREDDITS:
        results = _fetch_subreddit(sub_name)
        logger.info(f"  r/{sub_name}: {len(results)} sublet-relevant posts")
        out.extend(results)
        time.sleep(1.5)  # polite delay between feeds

    logger.info(f"[Reddit] {len(out)} total sublet posts")
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    results = fetch()
    print(f"\n=== {len(results)} posts ===")
    for r in results[:5]:
        print(f"{r.id} | ${r.price} | {r.title[:60]} | {r.url}")
