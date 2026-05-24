"""
SpareRoom NYC scraper.
spareroom.com/rooms-for-rent/nyc — plain HTML, no Cloudflare.

Free tier strategy: scrape all visible listings. Skip the $14/wk "Early Bird"
upsell — for an automated agent that hits new listings on day 1, 7-day-old
ads are fine.
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

BASE = "https://www.spareroom.com"
SEARCH_URL = f"{BASE}/rooms-for-rent/nyc"

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

MAX_PAGES = 3   # ~30 listings/page × 3 pages = ~90 per run; plenty for 30-min cadence


def _headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _make_id(url: str) -> str:
    m = re.search(r"/(\d{6,})", url)
    return "sr_" + (m.group(1) if m else hashlib.md5(url.encode()).hexdigest()[:12])


def _parse_price(text: str) -> int | None:
    """SpareRoom shows prices like '$1,800 pcm' (per calendar month) or '$415 pw' (per week)."""
    m = re.search(r"\$\s*([\d,]+)\s*(pcm|pw|monthly|weekly|/mo|/wk)?", text, re.IGNORECASE)
    if not m:
        return None
    try:
        amount = int(m.group(1).replace(",", ""))
    except ValueError:
        return None
    unit = (m.group(2) or "").lower()
    if unit in ("pw", "weekly", "/wk"):
        return int(amount * 52 / 12)   # convert weekly → monthly
    return amount


def _parse_listing_card(card) -> Listing | None:
    """Parse one listing tile from the search results page."""
    a = card.select_one("a[href*='/flatshare/']") or card.find("a", href=True)
    if not a:
        return None

    href = a.get("href", "")
    if not href:
        return None
    url = href if href.startswith("http") else f"{BASE}{href}"

    card_text = card.get_text(" ", strip=True)

    # Skip listings already marked "Deposit taken"
    if re.search(r"deposit taken|let agreed|no longer available", card_text, re.IGNORECASE):
        return None

    # Title — usually in an h2 or h3
    title_el = card.find(["h2", "h3"]) or a
    title = title_el.get_text(" ", strip=True)[:160] if title_el else "SpareRoom NYC"

    price = _parse_price(card_text)

    # Neighborhood often appears as text near "in [neighborhood]"
    hood = None
    hood_match = re.search(r"\bin\s+([A-Z][A-Za-z\- ]{2,30}?)(?:,|\s+\$|\s+pcm|$)", card_text)
    if hood_match:
        hood = hood_match.group(1).strip()

    # Detect furnished / shared signals
    text_low = card_text.lower()
    furnished = None
    if "furnished" in text_low:
        furnished = True
    elif "unfurnished" in text_low:
        furnished = False

    return Listing(
        id=_make_id(url),
        source="spareroom",
        url=url,
        title=title,
        price=price,
        neighborhood=hood,
        furnished=furnished,
        body_snippet=card_text[:300],
    )


def _fetch_page(page: int = 1) -> list[Listing]:
    params = {"offset": (page - 1) * 30} if page > 1 else {}
    try:
        resp = requests.get(SEARCH_URL, params=params, headers=_headers(), timeout=20)
        if resp.status_code != 200:
            logger.warning(f"SpareRoom page {page}: {resp.status_code}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        # SpareRoom listings tend to be in <li class="listing-result"> or similar
        cards = soup.select("li.listing-result, article.listing, li[class*='listing']")
        if not cards:
            # Fallback: look for any container with an /flatshare/ link
            cards = []
            for a in soup.select("a[href*='/flatshare/']"):
                parent = a.find_parent(["li", "article", "div"])
                if parent and parent not in cards:
                    cards.append(parent)

        out: list[Listing] = []
        seen_urls: set[str] = set()
        for card in cards:
            listing = _parse_listing_card(card)
            if listing and listing.url not in seen_urls:
                seen_urls.add(listing.url)
                out.append(listing)
        return out

    except Exception as exc:
        logger.warning(f"SpareRoom page {page} failed: {exc}")
        return []


def fetch() -> list[Listing]:
    """Scrape SpareRoom NYC across the first few pages."""
    all_listings: list[Listing] = []
    for page in range(1, MAX_PAGES + 1):
        page_results = _fetch_page(page)
        if not page_results:
            break
        all_listings.extend(page_results)
        time.sleep(random.uniform(2.0, 4.0))

    # Dedup by URL across pages
    seen: set[str] = set()
    unique = []
    for l in all_listings:
        if l.url not in seen:
            seen.add(l.url)
            unique.append(l)

    logger.info(f"[SpareRoom] {len(unique)} unique listings across {MAX_PAGES} pages")
    return unique


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    results = fetch()
    print(f"\n=== {len(results)} listings ===")
    for r in results[:5]:
        print(f"{r.id} | ${r.price} | {r.title[:60]} | {r.url}")
