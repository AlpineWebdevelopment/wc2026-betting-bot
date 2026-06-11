"""
Tippmix.hu odds fetcher.
Uses Playwright to load tippmix.hu and intercept the API — no scraping, clean JSON.
Maps Hungarian team names to English for the Poisson model.
"""
import asyncio, json
from datetime import datetime
from playwright.async_api import async_playwright

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


async def _fetch_via_playwright() -> list[dict]:
    saved = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="hu-HU",
        )

        async def on_response(resp):
            for target in ["best-games", "last-minute"]:
                if target in resp.url and resp.status == 200 and target not in saved:
                    try:
                        saved[target] = await resp.json()
                    except:
                        pass

        page = await ctx.new_page()
        page.on("response", on_response)
        try:
            await page.goto("https://www.tippmix.hu", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(5)
        except:
            pass
        await browser.close()

    # Prefer best-games (curated), fall back to last-minute
    for key in ["best-games", "last-minute"]:
        if key in saved:
            return _parse_events(saved[key])
    return []


def get_tippmix_matches() -> list[dict]:
    """Synchronous wrapper — returns list of WC matches with Tippmix odds."""
    print("  Fetching Tippmix.hu odds via browser...")
    matches = asyncio.run(_fetch_via_playwright())
    wc = [m for m in matches if m["is_wc"]]
    all_football = [m for m in matches if not m["is_wc"]]
    print(f"  Got {len(wc)} WC matches + {len(all_football)} other football matches from Tippmix")
    return matches
