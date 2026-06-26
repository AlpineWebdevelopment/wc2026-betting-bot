/**
 * Fetch live WC 2026 match data from ESPN public API — port of sofascore.py.
 * Returns: score, minute, estimated xG, shots, possession, red cards.
 */
import { round } from "@/lib/util";

const HEADERS: Record<string, string> = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
};

const ESPN_URL =
  "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard";

const CACHE_TTL = 55_000; // ms — slightly under 60s auto-refresh
let _cache: { data: any; ts: number } | null = null;

// ESPN name → our model name
const NAME_MAP: Record<string, string> = {
  USA: "United States",
  "United States": "United States",
  "South Korea": "Korea Republic",
  "Korea Republic": "Korea Republic",
  "IR Iran": "Iran",
  "Côte d'Ivoire": "Ivory Coast",
  "Cote d'Ivoire": "Ivory Coast",
  "Congo, DR": "DR Congo",
  "DR Congo": "DR Congo",
  "Czech Republic": "Czech Republic",
  Czechia: "Czech Republic",
  "Bosnia and Herzegovina": "Bosnia and Herzegovina",
  "Bosnia & Herzegovina": "Bosnia and Herzegovina",
  "North Macedonia": "North Macedonia",
  "Cape Verde": "Cape Verde",
  "Cabo Verde": "Cape Verde",
};

function en(name: string): string {
  return NAME_MAP[name] ?? name;
}

async function getEspn(): Promise<any> {
  const now = Date.now();
  if (_cache && now - _cache.ts < CACHE_TTL) return _cache.data;
  const r = await fetch(ESPN_URL, {
    headers: HEADERS,
    cache: "no-store",
    signal: AbortSignal.timeout(10000),
  });
  if (!r.ok) throw new Error(`ESPN error: ${r.status}`);
  const data = await r.json();
  _cache = { data, ts: now };
  return data;
}

function estimateXg(shotsOnTarget: number, totalShots: number): number {
  const otherShots = Math.max(0, totalShots - shotsOnTarget);
  return round(shotsOnTarget * 0.25 + otherShots * 0.04, 2);
}

function parseStats(
  competitors: any[]
): [Record<string, number>, Record<string, number>] {
  const homeStats: Record<string, number> = {};
  const awayStats: Record<string, number> = {};
  for (const c of competitors) {
    const side = c.homeAway === "home" ? homeStats : awayStats;
    for (const stat of c.statistics ?? []) {
      const name = stat.name ?? "";
      const val = Number(stat.value);
      side[name] = Number.isFinite(val) ? val : 0;
    }
  }
  return [homeStats, awayStats];
}

function parseScore(competitors: any[]): [number, number] {
  let homeScore = 0;
  let awayScore = 0;
  for (const c of competitors) {
    const n = Number(c.score);
    const score = Number.isFinite(n) ? Math.trunc(n) : 0;
    if (c.homeAway === "home") homeScore = score;
    else awayScore = score;
  }
  return [homeScore, awayScore];
}

function parseTeamNames(competitors: any[]): [string, string, string, string] {
  let homeRaw = "";
  let awayRaw = "";
  for (const c of competitors) {
    const name = c.team?.displayName ?? "";
    if (c.homeAway === "home") homeRaw = name;
    else awayRaw = name;
  }
  return [homeRaw, en(homeRaw), awayRaw, en(awayRaw)];
}

function parseMinute(status: any): [number, number] {
  const clock: string = status.displayClock ?? "0'";
  const state = status.type?.state ?? "";
  if (state !== "in") return [0, 0];
  try {
    const clean = clock.replace(/'/g, "").trim();
    if (clean.includes("+")) {
      const [base, extra] = clean.split("+", 2);
      return [parseInt(base, 10), parseInt(extra, 10)];
    }
    return [parseInt(clean, 10), 0];
  } catch {
    return [0, 0];
  }
}

export interface LiveWcMatch {
  espn_id: string;
  home_team: string;
  away_team: string;
  home_team_raw: string;
  away_team_raw: string;
  home_score: number;
  away_score: number;
  minute: number;
  extra_time: number;
  status: string;
  xg_home: number;
  xg_away: number;
  xg_source: string;
  shots_on_target_home: number;
  shots_on_target_away: number;
  total_shots_home: number;
  total_shots_away: number;
  possession_home: number;
  possession_away: number;
  red_cards_home: number;
  red_cards_away: number;
}

export async function getLiveWcMatches(): Promise<LiveWcMatch[]> {
  let data: any;
  try {
    data = await getEspn();
  } catch (e) {
    console.log(`  ESPN error: ${e}`);
    return [];
  }

  const results: LiveWcMatch[] = [];
  for (const event of data.events ?? []) {
    const competitions = event.competitions ?? [];
    if (!competitions.length) continue;
    const comp = competitions[0];

    const status = comp.status ?? {};
    const state = status.type?.state ?? "";
    if (state !== "in") continue;

    const competitors = comp.competitors ?? [];
    const [homeRaw, homeEn, awayRaw, awayEn] = parseTeamNames(competitors);
    const [homeScore, awayScore] = parseScore(competitors);
    const [minute, extra] = parseMinute(status);
    const [homeStats, awayStats] = parseStats(competitors);

    const sotH = Math.trunc(homeStats.shotsOnTarget ?? 0);
    const sotA = Math.trunc(awayStats.shotsOnTarget ?? 0);
    const totH = Math.trunc(homeStats.totalShots ?? 0);
    const totA = Math.trunc(awayStats.totalShots ?? 0);
    const posH = homeStats.possessionPct ?? 50;
    const posA = awayStats.possessionPct ?? 50;

    results.push({
      espn_id: event.id ?? "",
      home_team: homeEn,
      away_team: awayEn,
      home_team_raw: homeRaw,
      away_team_raw: awayRaw,
      home_score: homeScore,
      away_score: awayScore,
      minute,
      extra_time: extra,
      status: status.type?.description ?? "",
      xg_home: estimateXg(sotH, totH),
      xg_away: estimateXg(sotA, totA),
      xg_source: "estimated",
      shots_on_target_home: sotH,
      shots_on_target_away: sotA,
      total_shots_home: totH,
      total_shots_away: totA,
      possession_home: round(posH, 1),
      possession_away: round(posA, 1),
      red_cards_home: 0,
      red_cards_away: 0,
    });
  }

  return results;
}
