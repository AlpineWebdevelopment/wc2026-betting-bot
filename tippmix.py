"""
Tippmix.hu odds fetcher.
Calls the public tippmix.hu JSON API directly with `requests` — no browser needed.
The list endpoints (best-games / last-minute) are POST; the per-event market
endpoint is GET. Maps Hungarian team names to English for the Poisson model.
"""
import requests
from concurrent.futures import ThreadPoolExecutor

API_BASE = "https://api.tippmix.hu"

# tippmix's API rejects requests without these (the list endpoints 404 otherwise).
_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=UTF-8",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)",
    "Referer": "https://www.tippmix.hu/",
    "Accept-Language": "hu-HU",
}

# Hungarian name → English name mapping for WC 2026 teams
HU_TO_EN: dict[str, str] = {
    "Mexikó": "Mexico",
    "Dél-Afrika": "South Africa",
    "Marokkó": "Morocco",
    "Portugália": "Portugal",
    "Argentína": "Argentina",
    "Szaúd-Arábia": "Saudi Arabia",
    "Lengyelország": "Poland",
    "Németország": "Germany",
    "Japán": "Japan",
    "Spanyolország": "Spain",
    "Costa Rica": "Costa Rica",
    "Belgium": "Belgium",
    "Kanada": "Canada",
    "Horvátország": "Croatia",
    "Szerbia": "Serbia",
    "Brazília": "Brazil",
    "Svájc": "Switzerland",
    "Kamerun": "Cameroon",
    "Dél-Korea": "Korea Republic",
    "Ghána": "Ghana",
    "Uruguay": "Uruguay",
    "Franciaország": "France",
    "Ausztrália": "Australia",
    "Dánia": "Denmark",
    "Tunézia": "Tunisia",
    "Szenegál": "Senegal",
    "Hollandia": "Netherlands",
    "Ecuador": "Ecuador",
    "Anglia": "England",
    "Irán": "Iran",
    "Wales": "Wales",
    "Katar": "Qatar",
    "Egyesült Államok": "United States",
    "USA": "United States",
    "Panamá": "Panama",
    "Jamaika": "Jamaica",
    "Bolívia": "Bolivia",
    "Venezuela": "Venezuela",
    "Kolumbia": "Colombia",
    "Chile": "Chile",
    "Peru": "Peru",
    "Paraguay": "Paraguay",
    "Honduras": "Honduras",
    "Nigéria": "Nigeria",
    "Elefántcsontpart": "Ivory Coast",
    "Mali": "Mali",
    "Kenya": "Kenya",
    "Egyiptom": "Egypt",
    "DR Kongó": "DR Congo",
    "Algéria": "Algeria",
    "Szlovénia": "Slovenia",
    "Ausztria": "Austria",
    "Törökország": "Turkey",
    "Csehország": "Czech Republic",
    "Új-Zéland": "New Zealand",
    "Norvégia": "Norway",
    "Svédország": "Sweden",
    "Skócia": "Scotland",
    "Görögország": "Greece",
    "Románia": "Romania",
    "Ukrajna": "Ukraine",
    "Magyarország": "Hungary",
    "Olaszország": "Italy",
    "Bosznia-Hercegovina": "Bosnia & Herzegovina",
}


def _en(name: str) -> str:
    return HU_TO_EN.get(name, name)


def _parse_events(data: dict) -> list[dict]:
    """Extract 1X2 football matches from a tippmix API response."""
    matches = []
    for sport_block in data.get("data", []):
        if sport_block.get("sportId") != 1:
            continue
        for ev in sport_block.get("events", []):
            if ev.get("isLive") or ev.get("bettingStatus") != 0:
                continue
            participants = ev.get("eventParticipants", [])
            if len(participants) < 2:
                continue

            home_hu = participants[0]["participantName"]
            away_hu = participants[1]["participantName"]
            home_en = _en(home_hu)
            away_en = _en(away_hu)
            event_date = ev.get("eventDate", "")

            # Find 1X2 market
            market_1x2 = next(
                (m for m in ev.get("markets", []) if m.get("marketName") == "1X2"),
                None
            )
            if not market_1x2:
                continue

            outcomes = {o["outcomeNo"]: o["fixedOdds"] for o in market_1x2.get("outcomes", [])}
            home_odds = outcomes.get(1)
            draw_odds = outcomes.get(2)
            away_odds = outcomes.get(3)

            if not all([home_odds, draw_odds, away_odds]):
                continue

            # Only include if it's a WC competition
            competition = ev.get("competitionName", "")
            is_wc = any(c.get("name") == "vb" for c in ev.get("competitions", []))

            matches.append({
                "home_team_hu": home_hu,
                "away_team_hu": away_hu,
                "home_team": home_en,
                "away_team": away_en,
                "competition": competition,
                "is_wc": is_wc,
                "event_date": event_date,
                "home_odds": home_odds,
                "draw_odds": draw_odds,
                "away_odds": away_odds,
                "event_id": ev.get("eventId"),
            })

    return matches


def _fetch_event_markets(event_id: int) -> list[dict]:
    """Fetch full market groups for a single event (GET /v2/tippmix/event/{id})."""
    try:
        r = requests.get(f"{API_BASE}/v2/tippmix/event/{event_id}",
                         headers=_HEADERS, timeout=20)
        r.raise_for_status()
        return r.json().get("event", {}).get("marketGroups", [])
    except Exception:
        return []


def _fetch_events_list() -> dict | None:
    """POST the list endpoints (best-games, then last-minute) — first 200 wins."""
    for path in ("/tippmix/best-games", "/tippmix/last-minute"):
        try:
            r = requests.post(f"{API_BASE}{path}", headers=_HEADERS, json={}, timeout=20)
            if r.status_code == 200:
                return r.json()
        except Exception:
            continue
    return None


def get_tippmix_matches() -> list[dict]:
    """Returns football matches with Tippmix odds and full market data for WC matches."""
    print("  Fetching Tippmix.hu odds via API...")
    data = _fetch_events_list()
    base_matches = _parse_events(data) if data else []

    # Fetch full market data for WC matches in parallel (keeps us well under
    # Vercel's request time limit even with a dozen WC fixtures).
    wc = [m for m in base_matches if m.get("is_wc") and m.get("event_id")]
    if wc:
        with ThreadPoolExecutor(max_workers=8) as ex:
            groups = list(ex.map(lambda m: _fetch_event_markets(m["event_id"]), wc))
        for m, mgs in zip(wc, groups):
            m["market_groups"] = mgs

    for m in base_matches:
        m.setdefault("market_groups", [])

    other = [m for m in base_matches if not m["is_wc"]]
    print(f"  Got {len(wc)} WC matches + {len(other)} other football matches from Tippmix")
    return base_matches
