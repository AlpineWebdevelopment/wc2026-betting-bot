/**
 * Yellow card model — port of card_model.py.
 * Bayesian rate model with referee factor; loaded from card_model_params.json.
 */
import cardParams from "@/card_model_params.json";
import { poissonPmf, arange } from "@/lib/stats";
import { convolve, tailSum } from "@/lib/matrix";
import { round } from "@/lib/util";

const MAX_CARDS = 15;

export interface CardProbs {
  exp_home_cards: number;
  exp_away_cards: number;
  exp_total_cards: number;
  ref_factor: number;
  referee: string | null;
  ref_known: boolean;
  ou_probs: Record<number, { over: number; under: number }>;
}

interface ParamsFile {
  global_avg: number;
  global_home: number;
  global_away: number;
  team_home_rates: Record<string, number>;
  team_away_rates: Record<string, number>;
  ref_rates: Record<string, number>;
  teams: string[];
}

class CardModel {
  teams: string[];
  private globalAvg: number;
  private globalHome: number;
  private globalAway: number;
  private teamHomeRates: Record<string, number>;
  private teamAwayRates: Record<string, number>;
  private refRates: Record<string, number>;

  constructor(d: ParamsFile) {
    this.globalAvg = d.global_avg;
    this.globalHome = d.global_home ?? d.global_avg / 2;
    this.globalAway = d.global_away ?? d.global_avg / 2;
    this.teamHomeRates = d.team_home_rates;
    this.teamAwayRates = d.team_away_rates;
    this.refRates = d.ref_rates ?? {};
    this.teams = d.teams ?? Object.keys(d.team_home_rates);
  }

  predict(homeTeam: string, awayTeam: string, referee: string | null = null): CardProbs {
    let expHome = this.teamHomeRates[homeTeam] ?? this.globalHome;
    let expAway = this.teamAwayRates[awayTeam] ?? this.globalAway;

    let refFactor = 1.0;
    if (referee && referee in this.refRates) {
      const refTotal = this.refRates[referee];
      refFactor = this.globalAvg > 0 ? refTotal / this.globalAvg : 1.0;
    }

    expHome *= refFactor;
    expAway *= refFactor;
    const expTotal = expHome + expAway;

    const cards = arange(MAX_CARDS);
    const ph = poissonPmf(cards, Math.max(0.01, expHome));
    const pa = poissonPmf(cards, Math.max(0.01, expAway));
    const totalDist = convolve(ph, pa).slice(0, 2 * MAX_CARDS + 1);

    const ouProbs: Record<number, { over: number; under: number }> = {};
    for (const line of [1.5, 2.5, 3.5, 4.5, 5.5]) {
      const k = Math.trunc(line - 0.5);
      const over = tailSum(totalDist, k + 1);
      ouProbs[line] = { over: round(over, 4), under: round(1 - over, 4) };
    }

    return {
      exp_home_cards: round(expHome, 2),
      exp_away_cards: round(expAway, 2),
      exp_total_cards: round(expTotal, 2),
      ref_factor: round(refFactor, 3),
      referee,
      ref_known: referee ? referee in this.refRates : false,
      ou_probs: ouProbs,
    };
  }
}

export const cardModel = new CardModel(cardParams as ParamsFile);
