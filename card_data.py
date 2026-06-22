"""
Fetches historical international match yellow card + referee data from ESPN.
Used to train the CardModel.
"""
import requests, json, os, time
from datetime import datetime, timedelta

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "card_training_cache.json")

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

_YELLOW_STAT_NAMES = ("yellowcards", "yellow_cards", "yellowcard", "yellowcards")


def _fetch_summary(slug, event_id):
    """Fetch the ESPN summary API for a single event to get referee and fallback card stats."""
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/summary?event={event_id}"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  ESPN summary {slug} event={event_id}: {e}")
        return {}


def _extract_referee(sdata):
    """Extract referee name from summary data."""
    officials = sdata.get("gameInfo", {}).get("officials", [])
    for official in officials:
        order = official.get("order")
        pos_name = official.get("position", {}).get("displayName", "").lower()
        if order == 1 or "referee" in pos_name:
            return official.get("displayName") or official.get("fullName", "") or None
    return None


def _extract_yellows_from_boxscore(sdata):
    """Fallback: extract yellow card counts from boxscore."""
    home_yellows = away_yellows = None
    teams_box = sdata.get("boxscore", {}).get("teams", [])
    for i, team_box in enumerate(teams_box):
        stats = team_box.get("statistics", [])
        for stat in stats:
            key = stat.get("name", "").lower()
            if "yellow" in key:
                try:
                    val = int(float(stat.get("displayValue") or stat.get("value") or 0))
                    # ESPN boxscore teams: index 0 = away, index 1 = home (common pattern)
                    if i == 0:
                        away_yellows = val
                    else:
                        home_yellows = val
                except Exception:
                    pass
    return home_yellows, away_yellows


def _fetch_day(slug, date_str):
    """Fetch completed matches with yellow card stats for one day."""
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={date_str}"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  ESPN {slug} {date_str}: {e}")
        return []

    partial_matches = []
    for event in data.get("events", []):
        comps = event.get("competitions", [])
        if not comps: continue
        comp = comps[0]
        state = comp.get("status", {}).get("type", {}).get("state", "")
        if state != "post": continue

        event_id = event.get("id", "")
        competitors = comp.get("competitors", [])
        home_team = away_team = ""
        home_yellows = away_yellows = None

        for c in competitors:
            name = _en(c.get("team", {}).get("displayName", ""))
            yellows = None
            for stat in c.get("statistics", []):
                if stat.get("name", "").lower() in _YELLOW_STAT_NAMES:
                    try:
                        yellows = int(float(stat.get("displayValue") or stat.get("value") or 0))
                    except Exception:
                        pass
            if c.get("homeAway") == "home":
                home_team = name
                home_yellows = yellows
            else:
                away_team = name
                away_yellows = yellows

        if home_team and away_team:
            partial_matches.append({
                "event_id":    event_id,
                "home_team":   home_team,
                "away_team":   away_team,
                "home_yellows": home_yellows,
                "away_yellows": away_yellows,
            })

    # For each match, fetch summary to get referee (and fallback card stats)
    matches = []
    date_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}" if len(date_str) == 8 else date_str
    for pm in partial_matches:
        event_id = pm["event_id"]
        home_yellows = pm["home_yellows"]
        away_yellows = pm["away_yellows"]
        referee = None

        if event_id:
            sdata = _fetch_summary(slug, event_id)
            time.sleep(0.1)

            referee = _extract_referee(sdata)

            # Fallback: get yellow cards from boxscore if missing from scoreboard
            if home_yellows is None or away_yellows is None:
                bh, ba = _extract_yellows_from_boxscore(sdata)
                if home_yellows is None:
                    home_yellows = bh
                if away_yellows is None:
                    away_yellows = ba

        if home_yellows is None or away_yellows is None:
            continue

        matches.append({
            "date":         date_fmt,
            "event_id":     event_id,
            "home_team":    pm["home_team"],
            "away_team":    pm["away_team"],
            "home_yellows": int(home_yellows),
            "away_yellows": int(away_yellows),
            "referee":      referee,
        })

    return matches


def fetch_card_training_data():
    """
    Fetch yellow card + referee data for all configured tournaments.
    Caches results in card_training_cache.json.
    Returns list of match dicts.
    """
    # Load existing cache
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                cache = json.load(f)
        except Exception:
            cache = {}

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
        print(f"  Card cache updated: {CACHE_FILE}")

    print(f"  Card training data: {len(all_matches)} matches")
    return all_matches
