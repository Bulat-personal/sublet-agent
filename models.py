"""
Listing dataclass — the normalized shape every source produces.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Listing:
    id: str                         # source-prefixed unique id, e.g. "cl_7567432"
    source: str                     # "craigslist" | "listings_project" | "spareroom" | "reddit" | "ohana" | "leasebreak" | "facebook"
    url: str
    title: str
    price: Optional[int] = None
    neighborhood: Optional[str] = None
    duration_months: Optional[int] = None     # sublet-specific
    move_in_date: Optional[str] = None        # sublet-specific, ISO date "YYYY-MM-DD"
    move_out_date: Optional[str] = None       # sublet-specific, ISO date
    furnished: Optional[bool] = None
    bedrooms: Optional[int] = None
    body_snippet: str = ""                    # first ~300 chars
    posted_at: Optional[str] = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
