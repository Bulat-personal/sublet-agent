# 🏙️ NYC Sublet Agent

A free, every-15-minutes agent that hunts NYC sublets across Craigslist, Listings Project, SpareRoom, and Reddit, and pings you on Telegram when something matches your criteria.

**Cost: $0/month.** Hosted on GitHub Actions (unlimited free minutes on a public repo) + Telegram bot + free Reddit API.

---

## What it does (Phase 1)

Every 15 minutes, it:
1. Scrapes **Craigslist NYC + NJ** (sublets + rooms categories)
2. Scrapes **Listings Project** (curated, weekly-refreshing housing listings)
3. Scrapes **SpareRoom NYC** (~2,300+ live ads, plain HTML)
4. Pulls recent **Reddit** posts from r/SublettingNYC, r/NYCapartments, r/AskNYC (filtered for sublet keywords)
5. Filters by your budget, neighborhoods, and basic scam patterns
6. Deduplicates against the persistent `state.db` (committed back to the repo)
7. Pushes any new matches to your Telegram (with Resend email as fallback)

**Phase 2** (commented out, ready to enable): Ohana + LeaseBreak via Playwright.
**Phase 4** (opt-in, local-only): Facebook groups via burner account.

---

## Setup

### 1. Tweak your preferences

Edit `config.py`:

```python
MAX_RENT = 2500
EARLIEST_MOVE_IN = "2026-06-01"
LATEST_MOVE_IN   = "2026-09-30"
NEIGHBORHOOD_KEYWORDS = [...]   # add/remove as you like
```

### 2. Create a Telegram bot (2 min, free)

1. Open Telegram, search **@BotFather**, send `/newbot`, pick a name (e.g. "BulatSubletBot")
2. Copy the **bot token** it gives you
3. Send any message to your new bot in Telegram (just "hi" is fine)
4. Run locally to find your chat_id:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
TELEGRAM_BOT_TOKEN=<your_token> python -m notifier --get-chat-id
```

It'll print your `chat_id`. Save both the token and chat_id — you'll add them to GitHub Secrets in step 5.

### 3. Reddit — nothing to do!

We use Reddit's public RSS feeds (`reddit.com/r/<sub>/new/.rss`), which need no app, no API key, no account. Skip ahead.

### 4. (Optional) Resend for email fallback

If you want an email backup when Telegram fails:
1. Sign up at https://resend.com (free 3,000 emails/mo)
2. Copy your API key

### 5. Push to a **public** GitHub repo

```bash
cd /Users/bulat/Documents/sublet-agent
git init -b main
git add .
git commit -m "Initial sublet-agent"
# Create a NEW public repo on github.com (e.g. "sublet-agent"), then:
git remote add origin https://github.com/<your-username>/sublet-agent.git
git push -u origin main
```

**Important: it must be a PUBLIC repo.** GitHub Actions only gives unlimited free minutes on public repos. Private repos cap at 2,000 min/month, which isn't enough for every-15-min runs.

(No worries about secrets — they live in GitHub Secrets, not the code.)

### 6. Add secrets in GitHub

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**, and add:

| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | from step 2 |
| `TELEGRAM_CHAT_ID` | from step 2 |
| `RESEND_API_KEY` | from step 4 (optional) |
| `TARGET_EMAIL` | your email address (optional, for fallback) |

### 7. Test it manually

In your GitHub repo → **Actions tab → sublet-hunt workflow → Run workflow**. Wait ~1 min for it to finish. Check your Telegram.

After the first successful run, the cron schedule will fire every 15 min automatically.

---

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in .env yourself — never commit it (it's in .gitignore)
python main.py
```

Test individual sources:
```bash
python -m sources.craigslist
python -m sources.listings_project
python -m sources.spareroom
python -m sources.reddit
```

Test Telegram notification:
```bash
python -m notifier --test
```

---

## Enabling Phase 2 (Ohana + LeaseBreak)

These two sources use Playwright (headless browser) because they're JS-heavy / Cloudflare-protected.

1. In `config.py`, uncomment:
   ```python
   ENABLED_SOURCES += ["ohana", "leasebreak"]
   ```
2. In `.github/workflows/hunt.yml`, uncomment the **"Install Playwright + Chromium"** step.
3. Implement `sources/ohana.py` and `sources/leasebreak.py` (skeletons not included in Phase 1).
4. Push.

Playwright adds ~30s per run — still well within GitHub Actions free tier.

---

## Files

| File | Purpose |
|---|---|
| `main.py` | Orchestrator — one run per GitHub Actions cron tick |
| `config.py` | Your preferences (rent, neighborhoods, move-in window) |
| `db.py` | SQLite dedup, committed back to repo as `state.db` |
| `filter.py` | Hard/soft/scam filters |
| `models.py` | `Listing` dataclass |
| `notifier.py` | Telegram primary, Resend email fallback |
| `sources/craigslist.py` | CL NYC + NJ sublets/rooms |
| `sources/listings_project.py` | listingsproject.com NYC |
| `sources/spareroom.py` | spareroom.com NYC |
| `sources/reddit.py` | PRAW for sublet subreddits |
| `.github/workflows/hunt.yml` | GitHub Actions cron + state commit |

---

## Living docs

- `99_troubleshooting.md` — append lessons as scrapers break and we patch them
