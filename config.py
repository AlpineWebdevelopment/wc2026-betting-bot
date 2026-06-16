import os

# ============================================================
# CONFIG — set via environment variables (or .env for local dev)
# ============================================================
# The Odds API  → https://the-odds-api.com  (free, 500 req/month)
THE_ODDS_API_KEY = os.environ.get("THE_ODDS_API_KEY", "")

# How many years of historical data to train on
TRAINING_YEARS = 4

# Time decay: older matches get lower weight
TIME_DECAY = 0.002

# Minimum edge % to flag a value bet
MIN_EDGE_PCT = 5.0

# Bookmaker region ("us", "uk", "eu", "au")
ODDS_REGION = "eu"

# Max goals to consider in probability matrix
MAX_GOALS = 10

# WC 2026 hosts — get a slight home advantage boost
WC_HOSTS = {"United States", "Canada", "Mexico"}

# ── Telegram bot ─────────────────────────────────────────────
TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_TOKEN", "8763791576:AAHmhBwNpH2sG6PHkhb2VgXt7NbIxnEdeZ0")
TELEGRAM_CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "5409923120")
TELEGRAM_INTERVAL_HOURS = 3        # how often to check (hours)
TELEGRAM_MIN_EDGE = 7.0            # only alert if best edge >= this %
TELEGRAM_BANKROLL = 10000          # your bankroll in HUF
