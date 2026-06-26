import { NextResponse } from "next/server";
import { cornerModel } from "@/lib/cornerModel";
import { findCornerValueBets } from "@/lib/cornerValuebets";
import { getTippmixPrematchCached } from "@/lib/store";

export const dynamic = "force-dynamic";

/** Corner model value bets for all WC matches. */
export async function GET() {
  let matches;
  try {
    matches = await getTippmixPrematchCached();
  } catch (e: any) {
    return NextResponse.json({ error: String(e?.message ?? e) }, { status: 500 });
  }

  const results = [];
  for (const m of matches) {
    if (!m.is_wc) continue;
    const home = m.home_team;
    const away = m.away_team;

    let cornerProbs;
    try {
      cornerProbs = cornerModel.predict(home, away);
    } catch {
      continue;
    }
    const mgs = m.market_groups ?? [];
    if (!mgs.length) continue;

    const vbets = findCornerValueBets(mgs, cornerProbs, m.home_team_hu, m.away_team_hu);
    results.push({
      home_team: home,
      away_team: away,
      home_team_hu: m.home_team_hu,
      away_team_hu: m.away_team_hu,
      event_date: m.event_date ?? "",
      exp_home_corners: cornerProbs.exp_home_corners,
      exp_away_corners: cornerProbs.exp_away_corners,
      exp_total_corners: cornerProbs.exp_total_corners,
      value_bets: vbets,
      has_value: vbets.some((v) => v.value),
    });
  }

  results.sort((a, b) => (a.event_date || "9999").localeCompare(b.event_date || "9999"));
  return NextResponse.json(results);
}
