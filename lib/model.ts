/**
 * Poisson goals model — prediction path ported from model.py.
 * Attack/defense ratings are loaded from the pre-trained model_params.json.
 * (Training, which used scipy.optimize, is local-only and not part of the runtime.)
 */
import modelParams from "@/model_params.json";
import { MAX_GOALS, WC_HOSTS } from "@/lib/config";
import { poissonPmf, arange } from "@/lib/stats";
import {
  outer,
  sumStrictLower,
  sumDiag,
  sumStrictUpper,
} from "@/lib/matrix";
import { round } from "@/lib/util";

export interface Probs {
  home_win: number;
  draw: number;
  away_win: number;
  exp_home_goals: number;
  exp_away_goals: number;
  score_matrix: number[][];
}

interface ParamsFile {
  teams: string[];
  params: number[];
  avg_attack: number;
  avg_defense: number;
}

class PoissonModel {
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

  predict(homeTeam: string, awayTeam: string, neutral = true): Probs {
    const n = this.teams.length;
    const mu = this.params[0];
    const hav = this.params[1];
    const atk = this.params.slice(2, 2 + n);
    const dfn = this.params.slice(2 + n);

    const atkOf = (team: string): number => {
      const i = this.teamIdx.get(team);
      return i !== undefined ? atk[i] : this.avgAttack;
    };
    const dfnOf = (team: string): number => {
      const i = this.teamIdx.get(team);
      return i !== undefined ? dfn[i] : this.avgDefense;
    };

    // At WC most matches are neutral — no home advantage.
    // Exception: US/Canada/Mexico playing on home soil.
    const homeBoost =
      !neutral || WC_HOSTS.has(homeTeam) ? hav : 0.0;

    const expH = Math.exp(
      mu + homeBoost + atkOf(homeTeam) - dfnOf(awayTeam)
    );
    const expA = Math.exp(mu + atkOf(awayTeam) - dfnOf(homeTeam));

    const goals = arange(MAX_GOALS);
    const ph = poissonPmf(goals, expH);
    const pa = poissonPmf(goals, expA);
    const matrix = outer(ph, pa);

    return {
      home_win: sumStrictLower(matrix),
      draw: sumDiag(matrix),
      away_win: sumStrictUpper(matrix),
      exp_home_goals: round(expH, 2),
      exp_away_goals: round(expA, 2),
      score_matrix: matrix,
    };
  }
}

// Module-level singleton — loaded once per serverless instance.
export const model = new PoissonModel(modelParams as ParamsFile);
