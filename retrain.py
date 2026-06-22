"""
Fetches completed WC 2026 results from ESPN and re-trains the Poisson model.
"""

import os
import json
import time
import requests
import pandas as pd
from datetime import datetime, timedelta

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"

_HERE = os.path.dirname(os.path.abspath(__file__))
_CACHE_FILE = os.path.join(_HERE, "wc_results_cache.json")

# ESPN name → model name (copied from sofascore.py)
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


def _load_cache() -> dict:
    """Load the on-disk cache. Returns dict keyed by YYYY-MM-DD."""
    if os.path.exists(_CACHE_FILE):
        try:
            with open(_CACHE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cache(cache: dict) -> None:
    with open(_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def fetch_completed_wc_matches() -> list[dict]:
    """
    Scan from 2026-06-11 to today, one ESPN request per day using ?dates=YYYYMMDD.
    Filter for state == 'post' (completed).
    Cache results in wc_results_cache.json — only fetch dates not already cached.
    If today's date has state == 'in' matches (live), don't cache today yet.
    Returns list of match dicts.
    """
    cache = _load_cache()
    today = datetime.now().date()
    wc_start = datetime(2026, 6, 11).date()

    # Always re-fetch the last 3 days: WC matches often finish late US time
    # (= next morning in Europe), so early-cached days can be incomplete.
    refresh_cutoff = today - timedelta(days=3)
    for k in [k for k in list(cache.keys()) if not k.startswith("__tmp_")]:
        try:
            if datetime.strptime(k, "%Y-%m-%d").date() >= refresh_cutoff:
                del cache[k]
        except ValueError:
            pass

    current = wc_start

    while current <= today:
        date_str = current.strftime("%Y-%m-%d")
        espn_date = current.strftime("%Y%m%d")

        if date_str not in cache:
            print(f"  [retrain] Fetching ESPN for {date_str}...")
            try:
                r = requests.get(ESPN_URL, params={"dates": espn_date}, headers=_HEADERS, timeout=15)
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                print(f"  [retrain] ESPN error for {date_str}: {e}")
                current += timedelta(days=1)
                continue

            day_completed = []
            day_has_live = False

            for event in data.get("events", []):
                competitions = event.get("competitions", [])
                if not competitions:
                    continue
                comp = competitions[0]
                status = comp.get("status", {})
                state = status.get("type", {}).get("state", "")

                if state == "in":
                    day_has_live = True
                    continue

                if state != "post":
                    continue

                competitors = comp.get("competitors", [])
                home_raw = away_raw = ""
                home_score = away_score = 0
                home_corners = away_corners = None

                for c in competitors:
                    name = c.get("team", {}).get("displayName", "")
                    try:
                        score = int(float(c.get("score", 0)))
                    except (TypeError, ValueError):
                        score = 0
                    # Extract corner stats from statistics array
                    corners = None
                    for stat in c.get("statistics", []):
                        if stat.get("name", "").lower() in ("cornerkicks", "corners", "corner_kicks", "woncorners"):
                            try:
                                corners = int(float(stat.get("displayValue") or stat.get("value") or 0))
                            except Exception:
                                pass
                    if c.get("homeAway") == "home":
                        home_raw = name
                        home_score = score
                        home_corners = corners
                    else:
                        away_raw = name
                        away_score = score
                        away_corners = corners

                if not home_raw or not away_raw:
                    continue

                event_id = event.get("id", "")
                entry = {
                    "date": date_str,
                    "event_id": event_id,
                    "home_team": _en(home_raw),
                    "away_team": _en(away_raw),
                    "home_score": home_score,
                    "away_score": away_score,
                    "home_team_raw": home_raw,
                    "away_team_raw": away_raw,
                }
                if home_corners is not None and away_corners is not None:
                    entry["home_corners"] = home_corners
                    entry["away_corners"] = away_corners
                day_completed.append(entry)

            # Fetch summary stats (offsides, yellow cards, referee) for each completed match
            for entry in day_completed:
                if entry.get("event_id") and "home_offsides" not in entry:
                    try:
                        sr = requests.get(
                            f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary",
                            params={"event": entry["event_id"]},
                            headers=_HEADERS, timeout=10
                        )
                        sr.raise_for_status()
                        sdata = sr.json()
                        for team_box in sdata.get("boxscore", {}).get("teams", []):
                            side = team_box.get("homeAway", "")
                            stats = {s["name"].lower(): s.get("displayValue") or s.get("value", 0)
                                     for s in team_box.get("statistics", [])}
                            offsides = int(float(stats.get("offsides", 0) or 0))
                            yellow_key = next((k for k in stats if "yellow" in k), None)
                            yellows = int(float(stats.get(yellow_key, 0) or 0)) if yellow_key else 0
                            if side == "home":
                                entry["home_offsides"] = offsides
                                entry["home_yellows"]  = yellows
                            else:
                                entry["away_offsides"] = offsides
                                entry["away_yellows"]  = yellows
                        # Referee
                        for official in sdata.get("gameInfo", {}).get("officials", []):
                            pos = official.get("position", {}).get("displayName", "")
                            if official.get("order") == 1 or "referee" in pos.lower():
                                entry["referee"] = official.get("displayName") or official.get("fullName", "")
                                break
                        time.sleep(0.1)
                    except Exception as e:
                        print(f"  [retrain] summary fetch failed for {entry.get('event_id')}: {e}")

            # Always save completed matches even if live games are still running.
            # The last-3-days re-fetch ensures we pick up any matches that finish later.
            if day_has_live:
                print(f"  [retrain] {date_str} has live matches — saving {len(day_completed)} completed so far")
            cache[date_str] = day_completed

        current += timedelta(days=1)

    # Debug: count how many entries have offside data
    with_offsides = sum(1 for day in cache.values() if isinstance(day, list) for m in day if m.get("home_offsides") is not None)
    print(f"  [retrain] Entries with offside data: {with_offsides}")

    _save_cache(cache)

    # Collect all matches (including today's tmp if present)
    all_matches = []
    for k, v in sorted(cache.items()):
        if isinstance(v, list):
            all_matches.extend(v)

    print(f"  [retrain] Total completed WC matches found: {len(all_matches)}")
    return all_matches


def retrain_with_wc(wc_matches: list[dict], wc_weight: float = 5.0) -> dict:
    """
    Load historical data, append WC 2026 results, re-fit Poisson model, save params.
    Returns stats dict.
    """
    from data import fetch_data
    from model import PoissonModel

    print("  [retrain] Loading historical data...")
    df = fetch_data()

    if wc_matches:
        wc_rows = []
        for match in wc_matches:
            wc_rows.append({
                "date": pd.to_datetime(match["date"]),
                "home_team": match["home_team"],
                "away_team": match["away_team"],
                "home_score": match["home_score"],
                "away_score": match["away_score"],
                "weight": wc_weight,
                "tournament": "FIFA World Cup 2026",
            })
        wc_df = pd.DataFrame(wc_rows)
        combined_df = pd.concat([df, wc_df], ignore_index=True)
        print(f"  [retrain] Combined: {len(df)} historical + {len(wc_df)} WC 2026 matches")
    else:
        combined_df = df
        print("  [retrain] No WC matches to append — training on historical data only")

    print("  [retrain] Re-fitting Poisson model...")
    m = PoissonModel().fit(combined_df)

    import numpy as np
    params_path = os.path.join(_HERE, "model_params.json")
    with open(params_path, "w") as f:
        json.dump({
            "teams": m.teams,
            "params": m.params.tolist(),
            "avg_attack": m._avg_attack,
            "avg_defense": m._avg_defense,
        }, f)

    print(f"  [retrain] Model saved to {params_path}")
    return {
        "teams_count": len(m.teams),
        "historical_matches": len(df),
        "wc_matches": len(wc_matches),
    }


def run_retrain() -> dict:
    """Fetch WC results + retrain model. Returns matches and stats."""
    wc_matches = fetch_completed_wc_matches()
    stats = retrain_with_wc(wc_matches)
    return {
        "matches": wc_matches,
        "stats": stats,
    }


if __name__ == "__main__":
    result = run_retrain()
    print(f"\nDone! Stats: {result['stats']}")
    print(f"Matches used: {len(result['matches'])}")
