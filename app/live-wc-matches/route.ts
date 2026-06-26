import { NextResponse } from "next/server";
import { model } from "@/lib/model";
import { WC_HOSTS, TELEGRAM_BANKROLL } from "@/lib/config";
import { getLiveWcMatches } from "@/lib/sofascore";
import { getTippmixLiveCached } from "@/lib/store";
import {
  liveProbs,
  liveValueBets,
  findLiveValueBetsFromMarkets,
} from "@/lib/liveModel";
import type { TippmixMatch } from "@/lib/tippmix";
import { round } from "@/lib/util";

export const dynamic = "force-dynamic";

const tkey = (h: string, a: string) =>
  `${h.toLowerCase().trim()}|${a.toLowerCase().trim()}`;

/** Live WC matches: ESPN stats + Tippmix live odds → full value bet analysis. */
export async function GET() {
  let espnMatches;
  try {
    espnMatches = await getLiveWcMatches();
  } catch (e: any) {
    return NextResponse.json({ error: String(e?.message ?? e) }, { status: 500 });
  }

  const { data: tippmixLive, age: cacheAge } = await getTippmixLiveCached();

  // Index Tippmix live matches by team pair for fast lookup
  const tippmixIndex = new Map<string, TippmixMatch>();
  for (const tm of tippmixLive) {
    if (tm.is_wc) tippmixIndex.set(tkey(tm.home_team, tm.away_team), tm);
  }

  const bankroll = TELEGRAM_BANKROLL;
  const results = [];

  for (const m of espnMatches) {
    const home = m.home_team;
    const away = m.away_team;
    const neutral = !WC_HOSTS.has(home);

    let preXgH: number;
    let preXgA: number;
    try {
      const pre = model.predict(home, away, neutral);
      preXgH = pre.exp_home_goals;
      preXgA = pre.exp_away_goals;
    } catch {
      preXgH = 1.2;
      preXgA = 1.0;
    }

    const lp = liveProbs({
      preXgHome: preXgH,
      preXgAway: preXgA,
      minute: m.minute + (m.extra_time ?? 0),
      homeScore: m.home_score,
      awayScore: m.away_score,
      liveXgHome: m.xg_home,
      liveXgAway: m.xg_away,
      redCardsHome: m.red_cards_home,
      redCardsAway: m.red_cards_away,
      possessionHome: m.possession_home,
    });

    const tmMatch = tippmixIndex.get(tkey(home, away));
    const hasTippmixOdds = Boolean(
      tmMatch && (tmMatch.market_groups?.length ?? 0) > 0
    );

    const liveVbets = hasTippmixOdds
      ? findLiveValueBetsFromMarkets(
          tmMatch!.market_groups!,
          lp,
          bankroll,
          5.0
        )
      : liveValueBets(lp, 5.0);

    results.push({
      ...m,
      pre_xg_home: round(preXgH, 2),
      pre_xg_away: round(preXgA, 2),
      live_probs: lp,
      live_bets: liveVbets,
      has_tippmix_odds: hasTippmixOdds,
    });
  }

  return NextResponse.json({ matches: results, tippmix_cache_age: cacheAge });
}
