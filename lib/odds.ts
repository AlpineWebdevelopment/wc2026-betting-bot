/**
 * Fetches live bookmaker odds from The Odds API (free tier) — port of odds.py.
 */
import { THE_ODDS_API_KEY, ODDS_REGION } from "@/lib/config";

const BASE_URL = "https://api.the-odds-api.com/v4";

const WC_SPORT_KEYS = [
  "soccer_fifa_world_cup_2026",
  "soccer_fifa_world_cup",
  "soccer_international",
];

export interface Bookmaker {
  name: string;
  home_odds?: number | null;
  draw_odds?: number | null;
  away_odds?: number | null;
}
export interface OddsMatch {
  home_team: string;
  away_team: string;
  commence_time: string;
  bookmakers: Bookmaker[];
}

export async function getWcOdds(): Promise<OddsMatch[]> {
  if (!THE_ODDS_API_KEY) return [];

  for (const sportKey of WC_SPORT_KEYS) {
    const url = new URL(`${BASE_URL}/sports/${sportKey}/odds/`);
    url.searchParams.set("apiKey", THE_ODDS_API_KEY);
    url.searchParams.set("regions", ODDS_REGION);
    url.searchParams.set("markets", "h2h");
    url.searchParams.set("oddsFormat", "decimal");

    const resp = await fetch(url, {
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });
    if (resp.status === 404) continue; // try next sport key
    if (!resp.ok) throw new Error(`The Odds API error: ${resp.status}`);

    const data = await resp.json();
    const remaining = resp.headers.get("x-requests-remaining") ?? "?";
    console.log(
      `  Fetched odds for ${data.length} matches. Requests remaining: ${remaining}/month`
    );
    return parse(data);
  }

  console.log("  No WC odds found via The Odds API (tournament may not be live yet).");
  return [];
}

function parse(raw: any[]): OddsMatch[] {
  const matches: OddsMatch[] = [];
  for (const game of raw) {
    const books: Bookmaker[] = [];
    for (const bm of game.bookmakers ?? []) {
      for (const market of bm.markets ?? []) {
        if (market.key !== "h2h") continue;
        const outcomes: Record<string, number> = {};
        for (const o of market.outcomes ?? []) outcomes[o.name] = o.price;
        books.push({
          name: bm.title,
          home_odds: outcomes[game.home_team] ?? null,
          draw_odds: outcomes["Draw"] ?? null,
          away_odds: outcomes[game.away_team] ?? null,
        });
      }
    }
    matches.push({
      home_team: game.home_team,
      away_team: game.away_team,
      commence_time: game.commence_time ?? "",
      bookmakers: books,
    });
  }
  return matches;
}

/** Returns the best (highest) decimal odds across all bookmakers. */
export function bestOdds(match: OddsMatch): {
  home_odds: number | null;
  draw_odds: number | null;
  away_odds: number | null;
} {
  const best: { home_odds: number | null; draw_odds: number | null; away_odds: number | null } =
    { home_odds: null, draw_odds: null, away_odds: null };
  for (const bm of match.bookmakers) {
    (["home_odds", "draw_odds", "away_odds"] as const).forEach((key) => {
      const val = bm[key];
      if (val && (best[key] === null || val > (best[key] as number)))
        best[key] = val;
    });
  }
  return best;
}
