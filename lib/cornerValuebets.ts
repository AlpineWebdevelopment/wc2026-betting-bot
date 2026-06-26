/**
 * Find value bets in Tippmix corner markets using the CornerModel.
 * Port of corner_valuebets.py.
 */
import { MIN_EDGE_PCT } from "@/lib/config";
import { round } from "@/lib/util";
import type { CornerProbs } from "@/lib/cornerModel";
import type { MarketGroup } from "@/lib/valuebets";
import type { ValueBet } from "@/lib/valuebets";

export function findCornerValueBets(
  marketGroups: MarketGroup[],
  cornerProbs: CornerProbs,
  homeHu: string,
  awayHu: string
): ValueBet[] {
  const ouProbs = cornerProbs.ou_probs ?? {};
  const teamOu = cornerProbs.team_ou ?? {};
  const results: ValueBet[] = [];

  for (const mg of marketGroups) {
    const groupName = mg.name ?? "";
    if (groupName !== "Szögletek") continue;

    for (const market of mg.markets ?? []) {
      const mktName = market.name ?? "";
      for (const outcome of market.outcomes ?? []) {
        const outName = outcome.name ?? "";
        const rawOdds = outcome.fixedOdds || outcome.odds;
        if (!rawOdds || Number(rawOdds) <= 1.0) continue;
        const oddsVal = Number(rawOdds);

        const modelProb = getModelProb(mktName, outName, ouProbs, teamOu, homeHu, awayHu);
        if (modelProb === null || modelProb <= 0) continue;

        const implied = 1.0 / oddsVal;
        const edge = (modelProb - implied) * 100;
        const kelly = Math.max(0.0, (modelProb * oddsVal - 1.0) / (oddsVal - 1.0));

        results.push({
          market: mktName,
          market_group: "Szögletek",
          outcome: outName,
          model_prob: round(modelProb * 100, 1),
          implied_prob: round(implied * 100, 1),
          best_odds: oddsVal,
          fair_odds: round(1.0 / modelProb, 2),
          edge_pct: round(edge, 1),
          kelly_pct: round(kelly * 100, 1),
          value: edge >= MIN_EDGE_PCT,
        });
      }
    }
  }

  results.sort(
    (a, b) => Number(b.value) - Number(a.value) || b.edge_pct - a.edge_pct
  );
  return results;
}

/** Extract numeric line from text like 'Több, mint 9,5' → 9.5 */
function parseLine(text: string): number | null {
  let m = text.match(/(\d+)[,.](\d+)/);
  if (m) return parseFloat(`${m[1]}.${m[2]}`);
  m = text.match(/(\d+)/);
  if (m) return parseFloat(m[1]) + 0.5;
  return null;
}

function getModelProb(
  mktName: string,
  outName: string,
  ouProbs: Record<number, { over: number; under: number }>,
  teamOu: Record<number, { home_over: number; away_over: number }>,
  homeHu: string,
  awayHu: string
): number | null {
  const line = parseLine(outName) ?? parseLine(mktName);
  if (line === null) return null;

  const outLower = outName.toLowerCase();
  const mktLower = mktName.toLowerCase();

  const isOver = ["több", "over", "felett"].some((w) => outLower.includes(w));
  const isUnder = ["kevesebb", "under", "alatt"].some((w) => outLower.includes(w));

  const isHome = mktLower.includes(homeHu.toLowerCase()) || mktLower.includes("hazai");
  const isAway = mktLower.includes(awayHu.toLowerCase()) || mktLower.includes("vendég");

  if (isHome && line in teamOu)
    return isOver
      ? teamOu[line].home_over
      : isUnder
      ? 1 - teamOu[line].home_over
      : null;
  if (isAway && line in teamOu)
    return isOver
      ? teamOu[line].away_over
      : isUnder
      ? 1 - teamOu[line].away_over
      : null;

  if (line in ouProbs) {
    if (isOver) return ouProbs[line].over;
    if (isUnder) return ouProbs[line].under;
  }

  return null;
}
