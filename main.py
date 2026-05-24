"""
Sublet-agent orchestrator.

Single run: scrape each enabled source → filter → dedup → notify → persist.
GitHub Actions cron handles the scheduling (no `while True` loop needed).

Adapted from rental-agent/main.py.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pytz

import config
import db
from models import Listing
from filter import filter_listings
from notifier import notify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

ET = pytz.timezone("America/New_York")


# Import sources lazily so missing optional deps (praw, playwright) don't crash startup
SOURCE_FETCHERS = {
    "craigslist":       ("sources.craigslist",       "fetch_all"),
    "listings_project": ("sources.listings_project", "fetch"),
    "spareroom":        ("sources.spareroom",        "fetch"),
    "reddit":           ("sources.reddit",           "fetch"),
    # Phase 2
    "ohana":            ("sources.ohana",            "fetch"),
    "leasebreak":       ("sources.leasebreak",       "fetch"),
    # Phase 4 (opt-in)
    "facebook":         ("sources.facebook",         "fetch"),
}


def _run_source(name: str) -> list[Listing]:
    """Import + run a source fetcher. Failures are logged, never raised."""
    if name not in SOURCE_FETCHERS:
        logger.warning(f"Unknown source: {name}")
        return []
    module_path, func_name = SOURCE_FETCHERS[name]
    try:
        module = __import__(module_path, fromlist=[func_name])
        fetcher = getattr(module, func_name)
        return fetcher() or []
    except Exception as exc:
        logger.error(f"Source '{name}' crashed: {exc}", exc_info=True)
        return []


def run():
    now = datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")
    logger.info("=" * 60)
    logger.info(f"Sublet-agent run — {now}")
    logger.info("=" * 60)

    # 1. Fetch from every enabled source
    sources = list(config.ENABLED_SOURCES)
    if config.ENABLE_FACEBOOK and "facebook" not in sources:
        sources.append("facebook")

    all_listings: list[Listing] = []
    for src in sources:
        results = _run_source(src)
        logger.info(f"  {src}: {len(results)} listings")
        all_listings.extend(results)

    logger.info(f"Total scraped: {len(all_listings)}")
    if not all_listings:
        logger.info("Nothing scraped — exiting")
        return

    # 2. Filter
    filtered = filter_listings(all_listings)
    if not filtered:
        logger.info("Nothing passed filters — exiting")
        return

    # 3. Dedup against state DB
    new_listings = [l for l in filtered if not db.is_seen(l.id)]
    logger.info(f"After dedup: {len(new_listings)} truly new listings")
    if not new_listings:
        logger.info("All filtered listings already seen — no notification")
        return

    # 4. Notify
    notified_ok = notify(new_listings)

    # 5. Mark seen (only if notification actually went out — so we retry on failure)
    if notified_ok:
        for l in new_listings:
            db.mark_seen(l.id, l.url, l.source)
        logger.info(f"Marked {len(new_listings)} listings as seen")
    else:
        logger.warning("Notification failed — NOT marking as seen so we'll retry next run")

    # 6. Housekeeping
    db.purge_old(days=45)
    logger.info(f"DB size: {db.count()} entries")
    logger.info("Run complete\n")


def main():
    db.init_db()
    logger.info("🏙️  NYC Sublet Agent starting")
    logger.info(f"   Sources       : {', '.join(config.ENABLED_SOURCES)}")
    logger.info(f"   Max rent      : ${config.MAX_RENT:,}/mo")
    logger.info(f"   Move-in window: {config.EARLIEST_MOVE_IN} → {config.LATEST_MOVE_IN}")
    logger.info(f"   Facebook opt-in: {config.ENABLE_FACEBOOK}")
    logger.info("")
    run()


if __name__ == "__main__":
    main()
