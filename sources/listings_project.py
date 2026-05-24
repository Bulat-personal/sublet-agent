"""
Listings Project scraper.
listingsproject.com — curated NYC sublets, refreshed weekly (digest goes out Wed).

Strategy: scrape the public listing index, filter to NYC.
"""

from __future__ import annotations

import re
import hashlib
import logging
import random
import time

import requests
from bs4 import BeautifulSoup

from models import Listing

logger = logging.getLogger(__name__)

INDEX_URL = "https://www.listingsproject.com/listings/all"
NYC_URL   = "https://www.listingsproject.com/listings/housing/new-york"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def _headers() -> dict:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _make_id(url: str) -> str:
    m = re.search(r"/listings/[^/]+/[^/]+/(\d+)", url)
    return "lp_" + (m.group(1) if m else hashlib.md5(url.encode()).hexdigest()[:12])


def _parse_price(text: str) -> int | None:
    """Extract a price from a string like '$2,400 / month' or '$2400'."""
    m = re.search(r"\$\s*([\d,]+)", text)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def fetch() -> list[Listing]:
    """Scrape NYC housing listings from Listings Project."""
    try:
        resp = requests.get(NYC_URL, headers=_headers(), timeout=20)
        if resp.status_code != 200:
            logger.warning(f"LP fetch {resp.status_code}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        out: list[Listing] = []

        # Listings Project uses card-style layout. Selectors are fragile — wrap loosely.
        # Cards typically have class "listing-card" or are in a <ul> with listing items.
        candidates = soup.select("a[href*='/listings/']")
        seen_urls: set[str] = set()

        for a in candidates:
            href = a.get("href", "")
            # Only listing detail URLs: /listings/housing/.../12345
            if not re.search(r"/listings/[^/]+/[^/]+/\d+", href):
                continue

            url = href if href.startswith("http") else f"https://www.listingsproject.com{href}"
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Grab surrounding card text
            card = a.find_parent(["li", "div", "article"]) or a
            card_text = card.get_text(" ", strip=True)[:500]

            title = (a.get_text(strip=True) or card_text[:80]).strip()
            price = _parse_price(card_text)

            out.append(Listing(
                id=_make_id(url),
                source="listings_project",
                url=url,
                title=title or "Listings Project — NYC",
                price=price,
                neighborhood=None,
                body_snippet=card_text[:300],
            ))

        logger.info(f"[LP] {len(out)} NYC listings")
        return out

    except Exception as exc:
        logger.warning(f"LP fetch failed: {exc}")
        return []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    results = fetch()
    print(f"\n=== {len(results)} listings ===")
    for r in results[:5]:
        print(f"{r.id} | ${r.price} | {r.title[:60]} | {r.url}")
