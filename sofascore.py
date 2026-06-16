"""
Fetch live WC 2026 match data from ESPN public API (no auth required).
Returns: score, minute, estimated xG, shots, possession, red cards.

xG is estimated from shots on target + total shots when not directly available.
Formula: xG ≈ shots_on_target * 0.25 + other_shots * 0.04
"""

import requests
import time

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"

_cache: dict = {}
_CACHE_TTL = 55  # seconds — slightly under 60s auto-refresh

# ESPN name → our model name
_NAME_MAP = {
    "USA":                      "United States",
    "United States":            "United States",
    "South Korea":              "Korea Republic",
    "Korea Republic":           "Korea Republic",
    "IR Iran":                  "Iran",
    "Côte d'Ivoire":            "Ivory Coast",
    "Cote d'Ivoire":            "Ivory Coast",
    "Congo, DR":                "DR Congo",
    "DR Congo":                 "DR Congo",
    "Czech Republic":           "Czech Republic",
    "Czechia":                  "Czech Republic",
    "Bosnia and Herzegovina":   "Bosnia and Herzegovina",
    "Bosnia & Herzegovina":     "Bosnia and Herzegovina",
    "North Macedonia":          "North Macedonia",
    "Cape Verde":               "Cape Verde",
    "Cabo Verde":               "Cape Verde",
}


def _en(name: str) -> str:
    return _NAME_MAP.get(name, name)


def _get_espn() -> dict:
    now = time.time()
    if "espn" in _cache and now - _cache["espn"]["ts"] < _CACHE_TTL:
        return _cache["espn"]["data"]
    r = requests.get(ESPN_URL, headers=_HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json()
    _cache["espn"] = {"data": data, "ts": now}
    return data


def _estimate_xg(shots_on_target: int, total_shots: int) -> float:
    """
    Estimate xG from shot counts.
    Shots on target: ~0.25 xG each (on average)
    Other shots: ~0.04 xG each
    """
    other_shots = max(0, total_shots - shots_on_target)
    return round(shots_on_target * 0.25 + other_shots * 0.04, 2)


def _parse_stats(competitors: list) -> tuple[dict, dict]:
    """Parse ESPN competitor stats into home/away dicts."""
    home_stats, away_stats = {}, {}
    for c in competitors:
        side = home_stats if c.get("homeAway") == "home" else away_stats
        for stat in c.get("statistics", []):
            name = stat.get("name", "")
            val  = stat.get("value", 0)
            try:
                side[name] = float(val)
            except (TypeError, ValueError):
                side[name] = 0
    return home_stats, away_stats


def _parse_score(competitors: list) -> tuple[int, int]:
    home_score = away_score = 0
    for c in competitors:
        try:
            score = int(float(c.get("score", 0)))
        except (TypeError, ValueError):
            score = 0
        if c.get("homeAway") == "home":
            home_score = score
        else:
            away_score = score
    return home_score, away_score


def _parse_team_names(competitors: list) -> tuple[str, str, str, str]:
    home_raw = away_raw = ""
    for c in competitors:
        name = c.get("team", {}).get("displayName", "")
        if c.get("homeAway") == "home":
            home_raw = name
        else:
            away_raw = name
    return home_raw, _en(home_raw), away_raw, _en(away_raw)


def _parse_minute(status: dict) -> tuple[int, int]:
    """Returns (minute, extra_time). Handles '90+5\'' format correctly."""
    clock = status.get("displayClock", "0'")
    state = status.get("type", {}).get("state", "")
    if state not in ("in",):
        return 0, 0
    try:
        clean = clock.replace("'", "").strip()
        if "+" in clean:
            base, extra = clean.split("+", 1)
            return int(base), int(extra)
        return int(clean), 0
    except Exception:
        return 0, 0


def _count_red_cards(competitors: list) -> tuple[int, int]:
    """ESPN doesn't directly expose red cards in scoreboard — return 0,0 for now."""
    return 0, 0


def get_live_wc_matches() -> list[dict]:
    """Return all currently live WC 2026 matches with stats."""
    try:
        data = _get_espn()
    except Exception as e:
        print(f"  ESPN error: {e}")
        return []

    results = []
    for event in data.get("events", []):
        competitions = event.get("competitions", [])
        if not competitions:
            continue
        comp = competitions[0]

        status = comp.get("status", {})
        state  = status.get("type", {}).get("state", "")

        # Only include in-progress matches
        if state != "in":
            continue

        competitors = comp.get("competitors", [])
        home_raw, home_en, away_raw, away_en = _parse_team_names(competitors)
        home_score, away_score = _parse_score(competitors)
        minute, extra = _parse_minute(status)
        home_stats, away_stats = _parse_stats(competitors)
        red_h, red_a = _count_red_cards(competitors)

        sot_h = int(home_stats.get("shotsOnTarget", 0))
        sot_a = int(away_stats.get("shotsOnTarget", 0))
        tot_h = int(home_stats.get("totalShots", 0))
        tot_a = int(away_stats.get("totalShots", 0))
        pos_h = float(home_stats.get("possessionPct", 50))
        pos_a = float(away_stats.get("possessionPct", 50))

        xg_h = _estimate_xg(sot_h, tot_h)
        xg_a = _estimate_xg(sot_a, tot_a)

        results.append({
            "espn_id":            event.get("id", ""),
            "home_team":          home_en,
            "away_team":          away_en,
            "home_team_raw":      home_raw,
            "away_team_raw":      away_raw,
            "home_score":         home_score,
            "away_score":         away_score,
            "minute":             minute,
            "extra_time":         extra,
            "status":             status.get("type", {}).get("description", ""),
            "xg_home":            xg_h,
            "xg_away":            xg_a,
            "xg_source":          "estimated",   # flag so UI can show ~
            "shots_on_target_home": sot_h,
            "shots_on_target_away": sot_a,
            "total_shots_home":   tot_h,
            "total_shots_away":   tot_a,
            "possession_home":    round(pos_h, 1),
            "possession_away":    round(pos_a, 1),
            "red_cards_home":     red_h,
            "red_cards_away":     red_a,
        })

    return results
