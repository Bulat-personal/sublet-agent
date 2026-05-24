"""
Craigslist NYC sublets scraper.

Sublet-focused subset of rental-agent's scraper:
  - Only the `sub` (sublets/temporary) and `roo` (rooms) categories
  - Skips the `apa` (apartments) category — handled by rental-agent
  - Extracts sublet-specific fields: duration_months, move_in/out dates
"""

from __future__ import annotations

import re
import time
import random
import hashlib
import logging
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup

import config
from models import Listing

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]

CATEGORIES = {
    "sublets": "sub",
    "rooms":   "roo",
}

CL_SITES = {
    "nyc": "https://newyork.craigslist.org",
    "nj":  "https://newjersey.craigslist.org",
}

MAX_RESULTS_PER_SEARCH = 30


def _headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _fetch_search(site_url: str, category: str, query: str) -> list[dict]:
    """Fetch a CL search page; return [{link, title, price, location}, ...]."""
    url = f"{site_url}/search/{category}"
    params = {"max_price": config.MAX_RENT, "query": query, "availabilityMode": 0}
    try:
        resp = requests.get(url, params=params, headers=_headers(), timeout=15)
        if resp.status_code != 200:
            logger.warning(f"CL search {resp.status_code} [{category}] '{query}'")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        out = []
        for li in soup.select("li.cl-static-search-result"):
            a = li.find("a")
            if not a or not a.get("href"):
                continue
            title_el = li.find("div", class_="title")
            price_el = li.find("div", class_="price")
            loc_el   = li.find("div", class_="location")

            price = None
            if price_el:
                m = re.search(r"[\d,]+", price_el.text)
                if m:
                    price = int(m.group().replace(",", ""))

            out.append({
                "link": a["href"],
                "title": li.get("title") or (title_el.text.strip() if title_el else "No title"),
                "price": price,
                "location": loc_el.text.strip() if loc_el else "",
            })
        return out
    except Exception as exc:
        logger.warning(f"CL search failed [{category}] '{query}': {exc}")
        return []


def _scrape_detail(url: str) -> dict:
    """Hit a CL listing detail page; extract sublet-relevant fields."""
    try:
        time.sleep(random.uniform(1.5, 3.0))
        resp = requests.get(url, headers=_headers(), timeout=15)
        if resp.status_code != 200:
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")
        d: dict = {}

        price_tag = soup.find("span", class_="price")
        if price_tag:
            try:
                d["price"] = int(re.sub(r"[^\d]", "", price_tag.text))
            except ValueError:
                pass

        for span in soup.find_all("span", class_="shared-line-bubble"):
            txt = span.text.strip().lower()
            if "br" in txt:
                m = re.search(r"(\d+)br", txt)
                if m:
                    d["bedrooms"] = int(m.group(1))

        body = soup.find("section", id="postingbody")
        body_text = body.get_text(" ", strip=True) if body else ""
        body_low = body_text.lower()

        d["description"] = body_text[:300]
        d["furnished"]   = any(w in body_low for w in [
            "furnished", "furniture included", "fully furnished", "comes furnished",
        ])

        # Sublet duration — look for "N months" or "N month"
        dur = re.search(r"(\d+)\s*[-–]?\s*month", body_low)
        if dur:
            d["duration_months"] = int(dur.group(1))

        # Move-in/move-out from CL's housing_movein/housing_moveout spans
        for cls, key in [("housing_movein_now", "move_in_date"), ("housing_moveout", "move_out_date")]:
            el = soup.find("span", class_=cls)
            if el:
                d[key] = _parse_date_phrase(el.text.strip())

        dt = soup.find("time", class_="date timeago")
        if dt:
            d["posted_at"] = dt.get("datetime", "")

        return d
    except Exception as exc:
        logger.warning(f"CL detail failed [{url}]: {exc}")
        return {}


def _parse_date_phrase(s: str) -> str | None:
    """CL phrases like 'available 2026-06-15' or 'jun 15' → ISO date string."""
    s = s.lower().strip()

    # Already ISO?
    m = re.search(r"\d{4}-\d{2}-\d{2}", s)
    if m:
        return m.group()

    # "available june 15" or "jun 15"
    months = {m: i for i, m in enumerate(
        ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"], start=1)}
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+(\d{1,2})", s)
    if m:
        mo, day = months[m.group(1)[:3]], int(m.group(2))
        # Assume current or next year
        today = date.today()
        year = today.year if mo >= today.month else today.year + 1
        try:
            return date(year, mo, day).isoformat()
        except ValueError:
            return None
    return None


def _make_id(url: str) -> str:
    m = re.search(r"/(\d{10})\.html", url)
    return "cl_" + (m.group(1) if m else hashlib.md5(url.encode()).hexdigest()[:12])


def fetch(region: str = "nyc") -> list[Listing]:
    """Public entry point — fetch all NYC sublet/room listings from Craigslist."""
    seen_urls: set[str] = set()
    listings: list[Listing] = []

    groups = config.CL_SEARCH_GROUPS.get(region, [])
    site_url = CL_SITES.get(region, CL_SITES["nyc"])

    for query in groups:
        for cat_name, cat_code in CATEGORIES.items():
            entries = _fetch_search(site_url, cat_code, query)
            logger.info(f"[CL {region}] {cat_name} '{query[:40]}' → {len(entries)}")

            for entry in entries[:MAX_RESULTS_PER_SEARCH]:
                url = entry.get("link", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                detail = _scrape_detail(url)
                price  = detail.get("price") or entry.get("price")

                listings.append(Listing(
                    id=_make_id(url),
                    source=f"craigslist_{region}",
                    url=url,
                    title=entry.get("title", "No title"),
                    price=price,
                    neighborhood=entry.get("location") or None,
                    duration_months=detail.get("duration_months"),
                    move_in_date=detail.get("move_in_date"),
                    move_out_date=detail.get("move_out_date"),
                    furnished=detail.get("furnished"),
                    bedrooms=detail.get("bedrooms"),
                    body_snippet=detail.get("description", ""),
                    posted_at=detail.get("posted_at"),
                ))

            time.sleep(random.uniform(3.0, 6.0))

    logger.info(f"[CL {region}] total: {len(listings)} listings")
    return listings


def fetch_all() -> list[Listing]:
    """Fetch from all configured regions."""
    out: list[Listing] = []
    for region in config.CL_SEARCH_GROUPS:
        out.extend(fetch(region))
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    results = fetch_all()
    print(f"\n=== {len(results)} listings ===")
    for r in results[:5]:
        print(f"{r.id} | ${r.price} | {r.title[:60]} | {r.url}")
