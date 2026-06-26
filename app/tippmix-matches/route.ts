import { NextResponse } from "next/server";
import { model } from "@/lib/model";
import { WC_HOSTS } from "@/lib/config";
import {
  findValueBets,
  findAllValueBets,
  isCornerBet,
  type ValueBet,
} from "@/lib/valuebets";
import { getTippmixPrematchCached } from "@/lib/store";
import { round } from "@/lib/util";

export const dynamic = "force-dynamic";

/** Fetch live Tippmix.hu odds, run model, return value bets. */
export async function GET() {
  let matches;
  try {
    matches = await getTippmixPrematchCached();
  } catch (e: any) {
    return NextResponse.json({ error: String(e?.message ?? e) }, { status: 500 });
  }

  const results = [];
  for (const m of matches) {
    const home = m.home_team;
    const away = m.away_team;
    const neutral = !WC_HOSTS.has(home);
    const probs = model.predict(home, away, neutral);

    const marketGroups = m.market_groups ?? [];
    let vbets: ValueBet[];
    if (m.is_wc && marketGroups.length) {
      vbets = findAllValueBets(marketGroups, probs, m.home_team_hu, m.away_team_hu);
    } else {
      vbets = findValueBets(
        probs,
        {
          home_odds: m.home_odds,
          draw_odds: m.draw_odds,
          away_odds: m.away_odds,
        },
        home,
        away
      );
    }

    // Corner bets now have their own dedicated tab/model — exclude them here.
    const goalBets = vbets.filter((v) => !isCornerBet(v));

    results.push({
      home_team: home,
      away_team: away,
      home_team_hu: m.home_team_hu,
      away_team_hu: m.away_team_hu,
      competition: m.competition,
      is_wc: m.is_wc,
      event_date: m.event_date,
      home_odds: m.home_odds,
      draw_odds: m.draw_odds,
      away_odds: m.away_odds,
      home_win: round(probs.home_win, 4),
      draw: round(probs.draw, 4),
      away_win: round(probs.away_win, 4),
      exp_home_goals: probs.exp_home_goals,
      exp_away_goals: probs.exp_away_goals,
      value_bets: goalBets,
      has_value: goalBets.some((v) => v.value),
    });
  }

  results.sort((a, b) => {
    const aw = Number(b.is_wc) - Number(a.is_wc);
    if (aw !== 0) return aw;
    const av = Number(b.has_value) - Number(a.has_value);
    if (av !== 0) return av;
    const ae = Math.max(0, ...a.value_bets.map((v) => v.edge_pct));
    const be = Math.max(0, ...b.value_bets.map((v) => v.edge_pct));
    return be - ae;
  });

  return NextResponse.json(results);
}
