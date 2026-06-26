/**
 * Compares model probabilities against bookmaker odds to find value bets.
 * Port of valuebets.py. A value bet exists when model prob > implied prob.
 */
import { MIN_EDGE_PCT } from "@/lib/config";
import { computeMarketProbs, parseExactScoreOutcome } from "@/lib/markets";
import { round } from "@/lib/util";
import type { Probs } from "@/lib/model";

export interface SimpleOdds {
  home_odds?: number | null;
  draw_odds?: number | null;
  away_odds?: number | null;
}

export interface ValueBet {
  market: string;
  market_group?: string;
  outcome?: string;
  model_prob: number;
  implied_prob: number;
  best_odds: number;
  fair_odds: number | null;
  edge_pct: number;
  kelly_pct: number;
  value: boolean;
}

export function findValueBets(
  probs: Probs,
  odds: SimpleOdds,
  _home: string,
  _away: string
): ValueBet[] {
  const candidates: [string, number | null | undefined, number][] = [
    ["Home Win", odds.home_odds, probs.home_win],
    ["Draw", odds.draw_odds, probs.draw],
    ["Away Win", odds.away_odds, probs.away_win],
  ];

  const results: ValueBet[] = [];
  for (const [label, decimalOdds, modelProb] of candidates) {
    if (!decimalOdds || decimalOdds <= 1.0) continue;

    const impliedProb = 1.0 / decimalOdds;
    const edgePct = (modelProb - impliedProb) * 100;
    const kelly = Math.max(
      0.0,
      (modelProb * decimalOdds - 1.0) / (decimalOdds - 1.0)
    );

    results.push({
      market: label,
      model_prob: round(modelProb * 100, 1),
      implied_prob: round(impliedProb * 100, 1),
      best_odds: decimalOdds,
      fair_odds: modelProb > 0 ? round(1.0 / modelProb, 2) : null,
      edge_pct: round(edgePct, 1),
      kelly_pct: round(kelly * 100, 1),
      value: edgePct >= MIN_EDGE_PCT,
    });
  }
  return results;
}

function makeVbet(
  marketName: string,
  outcomeName: string,
  decimalOdds: number,
  modelProb: number,
  groupName = ""
): ValueBet {
  const impliedProb = 1.0 / decimalOdds;
  const edgePct = (modelProb - impliedProb) * 100;
  const kelly = Math.max(
    0.0,
    (modelProb * decimalOdds - 1.0) / (decimalOdds - 1.0)
  );
  return {
    market: marketName,
    market_group: groupName,
    outcome: outcomeName,
    model_prob: round(modelProb * 100, 1),
    implied_prob: round(impliedProb * 100, 1),
    best_odds: decimalOdds,
    fair_odds: modelProb > 0 ? round(1.0 / modelProb, 2) : null,
    edge_pct: round(edgePct, 1),
    kelly_pct: round(kelly * 100, 1),
    value: edgePct >= MIN_EDGE_PCT,
  };
}

/**
 * True if this bet belongs to the corner model — it must be excluded from the
 * goal-model tab now that corners have their own dedicated tab/model.
 */
export function isCornerBet(v: ValueBet): boolean {
  const mg = v.market_group ?? "";
  const mkt = v.market ?? "";
  return (
    mg === "Szögletek" ||
    mkt.toLowerCase().includes("szöglet") ||
    mg.toLowerCase().includes("szöglet")
  );
}

// Groups to skip entirely (player/card markets — not predictable)
const SKIP_GROUPS = new Set(["Játékosok", "Büntetőlapok"]);

// Market name substrings indicating non-predictable player/card/shot markets
const SKIP_MARKET_SUBSTRINGS = [
  "büntetőlap",
  "sárga lap",
  "piros lap",
  "kaput eltaláló",
  "kapura tartó",
  "szabálytalanság",
  "lesz 11-es",
  "lesz kiállítás",
  "lesz öngól",
  "lesz mesterhármas",
  "kezdőként",
];

export interface MarketOutcome {
  name?: string;
  no?: number;
  fixedOdds?: number | null;
  odds?: number | null;
}
export interface Market {
  name?: string;
  outcomes?: MarketOutcome[];
}
export interface MarketGroup {
  name?: string;
  markets?: Market[];
}

const EXACT_SCORE_MARKETS = new Set([
  "Pontos végeredmény",
  "1. félidő - Pontos eredmény",
  "2. félidő - Pontos eredmény",
]);

export function findAllValueBets(
  marketGroups: MarketGroup[],
  probs: Probs,
  homeHu: string,
  awayHu: string
): ValueBet[] {
  const scoreMatrix = probs.score_matrix ?? [];
  const expH = probs.exp_home_goals;
  const expA = probs.exp_away_goals;

  const results: ValueBet[] = [];
  const seenMarkets = new Set<string>();

  for (const group of marketGroups) {
    const groupName = group.name ?? "";
    if (SKIP_GROUPS.has(groupName)) continue;

    for (const market of group.markets ?? []) {
      const marketName = market.name ?? "";
      if (!marketName) continue;

      const ml = marketName.toLowerCase();
      if (SKIP_MARKET_SUBSTRINGS.some((s) => ml.includes(s))) continue;

      if (seenMarkets.has(marketName)) continue;
      seenMarkets.add(marketName);

      const outcomes = market.outcomes ?? [];

      // Special handling: exact score markets
      if (EXACT_SCORE_MARKETS.has(marketName)) {
        for (const outcome of outcomes) {
          const oddsVal = outcome.fixedOdds || outcome.odds;
          if (!oddsVal || oddsVal <= 1.0) continue;
          const score = parseExactScoreOutcome(
            outcome.name ?? "",
            homeHu,
            awayHu
          );
          if (score === null) continue;
          const [hG, aG] = score;
          if (hG < scoreMatrix.length && aG < (scoreMatrix[0]?.length ?? 0)) {
            const modelProb = scoreMatrix[hG][aG];
            if (modelProb > 0)
              results.push(
                makeVbet(
                  marketName,
                  outcome.name ?? "",
                  oddsVal,
                  modelProb,
                  groupName
                )
              );
          }
        }
        continue;
      }

      // All other markets: use computeMarketProbs
      const outcomeProbs = computeMarketProbs(
        marketName,
        scoreMatrix,
        expH,
        expA,
        homeHu,
        awayHu
      );
      if (!outcomeProbs) continue;

      outcomes.forEach((outcome, idx) => {
        if (!(idx in outcomeProbs)) return;
        const oddsVal = outcome.fixedOdds || outcome.odds;
        if (!oddsVal || oddsVal <= 1.0) return;
        const modelProb = outcomeProbs[idx];
        if (modelProb <= 0) return;
        results.push(
          makeVbet(
            marketName,
            outcome.name ?? "",
            oddsVal,
            modelProb,
            groupName
          )
        );
      });
    }
  }

  // Sort: value bets first, then by edge descending
  results.sort(
    (a, b) =>
      Number(b.value) - Number(a.value) || b.edge_pct - a.edge_pct
  );
  return results;
}
