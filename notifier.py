"""
Notification dispatch.

Primary:   Telegram bot — instant, free, rich previews.
Fallback:  Resend email — used if Telegram isn't configured or fails.

Routing: each region (Manhattan, North Brooklyn, South Brooklyn, Queens, NJ)
goes to its own Telegram channel. If a region's chat_id isn't set,
its listings fall back to the global TELEGRAM_CHAT_ID.
"""

from __future__ import annotations

import os
import sys
import logging
from html import escape as html_escape

import requests

import config
from models import Listing

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

# Telegram message text caps at 4096 chars; aim well under to be safe.
MAX_MESSAGE_CHARS = 3500


# ─── Formatting ──────────────────────────────────────────────────────────────

SOURCE_BADGE = {
    "craigslist_nyc":      "🟧 CL-NYC",
    "craigslist_nj":       "🟧 CL-NJ",
    "listings_project":    "🟪 LP",
    "spareroom":           "🟦 SpareRoom",
    "ohana":               "🟩 Ohana",
    "leasebreak":          "🟫 LeaseBreak",
    "facebook":            "🔵 FB",
}


def _badge(source: str) -> str:
    for prefix, badge in SOURCE_BADGE.items():
        if source.startswith(prefix):
            return badge
    if source.startswith("reddit_"):
        return f"🟥 r/{source.split('_', 1)[1]}"
    return f"📌 {source}"


def _format_listing(l: Listing) -> str:
    """Telegram HTML-formatted single-listing block."""
    price = f"${l.price:,}/mo" if l.price else "Price ?"
    title = html_escape((l.title or "Listing")[:120])
    url   = html_escape(l.url)

    bits = [f"<b>{title}</b>", f"💰 {price}"]

    if l.neighborhood:
        bits.append(f"📍 {html_escape(l.neighborhood)}")
    if l.duration_months:
        bits.append(f"📅 {l.duration_months}mo")
    if l.move_in_date:
        bits.append(f"➡️ move-in {l.move_in_date}")
    if l.furnished is True:
        bits.append("🛋️ furnished")
    if l.bedrooms is not None:
        bits.append(f"🛏️ {'studio' if l.bedrooms == 0 else f'{l.bedrooms}BR'}")
    if l.tags:
        bits.append("🏷️ " + ", ".join(html_escape(t) for t in l.tags))

    meta = " · ".join(bits[1:])
    badge = _badge(l.source)

    return (
        f"{bits[0]}\n"
        f"{meta}\n"
        f"{badge} · <a href=\"{url}\">view →</a>"
    )


# ─── Telegram ────────────────────────────────────────────────────────────────

def _send_telegram(chat_id: str, text: str) -> bool:
    """Send a single Telegram message to a specific chat_id. Returns True on success."""
    if not (config.TELEGRAM_BOT_TOKEN and chat_id):
        logger.warning("Telegram not configured (missing bot token or chat_id)")
        return False

    url = TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN, method="sendMessage")
    try:
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }, timeout=15)
        if resp.ok:
            return True
        logger.error(f"Telegram send failed [{resp.status_code}]: {resp.text[:200]}")
        return False
    except Exception as exc:
        logger.error(f"Telegram send exception: {exc}")
        return False


def _chunk_listings(listings: list[Listing]) -> list[str]:
    """Group listings into Telegram-sized message chunks."""
    chunks: list[str] = []
    buffer = ""
    for l in listings:
        block = _format_listing(l) + "\n\n"
        if len(buffer) + len(block) > MAX_MESSAGE_CHARS and buffer:
            chunks.append(buffer.rstrip())
            buffer = block
        else:
            buffer += block
    if buffer:
        chunks.append(buffer.rstrip())
    return chunks


def _send_region_digest(chat_id: str, region_label: str, region_emoji: str, listings: list[Listing]) -> bool:
    """Send N listings via Telegram to a specific region's chat, chunked."""
    if not listings:
        return False
    n = len(listings)
    header = f"{region_emoji} <b>{n} new {region_label} sublet{'s' if n != 1 else ''}</b>\n\n"
    chunks = _chunk_listings(listings)
    if not chunks:
        return False
    chunks[0] = header + chunks[0]

    all_ok = True
    for i, chunk in enumerate(chunks, start=1):
        ok = _send_telegram(chat_id, chunk)
        all_ok = all_ok and ok
        if len(chunks) > 1:
            logger.info(f"Telegram[{region_label}]: chunk {i}/{len(chunks)} ({'ok' if ok else 'FAIL'})")
    return all_ok


def _resolve_chat_id(region_key: str | None) -> tuple[str, str, str]:
    """
    Return (chat_id, label, emoji) for a region.
    Falls back to global TELEGRAM_CHAT_ID if the region-specific env var is unset.
    """
    if region_key and region_key in config.REGIONS:
        region = config.REGIONS[region_key]
        chat_id = os.environ.get(region["chat_id_env"], "")
        if chat_id:
            return chat_id, region["label"], region["emoji"]
        # Fall through to global if region-specific not set
        return config.TELEGRAM_CHAT_ID, region["label"], region["emoji"]
    # Unknown / no region — use global with neutral label
    return config.TELEGRAM_CHAT_ID, "NYC", "🏙️"


def send_telegram_routed(listings: list[Listing]) -> bool:
    """
    Route listings to per-region Telegram chats.
    Returns True if every region we tried to message succeeded.
    """
    if not listings:
        return False

    # Bucket by region
    by_region: dict[str | None, list[Listing]] = {}
    for l in listings:
        by_region.setdefault(l.region, []).append(l)

    all_ok = True
    for region_key, region_listings in by_region.items():
        chat_id, label, emoji = _resolve_chat_id(region_key)
        if not chat_id:
            logger.warning(f"No chat_id for region '{region_key}' — skipping {len(region_listings)} listings")
            all_ok = False
            continue
        ok = _send_region_digest(chat_id, label, emoji, region_listings)
        logger.info(f"[{label}] sent {len(region_listings)} listings → {'ok' if ok else 'FAIL'}")
        all_ok = all_ok and ok

    return all_ok


# ─── Email fallback (Resend) ─────────────────────────────────────────────────

def _send_email_fallback(listings: list[Listing]) -> bool:
    """Plain-HTML digest via Resend. Only used if Telegram isn't configured/fails."""
    if not config.RESEND_API_KEY:
        return False

    rows = []
    for l in listings:
        price = f"${l.price:,}/mo" if l.price else "Price ?"
        meta_parts = [price]
        if l.neighborhood:
            meta_parts.append(l.neighborhood)
        if l.duration_months:
            meta_parts.append(f"{l.duration_months}mo")
        if l.move_in_date:
            meta_parts.append(f"move-in {l.move_in_date}")
        meta = " · ".join(meta_parts)

        rows.append(
            f'<div style="padding:12px 0;border-bottom:1px solid #eee;">'
            f'<div style="font-weight:600;"><a href="{html_escape(l.url)}">{html_escape(l.title[:120])}</a></div>'
            f'<div style="color:#555;font-size:13px;margin-top:4px;">{html_escape(meta)}</div>'
            f'<div style="color:#999;font-size:12px;margin-top:2px;">{_badge(l.source)}</div>'
            f'</div>'
        )

    html = (
        f'<div style="font-family:sans-serif;max-width:600px;margin:auto;padding:20px;">'
        f'<h2>🏠 {len(listings)} new NYC sublets</h2>'
        + "".join(rows)
        + '</div>'
    )

    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {config.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": "Sublet Agent <onboarding@resend.dev>",
                "to": [config.TARGET_EMAIL],
                "subject": f"🏠 {len(listings)} new NYC sublet{'s' if len(listings)!=1 else ''}",
                "html": html,
            },
            timeout=30,
        )
        if resp.ok:
            logger.info(f"Email fallback sent (id={resp.json().get('id', '?')})")
            return True
        logger.error(f"Email fallback failed [{resp.status_code}]: {resp.text[:200]}")
        return False
    except Exception as exc:
        logger.error(f"Email fallback exception: {exc}")
        return False


# ─── Public API ──────────────────────────────────────────────────────────────

def notify(listings: list[Listing]) -> bool:
    """Dispatch notifications. Returns True if at least one channel succeeded."""
    if not listings:
        logger.info("notify: no listings to send")
        return False

    tg_ok = send_telegram_routed(listings)
    if tg_ok:
        return True

    logger.info("Telegram unavailable or failed — trying email fallback")
    return _send_email_fallback(listings)


# ─── CLI helpers ─────────────────────────────────────────────────────────────

def _print_chat_id_helper():
    """Walk the user through finding their Telegram chat_id(s) by calling getUpdates.

    Works for direct messages, group chats, AND channels (as long as the bot
    is admin in the channel and at least one message has been posted there).
    """
    if not config.TELEGRAM_BOT_TOKEN:
        print("Set TELEGRAM_BOT_TOKEN in .env first, then post a message in each channel/group/DM.")
        sys.exit(1)
    url = TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN, method="getUpdates")
    resp = requests.get(url, timeout=10)
    data = resp.json()
    if not data.get("ok"):
        print(f"Telegram API error: {data}")
        sys.exit(1)
    updates = data.get("result", [])
    if not updates:
        print("No updates yet. Post a message in each Telegram chat/channel where the bot is, then re-run this.")
        sys.exit(0)
    seen = {}
    for u in updates:
        msg = (u.get("message") or u.get("channel_post")
               or u.get("edited_message") or u.get("edited_channel_post") or {})
        chat = msg.get("chat", {})
        cid = chat.get("id")
        if cid is None or cid in seen:
            continue
        title = chat.get("title") or chat.get("username") or chat.get("first_name") or "?"
        ctype = chat.get("type", "?")
        seen[cid] = (title, ctype)
    if not seen:
        print("No usable chats found. Make sure your bot is admin in the channels and has been messaged.")
        sys.exit(0)
    print("Found these chats:")
    for cid, (title, ctype) in seen.items():
        print(f"  chat_id={cid}  type={ctype}  name={title!r}")
    print("\n→ For each channel, copy its chat_id into the matching GitHub Secret:")
    print("    TELEGRAM_CHAT_ID_MANHATTAN")
    print("    TELEGRAM_CHAT_ID_NORTH_BK")
    print("    TELEGRAM_CHAT_ID_SOUTH_BK")
    print("    TELEGRAM_CHAT_ID_QUEENS")
    print("    TELEGRAM_CHAT_ID_NJ")


def _send_test():
    """Send a hardcoded test message to each configured region."""
    samples = [
        Listing(id="test_m", source="craigslist_nyc",
                url="https://example.com/m", title="TEST Manhattan: $2,200 sublet in East Village",
                price=2200, neighborhood="East Village", duration_months=3,
                move_in_date="2026-06-15", furnished=True, bedrooms=1,
                body_snippet="Test notification — Manhattan channel.", region="manhattan"),
        Listing(id="test_nbk", source="craigslist_nyc",
                url="https://example.com/nbk", title="TEST North BK: $1,900 room in Williamsburg",
                price=1900, neighborhood="Williamsburg", region="north_brooklyn",
                body_snippet="Test notification — North Brooklyn channel."),
        Listing(id="test_sbk", source="craigslist_nyc",
                url="https://example.com/sbk", title="TEST South BK: $2,400 sublet in Park Slope",
                price=2400, neighborhood="Park Slope", region="south_brooklyn",
                body_snippet="Test notification — South Brooklyn channel."),
        Listing(id="test_q", source="craigslist_nyc",
                url="https://example.com/q", title="TEST Queens: $1,800 in Astoria",
                price=1800, neighborhood="Astoria", region="queens",
                body_snippet="Test notification — Queens channel."),
        Listing(id="test_nj", source="craigslist_nj",
                url="https://example.com/nj", title="TEST NJ: $1,700 in Jersey City",
                price=1700, neighborhood="Jersey City", region="new_jersey",
                body_snippet="Test notification — NJ channel."),
    ]
    ok = notify(samples)
    print("✅ Sent" if ok else "❌ Some sends failed — check logs above")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if len(sys.argv) > 1 and sys.argv[1] == "--get-chat-id":
        _print_chat_id_helper()
    elif len(sys.argv) > 1 and sys.argv[1] == "--test":
        _send_test()
    else:
        print("Usage:")
        print("  python -m notifier --get-chat-id   # find all your Telegram chat_ids at once")
        print("  python -m notifier --test          # send a test message to each region")
