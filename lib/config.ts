/**
 * Config — set via environment variables (mirrors config.py).
 */

// The Odds API → https://the-odds-api.com (free, 500 req/month)
export const THE_ODDS_API_KEY = process.env.THE_ODDS_API_KEY ?? "";

// Minimum edge % to flag a value bet
export const MIN_EDGE_PCT = 5.0;

// Bookmaker region ("us", "uk", "eu", "au")
export const ODDS_REGION = "eu";

// Max goals to consider in probability matrix
export const MAX_GOALS = 10;

// WC 2026 hosts — get a slight home advantage boost
export const WC_HOSTS = new Set<string>([
  "United States",
  "Canada",
  "Mexico",
]);

// Bankroll in HUF used for live Kelly stake sizing
export const TELEGRAM_BANKROLL = 2300;

// Maintenance mode (MAINTENANCE=1|true|yes)
export const MAINTENANCE = ["1", "true", "yes"].includes(
  (process.env.MAINTENANCE ?? "").toLowerCase()
);
