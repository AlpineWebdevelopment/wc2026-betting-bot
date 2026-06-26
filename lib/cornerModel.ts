/**
 * Poisson corner model — port of corner_model.py.
 * Mirrors PoissonModel but trained on corner counts (attack = corner-winning
 * tendency, defense = corner-conceding tendency). Loaded from
 * corner_model_params.json. WC matches are always treated as neutral venue.
 */
import cornerParams from "@/corner_model_params.json";
import { poissonPmf, arange } from "@/lib/stats";
import { convolve, tailSum } from "@/lib/matrix";
import { round } from "@/lib/util";

const MAX_CORNERS = 20;

export interface CornerProbs {
  exp_home_corners: number;
  exp_away_corners: number;
  exp_total_corners: number;
  ou_probs: Record<number, { over: number; under: number }>;
  team_ou: Record<number, { home_over: number; away_over: number }>;
}

interface ParamsFile {
  teams: string[];
  params: number[];
  avg_attack: number;
  avg_defense: number;
}

class CornerModel {
  teams: string[];
  private teamIdx: Map<string, number>;
  private params: number[];
  private avgAttack: number;
  private avgDefense: number;

  constructor(data: ParamsFile) {
    this.teams = data.teams;
    this.teamIdx = new Map(data.teams.map((t, i) => [t, i]));
    this.params = data.params;
    this.avgAttack = data.avg_attack;
    this.avgDefense = data.avg_defense;
  }

  predict(homeTeam: string, awayTeam: string): CornerProbs {
    const n = this.teams.length;
    const mu = this.params[0];
    const atk = this.params.slice(2, 2 + n);
    const dfn = this.params.slice(2 + n);

    const atkOf = (t: string) => {
      const i = this.teamIdx.get(t);
      return i !== undefined ? atk[i] : this.avgAttack;
    };
    const dfnOf = (t: string) => {
      const i = this.teamIdx.get(t);
      return i !== undefined ? dfn[i] : this.avgDefense;
    };

    const expH = Math.exp(mu + atkOf(homeTeam) - dfnOf(awayTeam));
    const expA = Math.exp(mu + atkOf(awayTeam) - dfnOf(homeTeam));

    const corners = arange(MAX_CORNERS);
    const ph = poissonPmf(corners, expH);
    const pa = poissonPmf(corners, expA);

    // Total corners distribution (convolution)
    const totalDist = convolve(ph, pa).slice(0, 2 * MAX_CORNERS + 1);

    const ouProbs: Record<number, { over: number; under: number }> = {};
    for (const line of [6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5]) {
      const k = Math.trunc(line - 0.5);
      const over = tailSum(totalDist, k + 1);
      ouProbs[line] = { over: round(over, 4), under: round(1 - over, 4) };
    }

    const teamOu: Record<number, { home_over: number; away_over: number }> = {};
    for (const line of [3.5, 4.5, 5.5, 6.5]) {
      const k = Math.trunc(line - 0.5);
      teamOu[line] = {
        home_over: round(tailSum(ph, k + 1), 4),
        away_over: round(tailSum(pa, k + 1), 4),
      };
    }

    return {
      exp_home_corners: round(expH, 2),
      exp_away_corners: round(expA, 2),
      exp_total_corners: round(expH + expA, 2),
      ou_probs: ouProbs,
      team_ou: teamOu,
    };
  }
}

export const cornerModel = new CornerModel(cornerParams as ParamsFile);
