"""
Poisson corner model — mirrors PoissonModel exactly but trained on corner counts.
Attack = corner-winning tendency. Defense = corner-conceding tendency.
"""
import json, os
import numpy as np
from datetime import datetime
from stats import poisson_pmf
from config import TIME_DECAY

PARAMS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corner_model_params.json")
MAX_CORNERS = 20  # max corners to consider in distribution


class CornerModel:
    def __init__(self):
        self.params = None
        self.teams: list[str] = []
        self.team_idx: dict[str, int] = {}
        self._avg_attack = 0.0
        self._avg_defense = 0.0

    @classmethod
    def load(cls, path: str = None):
        path = path or PARAMS_PATH
        with open(path) as f:
            data = json.load(f)
        m = cls()
        m.teams = data["teams"]
        m.team_idx = {t: i for i, t in enumerate(m.teams)}
        m.params = np.array(data["params"])
        m._avg_attack = data["avg_attack"]
        m._avg_defense = data["avg_defense"]
        print(f"  Loaded corner model ({len(m.teams)} teams)")
        return m

    def save(self, path: str = None):
        path = path or PARAMS_PATH
        with open(path, "w") as f:
            json.dump({
                "teams": self.teams,
                "params": self.params.tolist(),
                "avg_attack": self._avg_attack,
                "avg_defense": self._avg_defense,
            }, f)

    def fit(self, matches: list[dict]):
        """
        matches: list of dicts with keys: home_team, away_team, home_corners, away_corners, date (str), weight (float)
        """
        import pandas as pd
        from scipy.optimize import minimize

        df = pd.DataFrame(matches)
        df["date"] = pd.to_datetime(df["date"])
        df = df.dropna(subset=["home_corners", "away_corners"])
        df["home_corners"] = df["home_corners"].astype(int)
        df["away_corners"] = df["away_corners"].astype(int)
        # Drop obviously bad data (0-0 corners unlikely but possible)
        df = df[df["home_corners"] + df["away_corners"] >= 1]

        teams = sorted(set(df["home_team"]) | set(df["away_team"]))
        self.teams = teams
        self.team_idx = {t: i for i, t in enumerate(teams)}
        n = len(teams)

        days_ago = (datetime.now() - df["date"]).dt.days.values
        time_w = np.exp(-TIME_DECAY * days_ago) * df["weight"].values

        x0 = np.zeros(2 + 2 * n)
        x0[0] = np.log((df["home_corners"].mean() + df["away_corners"].mean()) / 2)
        x0[1] = 0.1

        home_idx = [self.team_idx[t] for t in df["home_team"]]
        away_idx = [self.team_idx[t] for t in df["away_team"]]
        h_c = df["home_corners"].values
        a_c = df["away_corners"].values

        def neg_ll(params):
            from scipy.stats import poisson
            mu, hav = params[0], params[1]
            atk, dfn = params[2:2+n], params[2+n:]
            exp_h = np.exp(mu + hav + atk[home_idx] - dfn[away_idx])
            exp_a = np.exp(mu + atk[away_idx] - dfn[home_idx])
            ll = time_w * (poisson.logpmf(h_c, exp_h) + poisson.logpmf(a_c, exp_a))
            penalty = 100.0 * (np.sum(atk)**2 + np.sum(dfn)**2)
            return -(np.sum(ll) - penalty)

        print(f"  Fitting corner model on {len(df):,} matches for {n} teams...")
        res = minimize(neg_ll, x0, method="L-BFGS-B",
                       options={"maxiter": 5000, "ftol": 1e-8, "gtol": 1e-6})
        self.params = res.x
        self._avg_attack = float(np.mean(res.x[2:2+n]))
        self._avg_defense = float(np.mean(res.x[2+n:]))
        print(f"  Corner model fitted. Convergence: {res.message}")
        return self

    def predict(self, home_team: str, away_team: str) -> dict:
        """Returns expected corners and O/U probabilities."""
        n = len(self.teams)
        mu, hav = self.params[0], self.params[1]
        atk, dfn = self.params[2:2+n], self.params[2+n:]

        def _atk(t):
            i = self.team_idx.get(t)
            return float(atk[i]) if i is not None else self._avg_attack

        def _dfn(t):
            i = self.team_idx.get(t)
            return float(dfn[i]) if i is not None else self._avg_defense

        # WC matches are always neutral venue for corners
        exp_h = np.exp(mu + _atk(home_team) - _dfn(away_team))
        exp_a = np.exp(mu + _atk(away_team) - _dfn(home_team))

        corners = np.arange(0, MAX_CORNERS + 1)
        ph = poisson_pmf(corners, exp_h)
        pa = poisson_pmf(corners, exp_a)

        # Total corners distribution (convolution)
        total_dist = np.convolve(ph, pa)[:2*MAX_CORNERS+1]

        # O/U probabilities for common lines
        ou_probs = {}
        for line in [6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5]:
            k = int(line - 0.5)  # e.g. 9.5 → k=9 → P(total > 9.5) = P(total >= 10)
            over = float(np.sum(total_dist[k+1:]))
            ou_probs[line] = {"over": round(over, 4), "under": round(1 - over, 4)}

        # Team-specific corner O/U
        team_ou = {}
        for line in [3.5, 4.5, 5.5, 6.5]:
            k = int(line - 0.5)
            team_ou[line] = {
                "home_over": round(float(np.sum(ph[k+1:])), 4),
                "away_over": round(float(np.sum(pa[k+1:])), 4),
            }

        return {
            "exp_home_corners": round(exp_h, 2),
            "exp_away_corners": round(exp_a, 2),
            "exp_total_corners": round(exp_h + exp_a, 2),
            "ou_probs": ou_probs,
            "team_ou": team_ou,
        }
