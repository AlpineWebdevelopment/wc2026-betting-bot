import { NextResponse } from "next/server";
import { model } from "@/lib/model";
import { WC_HOSTS } from "@/lib/config";
import { bestOdds } from "@/lib/odds";
import { findValueBets } from "@/lib/valuebets";
import { getLiveOdds } from "@/lib/store";
import { round } from "@/lib/util";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const home = (searchParams.get("home") ?? "").trim();
  const away = (searchParams.get("away") ?? "").trim();
  let neutral = (searchParams.get("neutral") ?? "true").toLowerCase() !== "false";

  if (!home || !away)
    return NextResponse.json(
      { error: "Provide home and away team names." },
      { status: 400 }
    );
  if (home === away)
    return NextResponse.json({ error: "Teams must be different." }, { status: 400 });

  // Hosts get home advantage at their own venues
  if (WC_HOSTS.has(home)) neutral = false;

  const probs = model.predict(home, away, neutral);

  const liveOdds = await getLiveOdds();
  const matchData = liveOdds[`${home}|${away}`];
  const reversed = liveOdds[`${away}|${home}`];
  let valueBets: ReturnType<typeof findValueBets> = [];

  if (matchData) {
    valueBets = findValueBets(probs, bestOdds(matchData), home, away);
  } else if (reversed) {
    // Odds fetched with teams swapped — flip probabilities
    const flipped = {
      ...probs,
      home_win: probs.away_win,
      away_win: probs.home_win,
      exp_home_goals: probs.exp_away_goals,
      exp_away_goals: probs.exp_home_goals,
    };
    valueBets = findValueBets(flipped, bestOdds(reversed), away, home);
  }

  return NextResponse.json({
    home_team: home,
    away_team: away,
    home_win: round(probs.home_win, 4),
    draw: round(probs.draw, 4),
    away_win: round(probs.away_win, 4),
    exp_home_goals: probs.exp_home_goals,
    exp_away_goals: probs.exp_away_goals,
    value_bets: valueBets,
  }); // score_matrix intentionally excluded from public response
}
