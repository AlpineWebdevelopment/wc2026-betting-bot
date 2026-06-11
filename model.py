"""
Poisson goals model with time decay and weighted fitting.
Attack/defense ratings are estimated via maximum likelihood.
"""

import numpy as np
import pandas as pd
from scipy.stats import poisson
from scipy.optimize import minimize
from datetime import datetime
from config import MAX_GOALS, TIME_DECAY, WC_HOSTS


class PoissonModel:
    def __init__(self):
        self.params = None
        self.teams: list[str] = []
        self.team_idx: dict[str, int] = {}
        self._avg_attack = 0.0
        self._avg_defense = 0.0

    @classmethod
    def load(cls, path: str = "model_params.json"):
        import json
        with open(path) as f:
            data = json.load(f)
        m = cls()
        m.teams = data["teams"]
        m.team_idx = {t: i for i, t in enumerate(m.teams)}
        m.params = np.array(data["params"])
        m._avg_attack = data["avg_attack"]
        m._avg_defense = data["avg_defense"]
        print(f"  Loaded pre-trained model ({len(m.teams)} teams)")
        return m

    # ------------------------------------------------------------------
    def fit(self, df: pd.DataFrame):
        teams = sorted(set(df["home_team"]) | set(df["away_team"]))
        self.teams = teams
        self.team_idx = {t: i for i, t in enumerate(teams)}
        n = len(teams)

        # Time-decay weights
        days_ago = (datetime.now() - df["date"]).dt.days.values
        time_w = np.exp(-TIME_DECAY * days_ago) * df["weight"].values

        # Initial params: [log_mu, home_adv, attack x n, defense x n]
        x0 = np.zeros(2 + 2 * n)
        x0[0] = np.log(df["home_score"].mean() + df["away_score"].mean()) / 2
        x0[1] = 0.1

        home_idx = [self.team_idx[t] for t in df["home_team"]]
        away_idx = [self.team_idx[t] for t in df["away_team"]]
        h_goals = df["home_score"].values
        a_goals = df["away_score"].values

        def neg_ll(params):
            mu = params[0]
            hav = params[1]
            atk = params[2:2 + n]
            dfn = params[2 + n:]

            exp_h = np.exp(mu + hav + atk[home_idx] - dfn[away_idx])
            exp_a = np.exp(mu + atk[away_idx] - dfn[home_idx])

            ll = time_w * (
                poisson.logpmf(h_goals, exp_h) +
                poisson.logpmf(a_goals, exp_a)
            )
            # Sum-to-zero regularisation
            penalty = 100.0 * (np.sum(atk) ** 2 + np.sum(dfn) ** 2)
            return -(np.sum(ll) - penalty)

        print(f"  Fitting model on {len(df):,} matches for {n} teams...")
        res = minimize(neg_ll, x0, method="L-BFGS-B",
                       options={"maxiter": 5000, "ftol": 1e-8, "gtol": 1e-6})
        self.params = res.x

        n = len(self.teams)
        self._avg_attack = float(np.mean(res.x[2:2 + n]))
        self._avg_defense = float(np.mean(res.x[2 + n:]))
        print(f"  Model fitted. Convergence: {res.message}")
        return self

    # ------------------------------------------------------------------
    def predict(self, home_team: str, away_team: str,
                neutral: bool = True) -> dict:
        n = len(self.teams)
        mu = self.params[0]
        hav = self.params[1]
        atk = self.params[2:2 + n]
        dfn = self.params[2 + n:]

        def _atk(team):
            i = self.team_idx.get(team)
            return float(atk[i]) if i is not None else self._avg_attack

        def _dfn(team):
            i = self.team_idx.get(team)
            return float(dfn[i]) if i is not None else self._avg_defense

        # At WC most matches are neutral — no home advantage
        # Exception: US/Canada/Mexico playing on home soil
        home_boost = hav if (not neutral or home_team in WC_HOSTS) else 0.0

        exp_h = np.exp(mu + home_boost + _atk(home_team) - _dfn(away_team))
        exp_a = np.exp(mu + _atk(away_team) - _dfn(home_team))

        goals = np.arange(0, MAX_GOALS + 1)
        ph = poisson.pmf(goals, exp_h)
        pa = poisson.pmf(goals, exp_a)
        matrix = np.outer(ph, pa)

        home_win = float(np.sum(np.tril(matrix, -1)))
        draw = float(np.sum(np.diag(matrix)))
        away_win = float(np.sum(np.triu(matrix, 1)))

        return {
            "home_win": home_win,
            "draw": draw,
            "away_win": away_win,
            "exp_home_goals": round(exp_h, 2),
            "exp_away_goals": round(exp_a, 2),
        }
