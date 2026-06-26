/**
 * Live in-play probability model for WC 2026 — port of live_model.py.
 * Adjusts pre-match Poisson predictions using current score, time elapsed,
 * live xG, red cards, and possession.
 */
import { poissonPmf, arange } from "@/lib/stats";
import { outer } from "@/lib/matrix";
import { round } from "@/lib/util";
import type { MarketGroup } from "@/lib/valuebets";

const MAX_GOALS = 8; // max additional goals to consider per team

export interface LiveProbs {
  home_win: number;
  draw: number;
  away_win: number;
  dnb_home: number;
  dnb_away: number;
  btts: number;
  over_0_5: number;
  over_1_5: number;
  over_2_5: number;
  over_3_5: number;
  over_4_5: number;
  exp_remaining_home: number;
  exp_remaining_away: number;
  adj_rate_home: number;
  adj_rate_away: number;
  live_weight: number;
  [key: string]: number;
}

function pmf(lam: number): number[] {
  return poissonPmf(arange(MAX_GOALS), Math.max(lam, 1e-6));
}

export function liveProbs(args: {
  preXgHome: number;
  preXgAway: number;
  minute: number;
  homeScore: number;
  awayScore: number;
  liveXgHome: number;
  liveXgAway: number;
  redCardsHome?: number;
  redCardsAway?: number;
  possessionHome?: number;
}): LiveProbs {
  const {
    preXgHome,
    preXgAway,
    minute,
    homeScore,
    awayScore,
    liveXgHome,
    liveXgAway,
    redCardsHome = 0,
    redCardsAway = 0,
    possessionHome = 50.0,
  } = args;

  // 1. Estimate total match minutes (add stoppage)
  const stoppage = minute < 45 ? 5 : 7;
  const totalMin = 90 + stoppage;
  const elapsedFrac = Math.min(minute / 90.0, 1.0);
  const remainingFrac = Math.max(0.0, (totalMin - minute) / 90.0);

  // 2. Blend pre-match rate with live xG rate
  let adjH: number;
  let adjA: number;
  if (minute >= 10 && liveXgHome + liveXgAway > 0.05) {
    const liveRateH = liveXgHome / elapsedFrac;
    const liveRateA = liveXgAway / elapsedFrac;
    const liveW = Math.min(0.7, elapsedFrac * 0.85);
    adjH = (1 - liveW) * preXgHome + liveW * liveRateH;
    adjA = (1 - liveW) * preXgAway + liveW * liveRateA;
  } else {
    adjH = preXgHome;
    adjA = preXgAway;
  }

  // 3. Possession nudge (secondary, small effect)
  const posFactorH = 0.9 + 0.2 * (possessionHome / 100.0);
  const posFactorA = 0.9 + 0.2 * ((100 - possessionHome) / 100.0);
  adjH = adjH * 0.95 + adjH * posFactorH * 0.05;
  adjA = adjA * 0.95 + adjA * posFactorA * 0.05;

  // 4. Red card penalty: 25% fewer goals per red
  adjH *= Math.pow(0.75, redCardsHome);
  adjA *= Math.pow(0.75, redCardsAway);

  // 5. Expected remaining goals
  const remH = Math.max(0.0, adjH * remainingFrac);
  const remA = Math.max(0.0, adjA * remainingFrac);

  // 6. Poisson joint distribution for remaining goals
  const pmfH = pmf(remH);
  const pmfA = pmf(remA);
  const joint = outer(pmfH, pmfA);

  let homeWin = 0.0;
  let draw = 0.0;
  let awayWin = 0.0;
  let btts = 0.0;
  const over: Record<string, number> = {
    "0.5": 0,
    "1.5": 0,
    "2.5": 0,
    "3.5": 0,
    "4.5": 0,
  };
  const thresholds = [0.5, 1.5, 2.5, 3.5, 4.5];

  for (let i = 0; i <= MAX_GOALS; i++) {
    for (let j = 0; j <= MAX_GOALS; j++) {
      const p = joint[i][j];
      const finalH = homeScore + i;
      const finalA = awayScore + j;
      const total = finalH + finalA;

      if (finalH > finalA) homeWin += p;
      else if (finalH < finalA) awayWin += p;
      else draw += p;

      if (finalH > 0 && finalA > 0) btts += p;

      for (const thr of thresholds) if (total > thr) over[String(thr)] += p;
    }
  }

  const hwAw = homeWin + awayWin;
  const dnbHome = hwAw > 0 ? homeWin / hwAw : 0.5;
  const dnbAway = hwAw > 0 ? awayWin / hwAw : 0.5;

  return {
    home_win: round(homeWin, 4),
    draw: round(draw, 4),
    away_win: round(awayWin, 4),
    dnb_home: round(dnbHome, 4),
    dnb_away: round(dnbAway, 4),
    btts: round(btts, 4),
    over_0_5: round(over["0.5"], 4),
    over_1_5: round(over["1.5"], 4),
    over_2_5: round(over["2.5"], 4),
    over_3_5: round(over["3.5"], 4),
    over_4_5: round(over["4.5"], 4),
    exp_remaining_home: round(remH, 2),
    exp_remaining_away: round(remA, 2),
    adj_rate_home: round(adjH, 2),
    adj_rate_away: round(adjA, 2),
    live_weight: round(Math.min(0.7, elapsedFrac * 0.85), 2),
  };
}

export interface LiveMinOddsBet {
  market: string;
  group: string;
  prob: number;
  fair_odds: number;
  min_odds: number;
  kelly_frac: number;
}

export function liveValueBets(
  probs: LiveProbs,
  minEdge = 5.0
): LiveMinOddsBet[] {
  const markets: [string, number, string, number][] = [
    ["Hazai győzelem (1)", probs.home_win, "1X2", 0.125],
    ["Döntetlen (X)", probs.draw, "1X2", 0.125],
    ["Vendég győzelem (2)", probs.away_win, "1X2", 0.125],
    ["DNB — Hazai", probs.dnb_home, "DNB", 0.25],
    ["DNB — Vendég", probs.dnb_away, "DNB", 0.25],
    ["Mindkét csapat szerez", probs.btts, "Gólok", 0.25],
    ["Gól O 0.5", probs.over_0_5, "Gólok", 0.25],
    ["Gól O 1.5", probs.over_1_5, "Gólok", 0.25],
    ["Gól O 2.5", probs.over_2_5, "Gólok", 0.25],
    ["Gól O 3.5", probs.over_3_5, "Gólok", 0.25],
    ["Gól O 4.5", probs.over_4_5, "Gólok", 0.25],
    ["Gól U 0.5", 1 - probs.over_0_5, "Gólok", 0.25],
    ["Gól U 1.5", 1 - probs.over_1_5, "Gólok", 0.25],
    ["Gól U 2.5", 1 - probs.over_2_5, "Gólok", 0.25],
  ];

  const results: LiveMinOddsBet[] = [];
  for (const [name, prob, group, kellyFrac] of markets) {
    if (prob <= 0) continue;
    const fairOdds = round(1.0 / prob, 2);
    const minOdds = round(fairOdds * (1 + minEdge / 100), 2);
    results.push({
      market: name,
      group,
      prob: round(prob * 100, 1),
      fair_odds: fairOdds,
      min_odds: minOdds,
      kelly_frac: kellyFrac,
    });
  }

  results.sort((a, b) => b.prob - a.prob);
  return results;
}

// ---------------------------------------------------------------------------
// Live value bets using actual Tippmix market odds
// ---------------------------------------------------------------------------

const GOLSZAM_RE = /(\d+)[,.](\d+)/;

function outcomeLiveProb(
  marketName: string,
  outcomeNo: number | undefined,
  probs: LiveProbs
): number | null {
  const n = marketName.trim();
  const nl = n.toLowerCase();

  if (n === "1X2") {
    const map: Record<number, number> = {
      1: probs.home_win,
      2: probs.draw,
      3: probs.away_win,
    };
    return outcomeNo !== undefined && outcomeNo in map ? map[outcomeNo] : null;
  }

  if (nl.includes("döntetlennél") && nl.includes("visszajár")) {
    const map: Record<number, number> = {
      1: probs.dnb_home,
      2: probs.dnb_away,
    };
    return outcomeNo !== undefined && outcomeNo in map ? map[outcomeNo] : null;
  }

  if (n.startsWith("Gólszám")) {
    const mm = n.match(GOLSZAM_RE);
    if (mm) {
      const key = `over_${mm[1]}_${mm[2]}`;
      const overProb = (probs as Record<string, number>)[key] ?? 0.0;
      if (outcomeNo === 1) return 1.0 - overProb; // under
      if (outcomeNo === 2) return overProb; // over
    }
  }

  if (nl.includes("mindkét csapat")) {
    const btts = probs.btts ?? 0.0;
    if (outcomeNo === 1) return btts;
    if (outcomeNo === 2) return 1.0 - btts;
  }

  return null;
}

export interface LiveMarketBet {
  market: string;
  outcome: string;
  model_prob: number;
  tippmix_odds: number;
  implied_prob: number;
  fair_odds: number;
  edge_pct: number;
  kelly_pct: number;
  kelly_frac: number;
  stake_ft: number;
  value: boolean;
}

export function findLiveValueBetsFromMarkets(
  marketGroups: MarketGroup[],
  liveProbsDict: LiveProbs,
  bankroll = 10000.0,
  minEdge = 5.0
): LiveMarketBet[] {
  const results: LiveMarketBet[] = [];
  const seenMarkets = new Set<string>();

  for (const group of marketGroups) {
    for (const market of group.markets ?? []) {
      const marketName = market.name ?? "";
      if (!marketName || seenMarkets.has(marketName)) continue;

      const ml = marketName.toLowerCase();
      const isSupported =
        marketName === "1X2" ||
        marketName.startsWith("Gólszám") ||
        (ml.includes("döntetlennél") && ml.includes("visszajár")) ||
        ml.includes("mindkét csapat");
      if (!isSupported) continue;

      seenMarkets.add(marketName);

      let kellyFrac: number;
      if (marketName.startsWith("Gólszám") || ml.includes("mindkét csapat"))
        kellyFrac = 0.25;
      else if (ml.includes("döntetlennél")) kellyFrac = 0.25;
      else kellyFrac = 0.125;

      for (const outcome of market.outcomes ?? []) {
        const outcomeNo = outcome.no;
        const outcomeName = outcome.name ?? "";
        const oddsVal = Number(outcome.fixedOdds || outcome.odds || 0);
        if (oddsVal <= 1.0) continue;

        const prob = outcomeLiveProb(marketName, outcomeNo, liveProbsDict);
        if (prob === null || prob <= 0) continue;

        const implied = 1.0 / oddsVal;
        const edgePct = (prob - implied) * 100;
        const kelly = Math.max(
          0.0,
          (prob * oddsVal - 1.0) / (oddsVal - 1.0)
        );
        const stake = Math.round(kelly * kellyFrac * bankroll);

        results.push({
          market: marketName,
          outcome: outcomeName,
          model_prob: round(prob * 100, 1),
          tippmix_odds: oddsVal,
          implied_prob: round(implied * 100, 1),
          fair_odds: round(1.0 / prob, 2),
          edge_pct: round(edgePct, 1),
          kelly_pct: round(kelly * 100, 2),
          kelly_frac: kellyFrac,
          stake_ft: stake,
          value: edgePct >= minEdge,
        });
      }
    }
  }

  results.sort(
    (a, b) => Number(b.value) - Number(a.value) || b.edge_pct - a.edge_pct
  );
  return results;
}
