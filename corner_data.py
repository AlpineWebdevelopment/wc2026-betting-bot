"""
Fetches historical international match corner data from ESPN.
Used to train the CornerModel.
"""
import requests, json, os, time
from datetime import datetime, timedelta

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corner_training_cache.json")

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# ESPN competition slugs → date ranges to scan
TOURNAMENTS = [
    # (slug, start_date, end_date, tournament_name, weight)
    ("fifa.world",      "2022-11-20", "2022-12-18", "FIFA World Cup 2022", 3.0),
    ("uefa.euro",       "2024-06-14", "2024-07-14", "UEFA Euro 2024",      2.0),
    ("conmebol.america","2024-06-20", "2024-07-14", "Copa América 2024",   2.0),
    ("afc.asian.cup",   "2024-01-12", "2024-02-10", "AFC Asian Cup 2024",  1.5),
    ("caf.nations",     "2024-01-13", "2024-02-11", "AFCON 2024",          1.5),
    ("fifa.world",      "2026-06-11", None,          "FIFA World Cup 2026", 5.0),  # None = today
]

_NAME_MAP = {
    "USA": "United States", "United States": "United States",
    "South Korea": "Korea Republic", "Korea Republic": "Korea Republic",
    "IR Iran": "Iran", "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast", "Congo, DR": "DR Congo",
    "DR Congo": "DR Congo", "Czech Republic": "Czech Republic",
    "Czechia": "Czech Republic", "Bosnia and Herzegovina": "Bosnia and Herzegovina",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "North Macedonia": "North Macedonia",
}

def _en(name): return _NAME_MAP.get(name, name)

def _fetch_day(slug, date_str):
    """Fetch completed matches with corner stats for one day."""
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={date_str}"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  ESPN {slug} {date_str}: {e}")
        return []

    matches = []
    for event in data.get("events", []):
        comps = event.get("competitions", [])
        if not comps: continue
        comp = comps[0]
        state = comp.get("status", {}).get("type", {}).get("state", "")
        if state != "post": continue

        competitors = comp.get("competitors", [])
        home_team = away_team = ""
        home_corners = away_corners = None

        for c in competitors:
            name = _en(c.get("team", {}).get("displayName", ""))
            corners = None
            for stat in c.get("statistics", []):
                if stat.get("name", "").lower() in ("cornerkicks", "corners", "corner_kicks", "woncorners"):
                    try: corners = int(float(stat.get("displayValue") or stat.get("value") or 0))
                    except: pass
            if c.get("homeAway") == "home":
                home_team = name
                home_corners = corners
            else:
                away_team = name
                away_corners = corners

        if home_team and away_team and home_corners is not None and away_corners is not None:
            matches.append({
                "date": date_str,
                "home_team": home_team,
                "away_team": away_team,
                "home_corners": home_corners,
                "away_corners": away_corners,
            })
    return matches


def fetch_corner_training_data():
    """
    Fetch corner data for all configured tournaments.
    Caches results in corner_training_cache.json.
    Returns list of match dicts.
    """
    # Load existing cache
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                cache = json.load(f)
        except: cache = {}

    # Always re-fetch the last 3 days for any live tournament (matches finish late)
    today = datetime.now().date()
    refresh_cutoff = today - timedelta(days=3)
    for key in list(cache.keys()):
        try:
            parts = key.split(":")
            if len(parts) == 2:
                key_date = datetime.strptime(parts[1], "%Y-%m-%d").date()
                if key_date >= refresh_cutoff:
                    del cache[key]
        except ValueError:
            pass

    all_matches = []
    changed = False

    for slug, start_str, end_str, name, weight in TOURNAMENTS:
        start = datetime.strptime(start_str, "%Y-%m-%d")
        end   = datetime.now() if end_str is None else datetime.strptime(end_str, "%Y-%m-%d")
        end   = min(end, datetime.now())

        d = start
        while d <= end:
            key = f"{slug}:{d.strftime('%Y-%m-%d')}"
            if key not in cache:
                matches = _fetch_day(slug, d.strftime("%Y%m%d"))
                cache[key] = matches
                changed = True
                time.sleep(0.15)  # be polite to ESPN
            for m in cache.get(key, []):
                all_matches.append({**m, "tournament": name, "weight": weight})
            d += timedelta(days=1)

    if changed:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
        print(f"  Corner cache updated: {CACHE_FILE}")

    print(f"  Corner training data: {len(all_matches)} matches")
    return all_matches
