"""
Fetches live bookmaker odds from The Odds API (free tier).
Sign up free at https://the-odds-api.com — 500 requests/month included.
"""

import requests
from config import THE_ODDS_API_KEY, ODDS_REGION

BASE_URL = "https://api.the-odds-api.com/v4"

# Try these sport keys in order — The Odds API key for WC 2026
WC_SPORT_KEYS = [
    "soccer_fifa_world_cup_2026",
    "soccer_fifa_world_cup",
    "soccer_international",
]


def get_wc_odds() -> list[dict]:
    """
    Returns a list of matches with bookmaker odds.
    Each item: {home_team, away_team, bookmakers: [{name, h2h: [home, draw, away]}]}
    Returns [] if no API key is configured.
    """
    if not THE_ODDS_API_KEY:
        return []

    for sport_key in WC_SPORT_KEYS:
        url = f"{BASE_URL}/sports/{sport_key}/odds/"
        params = {
            "apiKey": THE_ODDS_API_KEY,
            "regions": ODDS_REGION,
            "markets": "h2h",
            "oddsFormat": "decimal",
        }
        resp = requests.get(url, params=params, timeout=15)

        if resp.status_code == 404:
            continue  # try next sport key
        resp.raise_for_status()

        data = resp.json()
        remaining = resp.headers.get("x-requests-remaining", "?")
        print(f"  Fetched odds for {len(data)} matches. Requests remaining: {remaining}/month")
        return _parse(data)

    print("  No WC odds found via The Odds API (tournament may not be live yet).")
    return []


def _parse(raw: list) -> list[dict]:
    matches = []
    for game in raw:
        books = []
        for bm in game.get("bookmakers", []):
            for market in bm.get("markets", []):
                if market["key"] != "h2h":
                    continue
                outcomes = {o["name"]: o["price"] for o in market["outcomes"]}
                draw_odds = outcomes.get("Draw", None)
                books.append({
                    "name": bm["title"],
                    "home_odds": outcomes.get(game["home_team"]),
                    "draw_odds": draw_odds,
                    "away_odds": outcomes.get(game["away_team"]),
                })
        matches.append({
            "home_team": game["home_team"],
            "away_team": game["away_team"],
            "commence_time": game.get("commence_time", ""),
            "bookmakers": books,
        })
    return matches


def best_odds(match: dict) -> dict:
    """Returns the best (highest) decimal odds across all bookmakers."""
    best = {"home_odds": None, "draw_odds": None, "away_odds": None}
    for bm in match["bookmakers"]:
        for key in best:
            val = bm.get(key)
            if val and (best[key] is None or val > best[key]):
                best[key] = val
    return best
