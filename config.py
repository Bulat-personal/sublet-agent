"""
Sublet-agent configuration. Defaults adapted from rental-agent.
Edit the constants below before running. Secrets come from env vars.
"""

import os

# ─── Your preferences ─────────────────────────────────────────────────────────

MAX_RENT = 2500                  # hard filter: reject listings above this monthly price
MIN_RENT = 700                   # quality filter: scam-suspicious below this
MAX_BEDROOMS = 2                 # 0=studio, 1=1BR, 2=2BR

# Sublet-specific
SUBLET_DURATION_MIN_MONTHS = 1
SUBLET_DURATION_MAX_MONTHS = 12
REQUIRE_FURNISHED = False        # flag, not filter (still get unfurnished listings)
EARLIEST_MOVE_IN = "2026-06-01"  # ISO date; flag listings starting before
LATEST_MOVE_IN   = "2026-09-30"  # ISO date; flag listings starting after


# ─── Regions ──────────────────────────────────────────────────────────────────
#
# Each region is one Telegram channel. Listings are routed to the channel of
# the first matching neighborhood. If a region's chat_id env var is missing,
# its listings fall back to TELEGRAM_CHAT_ID.

REGIONS = {
    "manhattan": {
        "label": "Manhattan",
        "emoji": "🟦",
        "chat_id_env": "TELEGRAM_CHAT_ID_MANHATTAN",
        "neighborhoods": [
            "soho", "tribeca", "financial district", "fidi", "battery park",
            "lower east side", "les", "east village", "west village",
            "greenwich village", "nolita", "noho", "chinatown", "two bridges",
            "seaport", "chelsea", "flatiron", "gramercy", "kips bay",
        ],
    },
    "north_brooklyn": {
        "label": "North Brooklyn",
        "emoji": "🟩",
        "chat_id_env": "TELEGRAM_CHAT_ID_NORTH_BK",
        "neighborhoods": ["williamsburg", "greenpoint", "bushwick"],
    },
    "south_brooklyn": {
        "label": "South Brooklyn",
        "emoji": "🟪",
        "chat_id_env": "TELEGRAM_CHAT_ID_SOUTH_BK",
        "neighborhoods": [
            "downtown brooklyn", "dumbo", "boerum hill",
            "cobble hill", "carroll gardens", "park slope", "gowanus",
        ],
    },
    "queens": {
        "label": "Queens",
        "emoji": "🟧",
        "chat_id_env": "TELEGRAM_CHAT_ID_QUEENS",
        "neighborhoods": ["astoria", "long island city", "lic", "sunnyside"],
    },
    "new_jersey": {
        "label": "New Jersey",
        "emoji": "🟫",
        "chat_id_env": "TELEGRAM_CHAT_ID_NJ",
        "neighborhoods": ["jersey city", "hoboken", "journal square", "newport"],
    },
}

# Derived: flat list of all neighborhood keywords (used by filter + scrapers)
NEIGHBORHOOD_KEYWORDS = [
    hood for region in REGIONS.values() for hood in region["neighborhoods"]
]


# ─── Craigslist search groups (sublets/rooms categories only) ─────────────────

CL_SEARCH_GROUPS = {
    "nyc": [
        "soho tribeca chelsea lower east side",
        "east village west village greenwich village",
        "williamsburg greenpoint",
        "bushwick",
        "downtown brooklyn carroll gardens",
        "park slope cobble hill",
        "astoria long island city",   # Queens
    ],
    "nj": [
        "jersey city hoboken",
    ],
}

# ─── Neighborhood median rents (for % comparison enrichment) ──────────────────

MEDIANS = {
    "williamsburg":      {"studio": 3000, "1br": 3500, "2br": 4800},
    "greenpoint":        {"studio": 2800, "1br": 3200, "2br": 4200},
    "bushwick":          {"studio": 2200, "1br": 2800, "2br": 3500},
    "park slope":        {"studio": 2600, "1br": 3200, "2br": 4400},
    "carroll gardens":   {"studio": 2700, "1br": 3300, "2br": 4500},
    "cobble hill":       {"studio": 2700, "1br": 3400, "2br": 4600},
    "downtown brooklyn": {"studio": 2800, "1br": 3400, "2br": 4600},
    "east village":      {"studio": 2800, "1br": 3400, "2br": 4800},
    "west village":      {"studio": 3200, "1br": 4200, "2br": 6000},
    "soho":              {"studio": 3500, "1br": 4500, "2br": 6500},
    "tribeca":           {"studio": 3800, "1br": 5000, "2br": 7000},
    "chelsea":           {"studio": 3000, "1br": 3800, "2br": 5200},
    "lower east side":   {"studio": 2700, "1br": 3200, "2br": 4500},
    "astoria":           {"studio": 2200, "1br": 2700, "2br": 3500},
    "long island city":  {"studio": 2800, "1br": 3400, "2br": 4600},
    "jersey city":       {"studio": 2200, "1br": 2800, "2br": 3600},
    "hoboken":           {"studio": 2400, "1br": 3000, "2br": 4000},
}

# ─── Reddit subreddits ────────────────────────────────────────────────────────

REDDIT_SUBREDDITS = [
    "SublettingNYC",
    "NYCapartments",
    "AskNYC",            # filter heavily for sublet keywords
]

REDDIT_SUBLET_KEYWORDS = [
    "sublet", "sublease", "sub-let", "subletting",
    "lease takeover", "lease transfer", "lease break", "lease assignment",
    "room available", "room for rent",
]

# ─── Sources to enable ────────────────────────────────────────────────────────

# Phase 1 — no Playwright required
ENABLED_SOURCES = ["craigslist", "listings_project", "spareroom", "reddit"]

# Phase 2 — flip on once Playwright is wired in CI
# ENABLED_SOURCES += ["ohana", "leasebreak"]

# Facebook: opt-in via ENABLE_FACEBOOK=true env var, local-only

# ─── Per-source minimum cadence (informational; GH Actions runs every 15min) ──

SOURCE_CADENCE_MINUTES = {
    "craigslist": 15,
    "listings_project": 360,    # weekly inventory — 6h is plenty
    "spareroom": 30,
    "reddit": 15,
    "ohana": 20,
    "leasebreak": 30,
    "facebook": 60,
}

# ─── Secrets (env vars only — never hardcode) ─────────────────────────────────

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")    # global fallback

# Per-region chat IDs are read lazily in notifier.py via REGIONS[key]["chat_id_env"]

# Reddit uses public RSS feeds — no credentials needed.

RESEND_API_KEY    = os.environ.get("RESEND_API_KEY", "")
TARGET_EMAIL      = os.environ.get("TARGET_EMAIL", "milkypillow@gmail.com")

ENABLE_FACEBOOK   = os.environ.get("ENABLE_FACEBOOK", "false").lower() == "true"
FB_COOKIES_PATH   = os.environ.get("FB_COOKIES_PATH", "./fb_cookies.json")
