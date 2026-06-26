import { NextResponse } from "next/server";
import { model } from "@/lib/model";
import { WC_HOSTS } from "@/lib/config";
import { bestOdds } from "@/lib/odds";
import { findValueBets } from "@/lib/valuebets";
import { getLiveOdds } from "@/lib/store";
import { round } from "@/lib/util";

export const dynamic = "force-dynamic";

/** All matches that have live odds, with full value bet analysis. */
export async function GET() {
  const liveOdds = await getLiveOdds();
  const results = [];

  for (const m of Object.values(liveOdds)) {
    const home = m.home_team;
    const away = m.away_team;
    const neutral = !WC_HOSTS.has(home);
    const probs = model.predict(home, away, neutral);
    const vbets = findValueBets(probs, bestOdds(m), home, away);
    results.push({
      home_team: home,
      away_team: away,
      commence_time: m.commence_time ?? "",
      home_win: round(probs.home_win, 4),
      draw: round(probs.draw, 4),
      away_win: round(probs.away_win, 4),
      exp_home_goals: probs.exp_home_goals,
      exp_away_goals: probs.exp_away_goals,
      value_bets: vbets,
      has_value: vbets.some((v) => v.value),
    });
  }

  results.sort((a, b) => {
    const av = Number(b.has_value) - Number(a.has_value);
    if (av !== 0) return av;
    const ae = Math.max(0, ...a.value_bets.map((v) => v.edge_pct));
    const be = Math.max(0, ...b.value_bets.map((v) => v.edge_pct));
    return be - ae;
  });

  return NextResponse.json(results);
}
