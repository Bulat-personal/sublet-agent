"""
Filter sublet listings against user criteria.

Three layers:
  - HARD filters → reject (over budget, wrong area)
  - SOFT filters → flag via tags but keep (duration/move-in unknown)
  - SCAM filters → reject (suspiciously cheap, suspicious text patterns)
"""

from __future__ import annotations

import re
import logging
from datetime import date

import config
from models import Listing

logger = logging.getLogger(__name__)


SCAM_PATTERNS = [
    r"wire (?:money|transfer|funds)",
    r"western union",
    r"moneygram",
    r"send (?:me )?(?:the )?(?:money|payment|deposit) (?:via|through|by)",
    r"god ?bless",                      # very common scam tell
    r"out of (?:the )?country",
    r"out of state and",
    r"missionary",
    r"god[' ]?s? will",
]
_SCAM_RE = re.compile("|".join(SCAM_PATTERNS), re.IGNORECASE)


def _matches_neighborhood(text: str) -> str | None:
    """Return the first matching neighborhood keyword, or None."""
    text_low = text.lower()
    for kw in config.NEIGHBORHOOD_KEYWORDS:
        if kw in text_low:
            return kw
    return None


def _is_scam(listing: Listing) -> bool:
    """Heuristic scam detection."""
    text = (listing.title + " " + listing.body_snippet)

    # Pattern match
    if _SCAM_RE.search(text):
        return True

    # Suspiciously cheap (well below MIN_RENT)
    if listing.price is not None and listing.price > 0 and listing.price < config.MIN_RENT:
        return True

    # Empty / near-empty listing
    if len((listing.title + listing.body_snippet).strip()) < 30:
        return True

    return False


def _check_move_in(listing: Listing) -> str | None:
    """Return a tag if move-in date is outside the target window. None if fine or unknown."""
    if not listing.move_in_date:
        return None
    try:
        d = date.fromisoformat(listing.move_in_date)
    except (ValueError, TypeError):
        return None

    earliest = date.fromisoformat(config.EARLIEST_MOVE_IN)
    latest   = date.fromisoformat(config.LATEST_MOVE_IN)

    if d < earliest:
        return f"early-move-in:{listing.move_in_date}"
    if d > latest:
        return f"late-move-in:{listing.move_in_date}"
    return None


def filter_listings(listings: list[Listing]) -> list[Listing]:
    """Apply all filters. Returns the listings that pass, with soft-filter tags added."""
    kept: list[Listing] = []
    rejected = {"over_budget": 0, "wrong_area": 0, "scam": 0}

    for l in listings:
        # HARD: over budget
        if l.price is not None and l.price > config.MAX_RENT:
            rejected["over_budget"] += 1
            continue

        # HARD: not in target neighborhoods
        full_text = " ".join(filter(None, [l.title, l.body_snippet, l.neighborhood or ""]))
        hood = _matches_neighborhood(full_text)
        if hood is None:
            rejected["wrong_area"] += 1
            continue
        if not l.neighborhood:
            l.neighborhood = hood.title()

        # SCAM
        if _is_scam(l):
            rejected["scam"] += 1
            continue

        # SOFT tags
        if l.duration_months is not None:
            if l.duration_months < config.SUBLET_DURATION_MIN_MONTHS:
                l.tags.append(f"short-{l.duration_months}mo")
            elif l.duration_months > config.SUBLET_DURATION_MAX_MONTHS:
                l.tags.append(f"long-{l.duration_months}mo")

        move_in_tag = _check_move_in(l)
        if move_in_tag:
            l.tags.append(move_in_tag)

        if config.REQUIRE_FURNISHED and l.furnished is False:
            l.tags.append("unfurnished")

        kept.append(l)

    logger.info(
        f"Filter: kept {len(kept)} / {len(listings)} "
        f"(rejected: {rejected['over_budget']} over budget, "
        f"{rejected['wrong_area']} wrong area, {rejected['scam']} scam)"
    )
    return kept
