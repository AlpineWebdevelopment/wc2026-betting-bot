/**
 * Bet outcome evaluator — port of app.py `_eval_bet`.
 * Returns 'win','half_win','push','half_loss','loss','no_data','pending','unknown'.
 */

export interface EvalBet {
  market?: string;
  outcome?: string;
  market_group?: string;
}

const pn = (s: string): number => parseFloat(s.trim().replace(",", "."));

export function evalBet(
  bet: EvalBet | null | undefined,
  homeScore: number | null,
  awayScore: number | null,
  homeHu: string,
  awayHu: string,
  homeCorners: number | null = null,
  awayCorners: number | null = null,
  homeOffsides: number | null = null,
  awayOffsides: number | null = null
): string {
  if (!bet) return "unknown";
  const mkt = bet.market ?? "";
  const out = bet.outcome ?? "";
  const mg = bet.market_group ?? "";

  // Corner bets
  if (mg === "Szögletek" || mg === "Statisztika") {
    if (homeCorners === null || awayCorners === null) return "no_data";
    const totalC = homeCorners + awayCorners;
    if (out.startsWith("Több, mint "))
      return totalC > pn(out.slice(11)) ? "win" : "loss";
    if (out.startsWith("Kevesebb, mint "))
      return totalC < pn(out.slice(15)) ? "win" : "loss";
    for (const [kw, cscore] of [
      ["Hazai", homeCorners],
      ["Vendég", awayCorners],
    ] as [string, number][]) {
      if (mkt.includes(kw)) {
        if (out.startsWith("Több, mint "))
          return cscore > pn(out.slice(11)) ? "win" : "loss";
        if (out.startsWith("Kevesebb, mint "))
          return cscore < pn(out.slice(15)) ? "win" : "loss";
      }
    }
    return "unknown";
  }

  // Offside count bets
  if (mkt.includes("Lesszám")) {
    if (homeOffsides === null || awayOffsides === null) return "no_data";
    const totalOs = homeOffsides + awayOffsides;
    if (out.startsWith("Több, mint "))
      return totalOs > pn(out.slice(11)) ? "win" : "loss";
    if (out.startsWith("Kevesebb, mint "))
      return totalOs < pn(out.slice(15)) ? "win" : "loss";
    for (const [kw, oscore] of [
      ["Hazai", homeOffsides],
      ["Vendég", awayOffsides],
    ] as [string, number][]) {
      if (mkt.includes(kw)) {
        if (out.startsWith("Több, mint "))
          return oscore > pn(out.slice(11)) ? "win" : "loss";
        if (out.startsWith("Kevesebb, mint "))
          return oscore < pn(out.slice(15)) ? "win" : "loss";
      }
    }
    return "unknown";
  }

  if (homeScore === null || awayScore === null) return "pending";
  const total = homeScore + awayScore;

  // Total goals O/U
  if (out.startsWith("Több, mint ")) {
    const line = pn(out.slice(11));
    return total > line ? "win" : total === line ? "push" : "loss";
  }
  if (out.startsWith("Kevesebb, mint ")) {
    const line = pn(out.slice(15));
    return total < line ? "win" : total === line ? "push" : "loss";
  }

  // Team-specific goals
  for (const [kw, score] of [
    ["Hazai", homeScore],
    ["Vendég", awayScore],
  ] as [string, number][]) {
    if (mkt.includes(kw)) {
      if (out.startsWith("Több, mint "))
        return score > pn(out.slice(11)) ? "win" : "loss";
      if (out.startsWith("Kevesebb, mint "))
        return score < pn(out.slice(15)) ? "win" : "loss";
    }
  }

  // DNB
  if (mkt.includes("Döntetlennél")) {
    const isHome = (homeHu && out.includes(homeHu)) || out.includes("Hazai");
    const isAway = (awayHu && out.includes(awayHu)) || out.includes("Vendég");
    if (isHome)
      return homeScore > awayScore ? "win" : homeScore === awayScore ? "push" : "loss";
    if (isAway)
      return awayScore > homeScore ? "win" : homeScore === awayScore ? "push" : "loss";
  }

  // 1X2
  if (mkt === "1X2") {
    if (out.includes("Hazai győzelem") || (homeHu && out === homeHu))
      return homeScore > awayScore ? "win" : "loss";
    if (out.includes("Döntetlen")) return homeScore === awayScore ? "win" : "loss";
    if (out.includes("Vendég győzelem") || (awayHu && out === awayHu))
      return awayScore > homeScore ? "win" : "loss";
  }

  // Asian Handicap
  if (mkt.includes("Hendikep")) {
    const m = out.match(/([+-]?\d+[,.]?\d*)\s*$/);
    if (m) {
      const hcap = pn(m[1]);
      const isHome = Boolean(homeHu && out.includes(homeHu));
      const margin = isHome ? homeScore - awayScore : awayScore - homeScore;
      const fq = Math.round(Math.abs(hcap) * 4) % 4; // 0=whole,1=.25,2=.5,3=.75
      if (fq === 0) {
        const adj = margin + hcap;
        return adj > 0 ? "win" : adj === 0 ? "push" : "loss";
      } else if (fq === 2) {
        return margin + hcap > 0 ? "win" : "loss";
      } else if (fq === 3) {
        // -0.75: split into -0.5 and -1.0
        const pHalf = hcap + (hcap < 0 ? 0.25 : -0.25); // -0.5 part
        const pWhole = hcap - (hcap < 0 ? 0.25 : -0.25); // -1.0 part
        const rHalf = margin + pHalf > 0 ? "win" : "loss";
        const rWhole =
          margin + pWhole > 0 ? "win" : margin + pWhole === 0 ? "push" : "loss";
        if (rHalf === "win" && rWhole === "win") return "win";
        if (rHalf === "loss" && rWhole === "loss") return "loss";
        if (rHalf === "win" && rWhole === "push") return "half_win";
        if (rHalf === "loss" && rWhole === "push") return "half_loss";
        return "half_win";
      } else {
        // .25: split into 0 (DNB) and -0.5
        const pDnb = hcap + (hcap < 0 ? 0.25 : -0.25);
        const pHalf = hcap - (hcap < 0 ? 0.25 : -0.25);
        const rDnb =
          margin + pDnb > 0 ? "win" : margin + pDnb === 0 ? "push" : "loss";
        const rHalf = margin + pHalf > 0 ? "win" : "loss";
        if (rDnb === "win" && rHalf === "win") return "win";
        if (rDnb === "loss" && rHalf === "loss") return "loss";
        if (rDnb === "push" && rHalf === "win") return "half_win";
        if (rDnb === "push" && rHalf === "loss") return "half_loss";
        if (rDnb === "win" && rHalf === "loss") return "half_win";
        return "half_win";
      }
    }
  }

  // Asian total goals
  if (mkt.includes("Gólszám")) {
    const m2 = mkt.match(/(\d+[,.]?\d*)\s*$/);
    if (m2) {
      const line = pn(m2[1]);
      if (out.includes("Kevesebb"))
        return total < line ? "win" : total === line ? "push" : "loss";
      if (out.includes("Több"))
        return total > line ? "win" : total === line ? "push" : "loss";
    }
  }

  // BTTS
  if (mkt.includes("Mindkét")) {
    const btts = homeScore > 0 && awayScore > 0;
    if (out.includes("Igen")) return btts ? "win" : "loss";
    if (out.includes("Nem")) return !btts ? "win" : "loss";
  }

  // Complex "team wins or under X goals"
  if (mkt.includes("Vendégcsapat nyer") && out.includes("Igen"))
    return awayScore > homeScore || total <= 2 ? "win" : "loss";
  if (mkt.includes("Hazai csapat nyer") && out.includes("Igen"))
    return homeScore > awayScore || total <= 2 ? "win" : "loss";

  return "unknown";
}
