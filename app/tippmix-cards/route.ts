import { NextResponse } from "next/server";
import { cardModel } from "@/lib/cardModel";
import { findCardValueBets } from "@/lib/cardValuebets";
import { getTippmixPrematchCached } from "@/lib/store";
import { readJsonFile } from "@/lib/datafiles";

export const dynamic = "force-dynamic";

interface ResultMatch {
  home_team?: string;
  away_team?: string;
  referee?: string;
}

/** Card model value bets for all WC matches. */
export async function GET() {
  let matches;
  try {
    matches = await getTippmixPrematchCached();
  } catch (e: any) {
    return NextResponse.json({ error: String(e?.message ?? e) }, { status: 500 });
  }

  // Load WC results cache once for referee lookups (may be absent on serverless).
  const wc = await readJsonFile<Record<string, ResultMatch[]>>(
    "wc_results_cache.json",
    {}
  );
  const refMap = new Map<string, string>();
  for (const day of Object.values(wc)) {
    if (!Array.isArray(day)) continue;
    for (const mx of day) {
      if (mx.referee && mx.home_team && mx.away_team)
        refMap.set(`${mx.home_team}|${mx.away_team}`, mx.referee);
    }
  }

  const results = [];
  for (const m of matches) {
    if (!m.is_wc) continue;
    const home = m.home_team;
    const away = m.away_team;
    const referee = refMap.get(`${home}|${away}`) ?? null;

    let cardProbs;
    try {
      cardProbs = cardModel.predict(home, away, referee);
    } catch {
      continue;
    }
    const mgs = m.market_groups ?? [];
    if (!mgs.length) continue;

    const vbets = findCardValueBets(mgs, cardProbs, m.home_team_hu, m.away_team_hu);
    results.push({
      home_team: home,
      away_team: away,
      home_team_hu: m.home_team_hu,
      away_team_hu: m.away_team_hu,
      event_date: m.event_date ?? "",
      exp_home_cards: cardProbs.exp_home_cards,
      exp_away_cards: cardProbs.exp_away_cards,
      exp_total_cards: cardProbs.exp_total_cards,
      ref_factor: cardProbs.ref_factor,
      referee,
      ref_known: cardProbs.ref_known,
      value_bets: vbets,
      has_value: vbets.some((v) => v.value),
    });
  }

  results.sort((a, b) => (a.event_date || "9999").localeCompare(b.event_date || "9999"));
  return NextResponse.json(results);
}
