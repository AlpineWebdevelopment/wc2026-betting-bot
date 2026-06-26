/**
 * Probability calculations for all predictable Tippmix markets.
 * Direct TypeScript port of markets.py — derived from the Poisson score matrix
 * (home goals x away goals joint PMF).
 */
import { poissonPmf, arange } from "@/lib/stats";
import {
  outer,
  sumStrictLower,
  sumDiag,
  sumStrictUpper,
  rowSums,
  colSums,
} from "@/lib/matrix";

const HT_FRAC = 0.42; // fraction of total xG that occurs in the 1st half
const MAX_G = 10; // goals cap (matches config.MAX_GOALS)

/** Outcome index → probability. null means "not predictable". */
export type OutcomeProbs = Record<number, number> | null;

// ---------------------------------------------------------------------------
// Helper functions
// ---------------------------------------------------------------------------

function halfMatrix(expH: number, expA: number, frac: number): number[][] {
  const g = arange(MAX_G);
  return outer(poissonPmf(g, frac * expH), poissonPmf(g, frac * expA));
}

/** Sum of m[i][j] over all (i, j) satisfying pred. */
function sumWhere(
  m: number[][],
  pred: (i: number, j: number) => boolean
): number {
  let s = 0;
  const n = m.length;
  for (let i = 0; i < n; i++)
    for (let j = 0; j < n; j++) if (pred(i, j)) s += m[i][j];
  return s;
}

/** (under, over) for total goals O/U `line`. */
function ou(m: number[][], line: number): [number, number] {
  const over = sumWhere(m, (i, j) => i + j > line);
  return [1.0 - over, over];
}

function teamOu(marginal: number[], line: number): [number, number] {
  let over = 0;
  for (let k = 0; k < marginal.length; k++) if (k > line) over += marginal[k];
  return [1.0 - over, over];
}

/** Effective (under, over) for Asian total lines (handles quarter-ball). */
function asianTotal(m: number[][], line: number): [number, number] {
  const frac = round2(((line % 1.0) + 1.0) % 1.0);

  const exactTotal = (t: number): number =>
    sumWhere(m, (i, j) => i + j === Math.trunc(t));

  if (frac === 0.5) return ou(m, line);
  if (frac === 0.0) {
    const exact = exactTotal(line);
    const [, overFull] = ou(m, line);
    const effOver = overFull + 0.5 * exact;
    return [1.0 - effOver, effOver];
  }
  if (Math.abs(frac - 0.25) < 0.01) {
    const base = Math.trunc(line);
    const exact = exactTotal(base);
    const [, overXp5] = ou(m, base + 0.5);
    const effOver = overXp5 + 0.5 * exact;
    return [1.0 - effOver, effOver];
  }
  if (Math.abs(frac - 0.75) < 0.01) {
    const base = Math.trunc(line);
    const [, overX5] = ou(m, base + 0.5);
    const exactXp1 = exactTotal(base + 1);
    const [, overXp1] = ou(m, base + 1.0);
    const effOverXp1 = overXp1 + 0.5 * exactXp1;
    const effOver = 0.5 * overX5 + 0.5 * effOverXp1;
    return [1.0 - effOver, effOver];
  }
  return ou(m, line);
}

/**
 * Effective (home, away) probs for Asian handicap.
 * line is from HOME perspective (e.g. -1.75 = home gives 1.75 goals to away).
 */
function asianHandicap(m: number[][], line: number): [number, number] {
  const n = m.length;
  const frac = round2((Math.abs(line) % 1.0));

  let homeP = 0.0;
  let awayP = 0.0;
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const p = m[i][j];
      const net = i - j + line; // > 0 means home wins AH

      if (Math.abs(frac) < 0.01) {
        // Whole-number line: push at net=0
        if (Math.abs(net) < 0.01) {
          homeP += 0.5 * p;
          awayP += 0.5 * p;
        } else if (net > 0) {
          homeP += p;
        } else {
          awayP += p;
        }
      } else if (Math.abs(frac - 0.5) < 0.01) {
        // Half-line: no push
        if (net > 0) homeP += p;
        else awayP += p;
      } else {
        // Quarter ball: split between two adjacent lines
        const sign = line < 0 ? -1.0 : 1.0;
        const l1 = line - 0.25 * sign;
        const l2 = line + 0.25 * sign;
        for (const lx of [l1, l2]) {
          const net2 = i - j + lx;
          const lxFrac = round2((Math.abs(lx) % 1.0));
          if (Math.abs(lxFrac) < 0.01 && Math.abs(net2) < 0.01) {
            homeP += 0.25 * p;
            awayP += 0.25 * p;
          } else if (net2 > 0) {
            homeP += 0.5 * p;
          } else if (net2 < 0) {
            awayP += 0.5 * p;
          }
        }
      }
    }
  }
  return [homeP, awayP];
}

function round2(x: number): number {
  return Math.round(x * 100) / 100;
}

// ---------------------------------------------------------------------------
// Main dispatcher
// ---------------------------------------------------------------------------

export function computeMarketProbs(
  marketName: string,
  scoreMatrix: number[][],
  expH: number,
  expA: number,
  homeHu = "",
  awayHu = ""
): OutcomeProbs {
  const m = scoreMatrix;
  const n = m.length;

  const homeG = rowSums(m); // P(home scores k)
  const awayG = colSums(m); // P(away scores k)

  const hw = sumStrictLower(m);
  const dr = sumDiag(m);
  const aw = sumStrictUpper(m);

  const ht = halfMatrix(expH, expA, HT_FRAC);
  const sh = halfMatrix(expH, expA, 1.0 - HT_FRAC);

  const htHw = sumStrictLower(ht);
  const htDr = sumDiag(ht);
  const htAw = sumStrictUpper(ht);
  const shHw = sumStrictLower(sh);
  const shDr = sumDiag(sh);
  const shAw = sumStrictUpper(sh);

  const htHg = rowSums(ht);
  const htAg = colSums(ht);
  const shHg = rowSums(sh);
  const shAg = colSums(sh);

  const name = marketName;

  // ── 1X2 ──────────────────────────────────────────────────────────────────
  if (name === "1X2") return { 0: hw, 1: dr, 2: aw };

  // ── Double Chance ─────────────────────────────────────────────────────────
  if (name === "Kétesély") return { 0: hw + dr, 1: hw + aw, 2: dr + aw };

  // ── Draw No Bet ───────────────────────────────────────────────────────────
  if (name === "Döntetlennél a tét visszajár") {
    const d = hw + aw;
    return { 0: d > 0 ? hw / d : 0.5, 1: d > 0 ? aw / d : 0.5 };
  }

  // ── BTTS ──────────────────────────────────────────────────────────────────
  if (
    name === "Mindkét csapat szerez gólt" ||
    name === "1. félidő - Mindkét csapat szerez gólt?" ||
    name === "2. félidő - Mindkét csapat szerez gólt?"
  ) {
    let btts: number;
    if (name.includes("1. félid"))
      btts = sumWhere(ht, (i, j) => i >= 1 && j >= 1);
    else if (name.includes("2. félid"))
      btts = sumWhere(sh, (i, j) => i >= 1 && j >= 1);
    else btts = sumWhere(m, (i, j) => i >= 1 && j >= 1);
    return { 0: btts, 1: 1.0 - btts };
  }

  // ── Over/Under total goals ────────────────────────────────────────────────
  for (const line of [0.5, 1.5, 2.5, 3.5, 4.5]) {
    const huLine = line.toFixed(1).replace(".", ",");
    if (name === `Gólszám ${huLine}`) {
      const [u, o] = ou(m, line);
      return { 0: u, 1: o };
    }
    if (name === `1. félidő - Gólszám ${huLine}`) {
      const [u, o] = ou(ht, line);
      return { 0: u, 1: o };
    }
    if (name === `2. félidő - Gólszám ${huLine}`) {
      const [u, o] = ou(sh, line);
      return { 0: u, 1: o };
    }
  }

  // ── Goal ranges (0-1, 2-3, 4-5, 6+) ──────────────────────────────────────
  if (name === "Gólszám") {
    const r01 = sumWhere(m, (i, j) => i + j <= 1);
    const r23 = sumWhere(m, (i, j) => i + j >= 2 && i + j <= 3);
    const r45 = sumWhere(m, (i, j) => i + j >= 4 && i + j <= 5);
    const r6p = sumWhere(m, (i, j) => i + j >= 6);
    return { 0: r01, 1: r23, 2: r45, 3: r6p };
  }

  if (name === "1. félidő - Gólszám") {
    const g0 = sumWhere(ht, (i, j) => i + j === 0);
    const g1 = sumWhere(ht, (i, j) => i + j === 1);
    const g2p = 1.0 - g0 - g1;
    return { 0: g0, 1: g1, 2: Math.max(0.0, g2p) };
  }

  if (name === "2. félidő - Gólszám") {
    const g0 = sumWhere(sh, (i, j) => i + j === 0);
    const g1 = sumWhere(sh, (i, j) => i + j === 1);
    const g2p = 1.0 - g0 - g1;
    return { 0: g0, 1: g1, 2: Math.max(0.0, g2p) };
  }

  // ── Exact goal count ──────────────────────────────────────────────────────
  if (name === "Gólszám (pontosan)") {
    const probs: Record<number, number> = {};
    for (let k = 0; k < 5; k++) probs[k] = sumWhere(m, (i, j) => i + j === k);
    return probs;
  }

  // ── 1X2 + BTTS combo ──────────────────────────────────────────────────────
  if (name === "1X2 + Mindkét csapat szerez gólt") {
    const hY = sumWhere(m, (i, j) => i >= 1 && j >= 1 && i > j);
    const hN = sumWhere(m, (i, j) => i > j && (i === 0 || j === 0));
    const dY = sumWhere(m, (i, j) => i >= 1 && j >= 1 && i === j);
    const dN = m[0][0];
    const aY = sumWhere(m, (i, j) => i >= 1 && j >= 1 && j > i);
    const aN = sumWhere(m, (i, j) => j > i && (i === 0 || j === 0));
    return { 0: hY, 1: hN, 2: dY, 3: dN, 4: aY, 5: aN };
  }

  // ── 1X2 + Over/Under combo ────────────────────────────────────────────────
  for (const line of [1.5, 2.5, 3.5, 4.5]) {
    const huLine = line.toFixed(1).replace(".", ",");
    if (name === `1X2 + Gólszám ${huLine}`) {
      const hU = sumWhere(m, (i, j) => i > j && i + j <= line);
      const dU = sumWhere(m, (i, j) => i === j && i + j <= line);
      const aU = sumWhere(m, (i, j) => j > i && i + j <= line);
      const hO = sumWhere(m, (i, j) => i > j && i + j > line);
      const dO = sumWhere(m, (i, j) => i === j && i + j > line);
      const aO = sumWhere(m, (i, j) => j > i && i + j > line);
      return { 0: hU, 1: dU, 2: aU, 3: hO, 4: dO, 5: aO };
    }
    if (name === `1. félidő - 1X2 + Gólszám ${huLine}`) {
      const hU = sumWhere(ht, (i, j) => i > j && i + j <= line);
      const dU = sumWhere(ht, (i, j) => i === j && i + j <= line);
      const aU = sumWhere(ht, (i, j) => j > i && i + j <= line);
      const hO = sumWhere(ht, (i, j) => i > j && i + j > line);
      const dO = sumWhere(ht, (i, j) => i === j && i + j > line);
      const aO = sumWhere(ht, (i, j) => j > i && i + j > line);
      return { 0: hU, 1: dU, 2: aU, 3: hO, 4: dO, 5: aO };
    }
  }

  // ── Home team goals O/U ───────────────────────────────────────────────────
  for (const line of [0.5, 1.5, 2.5]) {
    const huLine = line.toFixed(1).replace(".", ",");
    if (name === `Hazai csapat - Gólszám ${huLine}`) {
      const [u, o] = teamOu(homeG, line);
      return { 0: u, 1: o };
    }
    if (name === `1. félidő - Hazai csapat - Gólszám ${huLine}`) {
      const [u, o] = teamOu(htHg, line);
      return { 0: u, 1: o };
    }
    if (name === `2. félidő - Hazai csapat - Gólszám ${huLine}`) {
      const [u, o] = teamOu(shHg, line);
      return { 0: u, 1: o };
    }
  }

  // ── Away team goals O/U ───────────────────────────────────────────────────
  for (const line of [0.5, 1.5]) {
    const huLine = line.toFixed(1).replace(".", ",");
    if (name === `Vendégcsapat - Gólszám ${huLine}`) {
      const [u, o] = teamOu(awayG, line);
      return { 0: u, 1: o };
    }
    if (name === `1. félidő - Vendégcsapat - Gólszám ${huLine}`) {
      const [u, o] = teamOu(htAg, line);
      return { 0: u, 1: o };
    }
    if (name === `2. félidő - Vendégcsapat - Gólszám ${huLine}`) {
      const [u, o] = teamOu(shAg, line);
      return { 0: u, 1: o };
    }
  }

  // ── BTTS + Over 2.5 ───────────────────────────────────────────────────────
  if (name === "Mindkét csapat szerez gólt + Gólszám 2,5") {
    const yO = sumWhere(m, (i, j) => i >= 1 && j >= 1 && i + j > 2.5);
    const yU = sumWhere(m, (i, j) => i >= 1 && j >= 1 && i + j <= 2.5);
    const nO = sumWhere(m, (i, j) => (i === 0 || j === 0) && i + j > 2.5);
    const nU = sumWhere(m, (i, j) => (i === 0 || j === 0) && i + j <= 2.5);
    return { 0: yO, 1: yU, 2: nO, 3: nU };
  }

  // ── European Handicap ─────────────────────────────────────────────────────
  for (const [hStart, aStart] of [
    [0, 2],
    [0, 1],
    [1, 0],
  ]) {
    if (name === `Hendikep ${hStart}:${aStart}`) {
      const hWin = sumWhere(m, (i, j) => i + hStart > j + aStart);
      const hDraw = sumWhere(m, (i, j) => i + hStart === j + aStart);
      const hAway = sumWhere(m, (i, j) => i + hStart < j + aStart);
      return { 0: hWin, 1: hDraw, 2: hAway };
    }
    if (name === `1. félidő - Hendikep ${hStart}:${aStart}`) {
      const hWin = sumWhere(ht, (i, j) => i + hStart > j + aStart);
      const hDraw = sumWhere(ht, (i, j) => i + hStart === j + aStart);
      const hAway = sumWhere(ht, (i, j) => i + hStart < j + aStart);
      return { 0: hWin, 1: hDraw, 2: hAway };
    }
    if (name === `2. félidő - Hendikep ${hStart}:${aStart}`) {
      const hWin = sumWhere(sh, (i, j) => i + hStart > j + aStart);
      const hDraw = sumWhere(sh, (i, j) => i + hStart === j + aStart);
      const hAway = sumWhere(sh, (i, j) => i + hStart < j + aStart);
      return { 0: hWin, 1: hDraw, 2: hAway };
    }
  }

  // ── Win margin ────────────────────────────────────────────────────────────
  if (name === "Nyertes különbség") {
    const h3p = sumWhere(m, (i, j) => i - j >= 3);
    const h2 = sumWhere(m, (i, j) => i - j === 2);
    const h1 = sumWhere(m, (i, j) => i - j === 1);
    const a1 = sumWhere(m, (i, j) => j - i === 1);
    const a2 = sumWhere(m, (i, j) => j - i === 2);
    const a3p = sumWhere(m, (i, j) => j - i >= 3);
    return { 0: h3p, 1: h2, 2: h1, 3: a1, 4: a2, 5: a3p };
  }

  // ── Clean sheet / wins to nil ─────────────────────────────────────────────
  if (name === "Hazai csapat kapott gól nélkül játssza le a mérkőzést") {
    const p = awayG[0];
    return { 0: p, 1: 1.0 - p };
  }
  if (name === "Vendégcsapat kapott gól nélkül játssza le a mérkőzést") {
    const p = homeG[0];
    return { 0: p, 1: 1.0 - p };
  }
  if (name === "Hazai csapat kapott gól nélkül játssza le az 1. félidőt") {
    const p = htAg[0];
    return { 0: p, 1: 1.0 - p };
  }
  if (name === "Vendégcsapat kapott gól nélkül játssza le az 1. félidőt") {
    const p = htHg[0];
    return { 0: p, 1: 1.0 - p };
  }
  if (name === "Hazai csapat kapott gól nélkül játssza le a 2. félidőt") {
    const p = shAg[0];
    return { 0: p, 1: 1.0 - p };
  }
  if (name === "Vendégcsapat kapott gól nélkül játssza le a 2. félidőt") {
    const p = shHg[0];
    return { 0: p, 1: 1.0 - p };
  }
  if (name === "Hazai csapat 0-ra nyeri a mérkőzést") {
    let p = 0;
    for (let i = 1; i < n; i++) p += m[i][0];
    return { 0: p, 1: 1.0 - p };
  }
  if (name === "Vendégcsapat 0-ra nyeri a mérkőzést") {
    let p = 0;
    for (let j = 1; j < n; j++) p += m[0][j];
    return { 0: p, 1: 1.0 - p };
  }

  // ── Exact goals per team (0, 1, 2, 3+) ───────────────────────────────────
  if (name === "Hazai csapat góljainak a száma") {
    const p0 = homeG[0];
    const p1 = n > 1 ? homeG[1] : 0.0;
    const p2 = n > 2 ? homeG[2] : 0.0;
    const p3p = Math.max(0.0, 1.0 - p0 - p1 - p2);
    return { 0: p0, 1: p1, 2: p2, 3: p3p };
  }
  if (name === "Vendégcsapat góljainak a száma") {
    const p0 = awayG[0];
    const p1 = n > 1 ? awayG[1] : 0.0;
    const p2 = n > 2 ? awayG[2] : 0.0;
    const p3p = Math.max(0.0, 1.0 - p0 - p1 - p2);
    return { 0: p0, 1: p1, 2: p2, 3: p3p };
  }

  // ── Goal odd/even ─────────────────────────────────────────────────────────
  if (name === "Gólszám: páros vagy páratlan") {
    const odd = sumWhere(m, (i, j) => (i + j) % 2 === 1);
    return { 0: odd, 1: 1.0 - odd };
  }

  // ── Which team scores (only home, only away, both, neither) ───────────────
  if (name === "Melyik csapat szerez gólt?") {
    let onlyH = 0;
    for (let i = 1; i < n; i++) onlyH += m[i][0];
    let onlyA = 0;
    for (let j = 1; j < n; j++) onlyA += m[0][j];
    const both = sumWhere(m, (i, j) => i >= 1 && j >= 1);
    const none = m[0][0];
    return { 0: onlyH, 1: onlyA, 2: both, 3: none };
  }

  // ── First goal scorer (team): [home, no goal, away] ──────────────────────
  if (name === "Melyik csapat szerzi a(z) 1. gólt?") {
    const noGoal = m[0][0];
    const totalG = expH + expA;
    let pHome = 0.0;
    let pAway = 0.0;
    if (totalG > 0) {
      pHome = ((1.0 - noGoal) * expH) / totalG;
      pAway = ((1.0 - noGoal) * expA) / totalG;
    }
    return { 0: pHome, 1: noGoal, 2: pAway };
  }

  // ── Which half more goals: [more 1H, equal, more 2H] ─────────────────────
  if (name === "Melyik félidőben lesz több gól?") {
    let more1h = 0.0;
    let equal = 0.0;
    let more2h = 0.0;
    for (let g1 = 0; g1 < n; g1++) {
      const ph1 = sumWhere(ht, (i, j) => i + j === g1);
      for (let g2 = 0; g2 < n; g2++) {
        const ph2 = sumWhere(sh, (i, j) => i + j === g2);
        const p = ph1 * ph2;
        if (g1 > g2) more1h += p;
        else if (g1 === g2) equal += p;
        else more2h += p;
      }
    }
    return { 0: more1h, 1: equal, 2: more2h };
  }

  // ── Home/away scores in both halves ──────────────────────────────────────
  if (name === "Hazai csapat szerez gólt mindkét félidőben?") {
    const pHt = 1.0 - htHg[0];
    const pSh = 1.0 - shHg[0];
    const p = pHt * pSh;
    return { 0: p, 1: 1.0 - p };
  }
  if (name === "Vendégcsapat szerez gólt mindkét félidőben?") {
    const pHt = 1.0 - htAg[0];
    const pSh = 1.0 - shAg[0];
    const p = pHt * pSh;
    return { 0: p, 1: 1.0 - p };
  }

  // ── Both halves with/without goals ───────────────────────────────────────
  if (name === "Mindkét félidőben kevesebb, mint 1,5 gól lesz?") {
    const [htU15] = ou(ht, 1.5); // P(HT total <= 1)
    const [shU15] = ou(sh, 1.5); // P(SH total <= 1)
    const p = htU15 * shU15;
    return { 0: p, 1: 1.0 - p };
  }
  if (name === "Mindkét félidőben több, mint 1,5 gól lesz?") {
    const [, htO15] = ou(ht, 1.5);
    const [, shO15] = ou(sh, 1.5);
    const p = htO15 * shO15;
    return { 0: p, 1: 1.0 - p };
  }

  // ── Both halves with at least 1 goal ─────────────────────────────────────
  if (name === "Mindkét félidőben lesz gól?") {
    const pHt = 1.0 - sumWhere(ht, (i, j) => i + j === 0);
    const pSh = 1.0 - sumWhere(sh, (i, j) => i + j === 0);
    const p = pHt * pSh;
    return { 0: p, 1: 1.0 - p };
  }

  // ── HT/FT result combo (9 outcomes) ──────────────────────────────────────
  if (name === "Félidő/végeredmény") {
    const results: Record<number, number> = {};
    let idx = 0;
    const resultOf = (h: number, a: number): string =>
      h > a ? "home" : h === a ? "draw" : "away";
    for (const htR of ["home", "draw", "away"]) {
      for (const ftR of ["home", "draw", "away"]) {
        let p = 0.0;
        for (let htH = 0; htH < n; htH++) {
          for (let htA = 0; htA < n; htA++) {
            const htProb = ht[htH][htA];
            if (htProb < 1e-9) continue;
            if (resultOf(htH, htA) !== htR) continue;
            for (let shH = 0; shH < n; shH++) {
              for (let shA = 0; shA < n; shA++) {
                const shProb = sh[shH][shA];
                if (shProb < 1e-9) continue;
                if (resultOf(htH + shH, htA + shA) === ftR)
                  p += htProb * shProb;
              }
            }
          }
        }
        results[idx] = p;
        idx += 1;
      }
    }
    return results;
  }

  // ── 1st half 1X2 variants ────────────────────────────────────────────────
  if (name === "1. félidő - 1X2") return { 0: htHw, 1: htDr, 2: htAw };
  if (name === "1. félidő - Kétesély")
    return { 0: htHw + htDr, 1: htHw + htAw, 2: htDr + htAw };
  if (name === "1. félidő - Döntetlennél a tét visszajár") {
    const d = htHw + htAw;
    return { 0: d > 0 ? htHw / d : 0.5, 1: d > 0 ? htAw / d : 0.5 };
  }

  // ── 2nd half 1X2 variants ────────────────────────────────────────────────
  if (name === "2. félidő - 1X2") return { 0: shHw, 1: shDr, 2: shAw };
  if (name === "2. félidő - Kétesély")
    return { 0: shHw + shDr, 1: shHw + shAw, 2: shDr + shAw };
  if (name === "2. félidő - Döntetlennél tét visszajár") {
    const d = shHw + shAw;
    return { 0: d > 0 ? shHw / d : 0.5, 1: d > 0 ? shAw / d : 0.5 };
  }

  // ── Asian Total (Ázsiai Gólszám) ─────────────────────────────────────────
  let mt = name.match(/^Ázsiai Gólszám (\d+)(?:,(\d+))?$/);
  if (mt) {
    const whole = parseInt(mt[1], 10);
    const fracStr = mt[2] || "0";
    let fracVal: number;
    if (fracStr.length === 1) fracVal = parseInt(fracStr, 10) / 10.0;
    else if (fracStr.length === 2) fracVal = parseInt(fracStr, 10) / 100.0;
    else fracVal = 0.0;
    const lineVal = whole + fracVal;
    const [u, o] = asianTotal(m, lineVal);
    return { 0: u, 1: o };
  }

  // ── Asian Handicap (Ázsiai Hendikep) ─────────────────────────────────────
  mt = name.match(/^Ázsiai Hendikep ([+-]?\d+)(?:,(\d+))?$/);
  if (mt) {
    const whole = parseInt(mt[1], 10);
    const fracStr = mt[2] || "0";
    let fracVal: number;
    if (fracStr.length === 1) fracVal = parseInt(fracStr, 10) / 10.0;
    else if (fracStr.length === 2) fracVal = parseInt(fracStr, 10) / 100.0;
    else fracVal = 0.0;
    const lineVal = whole < 0 ? whole - fracVal : whole + fracVal;
    const [homeP, awayP] = asianHandicap(m, lineVal);
    return { 0: homeP, 1: awayP };
  }

  // ── Home/away which half more goals: [more 1H, equal, more 2H] ───────────
  for (const [team, tgHt, tgSh] of [
    ["Hazai csapat melyik félidőben szerez több gólt?", htHg, shHg],
    ["Vendégcsapat melyik félidőben szerez több gólt?", htAg, shAg],
  ] as [string, number[], number[]][]) {
    if (name === team) {
      let p1h = 0.0;
      let pEq = 0.0;
      let p2h = 0.0;
      for (let g1 = 0; g1 < n; g1++) {
        const p1 = g1 < tgHt.length ? tgHt[g1] : 0.0;
        for (let g2 = 0; g2 < n; g2++) {
          const p2 = g2 < tgSh.length ? tgSh[g2] : 0.0;
          const p = p1 * p2;
          if (g1 > g2) p1h += p;
          else if (g1 === g2) pEq += p;
          else p2h += p;
        }
      }
      return { 0: p1h, 1: pEq, 2: p2h };
    }
  }

  // ── Home/away wins both halves / at least one half ───────────────────────
  if (name === "Hazai csapat nyeri mindkét félidőt?")
    return { 0: htHw * shHw, 1: 1.0 - htHw * shHw };
  if (name === "Hazai csapat nyer legalább egy félidőt?") {
    const pNone = (1.0 - htHw) * (1.0 - shHw);
    return { 0: 1.0 - pNone, 1: pNone };
  }
  if (name === "Vendégcsapat nyer legalább egy félidőt?") {
    const pNone = (1.0 - htAw) * (1.0 - shAw);
    return { 0: 1.0 - pNone, 1: pNone };
  }

  // ── 1st/2nd half BTTS combo: [Nem/Nem, Igen/Nem, Igen/Igen, Nem/Igen] ────
  if (name === "1.félidő/2.félidő - Mindkét csapat szerez gólt") {
    const htBtts = sumWhere(ht, (i, j) => i >= 1 && j >= 1);
    const shBtts = sumWhere(sh, (i, j) => i >= 1 && j >= 1);
    const nn = (1.0 - htBtts) * (1.0 - shBtts);
    const yn = htBtts * (1.0 - shBtts);
    const yy = htBtts * shBtts;
    const ny = (1.0 - htBtts) * shBtts;
    return { 0: nn, 1: yn, 2: yy, 3: ny };
  }

  // ── Combination OR markets ───────────────────────────────────────────────
  if (name === "Hazai csapat nyer vagy mindkét csapat szerez gólt") {
    const btts = sumWhere(m, (i, j) => i >= 1 && j >= 1);
    const hwBtts = sumWhere(m, (i, j) => i >= 1 && j >= 1 && i > j);
    const p = hw + btts - hwBtts;
    return { 0: p, 1: 1.0 - p };
  }
  if (name === "Döntetlen vagy mindkét csapat szerez gólt") {
    const btts = sumWhere(m, (i, j) => i >= 1 && j >= 1);
    const drBtts = sumWhere(m, (i, j) => i >= 1 && j >= 1 && i === j);
    const p = dr + btts - drBtts;
    return { 0: p, 1: 1.0 - p };
  }
  if (name === "Vendégcsapat nyer vagy mindkét csapat szerez gólt") {
    const btts = sumWhere(m, (i, j) => i >= 1 && j >= 1);
    const awBtts = sumWhere(m, (i, j) => i >= 1 && j >= 1 && j > i);
    const p = aw + btts - awBtts;
    return { 0: p, 1: 1.0 - p };
  }

  // Home win / draw / away win OR under/over 2.5
  for (const [result, rProb] of [
    ["Hazai csapat nyer", hw],
    ["Döntetlen", dr],
    ["Vendégcsapat nyer", aw],
  ] as [string, number][]) {
    for (const [direction, dirFn] of [
      ["kevesebb", (t: number) => t <= 2.5],
      ["több", (t: number) => t > 2.5],
    ] as [string, (t: number) => boolean][]) {
      const cname = `${result} vagy ${direction} gól lesz, mint 2,5?`;
      if (name === cname) {
        let rKey: (i: number, j: number) => boolean;
        if (result === "Hazai csapat nyer") rKey = (i, j) => i > j;
        else if (result === "Döntetlen") rKey = (i, j) => i === j;
        else rKey = (i, j) => j > i;
        const pDir = sumWhere(m, (i, j) => dirFn(i + j));
        const pAnd = sumWhere(m, (i, j) => rKey(i, j) && dirFn(i + j));
        const p = rProb + pDir - pAnd;
        return { 0: p, 1: 1.0 - p };
      }
    }
  }

  // ── Goal in first 30 minutes ─────────────────────────────────────────────
  if (name === "Lesz gól az első 30 percben (0:00-29:59)?") {
    const m30 = halfMatrix(expH, expA, 1.0 / 3.0);
    const pNoGoal = sumWhere(m30, (i, j) => i + j === 0);
    return { 0: 1.0 - pNoGoal, 1: pNoGoal };
  }

  // ── Corner markets (approximate — Poisson model from xG) ─────────────────
  const CORN_MAX = 25;
  const cornH = Math.max(0.5, 2.3 + 2.5 * expH);
  const cornA = Math.max(0.5, 2.3 + 2.5 * expA);
  const cornTotal = cornH + cornA;
  const htCornH = HT_FRAC * cornH;
  const htCornA = HT_FRAC * cornA;
  const htCornTotal = htCornH + htCornA;
  const k25 = arange(CORN_MAX);

  const tailSum = (pmf: number[], from: number): number => {
    let s = 0;
    for (let i = from; i < pmf.length; i++) s += pmf[i];
    return s;
  };
  const rangeSum = (pmf: number[], from: number, to: number): number => {
    let s = 0;
    for (let i = from; i < Math.min(to, pmf.length); i++) s += pmf[i];
    return s;
  };

  // Total corner O/U (e.g. "Szögletszám 8,5") and HT variant
  for (const [cornPrefix, cornLam] of [
    ["Szögletszám", cornTotal],
    ["1. félidő - Szögletszám", htCornTotal],
  ] as [string, number][]) {
    const cm = name.match(new RegExp(`^${escapeRe(cornPrefix)} (\\d+),5$`));
    if (cm) {
      const line = parseInt(cm[1], 10) + 0.5;
      const pmf = poissonPmf(k25, cornLam);
      const over = tailSum(pmf, Math.trunc(line + 0.5));
      return { 0: 1.0 - over, 1: over };
    }
  }

  // Corner count ranges [0-8, 9-11, 12+]
  if (name === "Szögletek száma") {
    const pmf = poissonPmf(k25, cornTotal);
    return {
      0: rangeSum(pmf, 0, 9),
      1: rangeSum(pmf, 9, 12),
      2: tailSum(pmf, 12),
    };
  }
  if (name === "1. félidő - Szögletek száma") {
    const pmf = poissonPmf(k25, htCornTotal);
    return {
      0: rangeSum(pmf, 0, 5),
      1: rangeSum(pmf, 5, 7),
      2: tailSum(pmf, 7),
    };
  }

  // Home / away corner O/U (e.g. "Hazai csapat szögletszám 5,5")
  for (const [cornPrefix, cornLam] of [
    ["Hazai csapat szögletszám", cornH],
    ["Vendégcsapat szögletszám", cornA],
  ] as [string, number][]) {
    const cm = name.match(new RegExp(`^${escapeRe(cornPrefix)} (\\d+),5$`));
    if (cm) {
      const line = parseInt(cm[1], 10) + 0.5;
      const pmf = poissonPmf(k25, cornLam);
      const over = tailSum(pmf, Math.trunc(line + 0.5));
      return { 0: 1.0 - over, 1: over };
    }
  }

  // Team corner ranges [0-2, 3-4, 5-6, 7+]
  for (const [cornMkt, cornLam] of [
    ["Hazai csapat szögleteinek száma", cornH],
    ["Vendégcsapat szögleteinek száma", cornA],
  ] as [string, number][]) {
    if (name === cornMkt) {
      const pmf = poissonPmf(k25, cornLam);
      return {
        0: rangeSum(pmf, 0, 3),
        1: rangeSum(pmf, 3, 5),
        2: rangeSum(pmf, 5, 7),
        3: tailSum(pmf, 7),
      };
    }
  }

  // Corner handicap (e.g. "Szöglet hendikep -3,5") — [home, away]
  for (const [cornPrefix, cornLamH, cornLamA] of [
    ["Szöglet hendikep", cornH, cornA],
    ["1. félidő - Szöglet hendikep", htCornH, htCornA],
  ] as [string, number, number][]) {
    const cm = name.match(
      new RegExp(`^${escapeRe(cornPrefix)} ([+-]?\\d+),5$`)
    );
    if (cm) {
      const lint = parseInt(cm[1], 10);
      const lval = lint + (lint < 0 ? -0.5 : 0.5);
      const ph = poissonPmf(k25, cornLamH);
      const pa = poissonPmf(k25, cornLamA);
      let hp = 0.0;
      let ap = 0.0;
      for (let ci = 0; ci < ph.length; ci++)
        for (let cj = 0; cj < pa.length; cj++) {
          if (ci - cj > -lval) hp += ph[ci] * pa[cj];
          else ap += ph[ci] * pa[cj];
        }
      return { 0: hp, 1: ap };
    }
  }

  // Which team more corners [home, equal, away]
  for (const [cornMkt, cornLamH, cornLamA] of [
    ["Melyik csapat végez el több szögletet?", cornH, cornA],
    ["1. félidő - Melyik csapat végez el több szögletet?", htCornH, htCornA],
  ] as [string, number, number][]) {
    if (name === cornMkt) {
      const ph = poissonPmf(k25, cornLamH);
      const pa = poissonPmf(k25, cornLamA);
      let pHm = 0.0;
      let pEq = 0.0;
      let pAm = 0.0;
      for (let ci = 0; ci < ph.length; ci++)
        for (let cj = 0; cj < pa.length; cj++) {
          const p = ph[ci] * pa[cj];
          if (ci > cj) pHm += p;
          else if (ci === cj) pEq += p;
          else pAm += p;
        }
      return { 0: pHm, 1: pEq, 2: pAm };
    }
  }

  // Corner odd/even
  if (name === "Szögletszám: páros vagy páratlan") {
    const pmf = poissonPmf(k25, cornTotal);
    let odd = 0;
    for (let i = 1; i < pmf.length; i += 2) odd += pmf[i];
    return { 0: odd, 1: 1.0 - odd };
  }

  // ── Offside markets (approximate — Poisson model from xG) ────────────────
  const offsH = Math.max(0.1, 0.7 + 1.3 * expH);
  const offsA = Math.max(0.1, 0.7 + 1.3 * expA);
  const k20 = arange(19); // np.arange(0, 20)

  // Total offside O/U (e.g. "Lesszám 3,5")
  let cm = name.match(/^Lesszám (\d+),5$/);
  if (cm) {
    const line = parseInt(cm[1], 10) + 0.5;
    const pmf = poissonPmf(k20, offsH + offsA);
    const over = tailSum(pmf, Math.trunc(line + 0.5));
    return { 0: 1.0 - over, 1: over };
  }

  // Team offside O/U (e.g. "Hazai csapat - Lesszám 1,5")
  for (const [offPrefix, offLam] of [
    ["Hazai csapat - Lesszám", offsH],
    ["Vendégcsapat - Lesszám", offsA],
  ] as [string, number][]) {
    cm = name.match(new RegExp(`^${escapeRe(offPrefix)} (\\d+),5$`));
    if (cm) {
      const line = parseInt(cm[1], 10) + 0.5;
      const pmf = poissonPmf(k20, offLam);
      const over = tailSum(pmf, Math.trunc(line + 0.5));
      return { 0: 1.0 - over, 1: over };
    }
  }

  return null; // not predictable
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// ---------------------------------------------------------------------------
// Exact score parser (for Pontos végeredmény market)
// ---------------------------------------------------------------------------

export function parseExactScoreOutcome(
  outcomeName: string,
  homeHu: string,
  awayHu: string
): [number, number] | null {
  const rx = outcomeName.trim().match(/^(.+?)\s+(\d+):(\d+)$/);
  if (!rx) return null;
  const teamName = rx[1].trim();
  const score1 = parseInt(rx[2], 10);
  const score2 = parseInt(rx[3], 10);

  if (teamName === "Döntetlen" || teamName === "Egyenlő")
    return [score1, score2]; // draw: home:away format

  if (homeHu && teamName.toLowerCase() === homeHu.toLowerCase())
    return [score1, score2]; // home wins
  if (awayHu && teamName.toLowerCase() === awayHu.toLowerCase())
    return [score2, score1]; // away wins

  return null;
}
