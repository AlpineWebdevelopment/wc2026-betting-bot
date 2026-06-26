/**
 * Find value bets in Tippmix card (yellow card) markets using the CardModel.
 * Port of card_valuebets.py.
 */
import { MIN_EDGE_PCT } from "@/lib/config";
import { round } from "@/lib/util";
import type { CardProbs } from "@/lib/cardModel";
import type { MarketGroup, ValueBet } from "@/lib/valuebets";

export function findCardValueBets(
  marketGroups: MarketGroup[],
  cardProbs: CardProbs,
  _homeHu: string,
  _awayHu: string
): ValueBet[] {
  const ouProbs = cardProbs.ou_probs ?? {};
  const results: ValueBet[] = [];

  for (const mg of marketGroups) {
    for (const market of mg.markets ?? []) {
      const mktName = market.name ?? "";

      // Only card total markets (skip player card markets)
      if (!mktName.toLowerCase().includes("büntetőlap-szám")) continue;

      const isHalftime = mktName.toLowerCase().includes("félidő");

      for (const outcome of market.outcomes ?? []) {
        const outName = outcome.name ?? "";
        const rawOdds = outcome.fixedOdds || outcome.odds;
        if (!rawOdds || Number(rawOdds) <= 1.0) continue;
        const oddsVal = Number(rawOdds);

        const modelProb = getModelProb(mktName, outName, ouProbs, isHalftime);
        if (modelProb === null || modelProb <= 0) continue;

        const implied = 1.0 / oddsVal;
        const edge = (modelProb - implied) * 100;
        const kelly = Math.max(0.0, (modelProb * oddsVal - 1.0) / (oddsVal - 1.0));

        results.push({
          market: mktName,
          market_group: "Kártyák",
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
  isHalftime: boolean
): number | null {
  const line = parseLine(outName) ?? parseLine(mktName);
  if (line === null) return null;

  const outLower = outName.toLowerCase();
  const isOver = ["több", "over", "felett"].some((w) => outLower.includes(w));
  const isUnder = ["kevesebb", "under", "alatt"].some((w) => outLower.includes(w));

  // Half-time: roughly half the total cards happen in HT (~45%)
  if (isHalftime) {
    const htLine = line * 2.0; // scale to full-match equivalent
    if (htLine in ouProbs) {
      if (isOver) return ouProbs[htLine].over;
      if (isUnder) return ouProbs[htLine].under;
    }
    return null;
  }

  if (line in ouProbs) {
    if (isOver) return ouProbs[line].over;
    if (isUnder) return ouProbs[line].under;
  }

  return null;
}
