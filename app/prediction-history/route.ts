import { NextResponse } from "next/server";
import { readJsonFile } from "@/lib/datafiles";
import { evalBet, type EvalBet } from "@/lib/evalBet";
import { HU_TO_EN } from "@/lib/tippmix";

export const dynamic = "force-dynamic";

interface ResultMatch {
  home_team: string;
  away_team: string;
  home_team_raw?: string;
  away_team_raw?: string;
  home_score: number;
  away_score: number;
  home_corners?: number | null;
  away_corners?: number | null;
  home_offsides?: number | null;
  away_offsides?: number | null;
}

interface LogEntry {
  logged_at?: string;
  match_date?: string;
  home_team?: string;
  away_team?: string;
  home_team_hu?: string;
  away_team_hu?: string;
  primary_goal?: EvalBet | null;
  secondary_goal?: EvalBet | null;
  best_corner?: EvalBet | null;
}

const norm = (s: string) =>
  s.toLowerCase().replace(/-/g, " ").replace(/&/g, "and").trim();

/** Logged predictions with actual results and outcome evaluation. */
export async function GET() {
  const log = await readJsonFile<LogEntry[]>("predictions_log.json", []);
  const cache = await readJsonFile<Record<string, ResultMatch[]>>(
    "wc_results_cache.json",
    {}
  );

  // Flatten results cache: "norm_home|norm_away" -> match dict
  const allResults = new Map<string, ResultMatch>();
  for (const dayMatches of Object.values(cache)) {
    if (!Array.isArray(dayMatches)) continue;
    for (const rm of dayMatches) {
      allResults.set(`${norm(rm.home_team)}|${norm(rm.away_team)}`, rm);
      if (rm.home_team_raw)
        allResults.set(
          `${norm(rm.home_team_raw)}|${norm(rm.away_team_raw ?? "")}`,
          rm
        );
    }
  }

  const findResult = (home: string, away: string): ResultMatch | undefined => {
    const direct = allResults.get(`${norm(home)}|${norm(away)}`);
    if (direct) return direct;
    const homeEn = HU_TO_EN[home] ?? home;
    const awayEn = HU_TO_EN[away] ?? away;
    return allResults.get(`${norm(homeEn)}|${norm(awayEn)}`);
  };

  const sorted = [...log].sort((a, b) =>
    `${a.match_date ?? ""}${a.logged_at ?? ""}`.localeCompare(
      `${b.match_date ?? ""}${b.logged_at ?? ""}`
    )
  );

  const out = sorted.map((entry) => {
    const home = entry.home_team ?? "";
    const away = entry.away_team ?? "";
    const homeHu = entry.home_team_hu ?? home;
    const awayHu = entry.away_team_hu ?? away;
    const result = findResult(home, away);

    let hs: number | null = null;
    let as_: number | null = null;
    let hc: number | null = null;
    let ac: number | null = null;
    let hos: number | null = null;
    let aos: number | null = null;
    if (result) {
      hs = result.home_score;
      as_ = result.away_score;
      hc = result.home_corners ?? null;
      ac = result.away_corners ?? null;
      hos = result.home_offsides ?? null;
      aos = result.away_offsides ?? null;
    }

    const ev = (bet: EvalBet | null | undefined): string =>
      result ? evalBet(bet, hs, as_, homeHu, awayHu, hc, ac, hos, aos) : "pending";

    const corner = entry.best_corner;
    return {
      logged_at: entry.logged_at ?? "",
      match_date: entry.match_date ?? "",
      home_team_hu: homeHu,
      away_team_hu: awayHu,
      home_score: hs,
      away_score: as_,
      home_corners: hc,
      away_corners: ac,
      home_offsides: hos,
      away_offsides: aos,
      has_result: result !== undefined,
      primary_goal: entry.primary_goal,
      primary_result: ev(entry.primary_goal),
      secondary_goal: entry.secondary_goal,
      secondary_result: ev(entry.secondary_goal),
      best_corner: corner,
      corner_result: corner ? ev(corner) : null,
    };
  });

  return NextResponse.json(out);
}
