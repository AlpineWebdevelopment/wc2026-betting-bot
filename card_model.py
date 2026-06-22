"""
Yellow card model — Bayesian rate model with referee factor.
Predicts expected yellow cards using team rates + referee strictness.
"""
import json, os, math
from collections import defaultdict
from stats import poisson_pmf
import numpy as np

PARAMS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "card_model_params.json")
MAX_CARDS = 15
_GLOBAL_PRIOR = 3.5   # global prior for total cards per match
_PRIOR_K_TEAM = 8     # Bayesian smoothing strength for team rates
_PRIOR_K_REF  = 15    # Bayesian smoothing strength for referee rates (less data)


class CardModel:
    def __init__(self):
        self.global_avg    = _GLOBAL_PRIOR
        self.global_home   = _GLOBAL_PRIOR / 2
        self.global_away   = _GLOBAL_PRIOR / 2
        self.team_home_rates: dict[str, float] = {}   # team → cards/game when home
        self.team_away_rates: dict[str, float] = {}   # team → cards/game when away
        self.ref_rates:       dict[str, float] = {}   # referee → total cards/game
        self.teams: list[str] = []

    def fit(self, matches: list[dict]):
        """
        matches: list of dicts with home_team, away_team, home_yellows, away_yellows,
                 optionally referee, weight (float)
        """
        home_samples  = defaultdict(list)
        away_samples  = defaultdict(list)
        ref_samples   = defaultdict(list)
        total_yellows = []

        for m in matches:
            hy = m.get("home_yellows")
            ay = m.get("away_yellows")
            if hy is None or ay is None:
                continue
            w = float(m.get("weight", 1.0))
            home_samples[m["home_team"]].extend([hy] * round(w))
            away_samples[m["away_team"]].extend([ay] * round(w))
            total_yellows.extend([hy + ay] * round(w))
            if m.get("referee"):
                ref_samples[m["referee"]].extend([hy + ay] * round(w))

        # Global averages
        if total_yellows:
            self.global_avg  = sum(total_yellows) / len(total_yellows)
            home_all = [v for vals in home_samples.values() for v in vals]
            away_all = [v for vals in away_samples.values() for v in vals]
            self.global_home = sum(home_all) / len(home_all) if home_all else self.global_avg / 2
            self.global_away = sum(away_all) / len(away_all) if away_all else self.global_avg / 2

        # Bayesian smoothed team rates
        self.team_home_rates = {}
        for team, vals in home_samples.items():
            n = len(vals)
            self.team_home_rates[team] = (sum(vals) + _PRIOR_K_TEAM * self.global_home) / (n + _PRIOR_K_TEAM)

        self.team_away_rates = {}
        for team, vals in away_samples.items():
            n = len(vals)
            self.team_away_rates[team] = (sum(vals) + _PRIOR_K_TEAM * self.global_away) / (n + _PRIOR_K_TEAM)

        # Referee rates
        self.ref_rates = {}
        for ref, vals in ref_samples.items():
            n = len(vals)
            self.ref_rates[ref] = (sum(vals) + _PRIOR_K_REF * self.global_avg) / (n + _PRIOR_K_REF)

        self.teams = sorted(set(home_samples) | set(away_samples))
        print(f"  Card model fit: {len(self.teams)} teams, {len(self.ref_rates)} referees, global_avg={self.global_avg:.2f}")
        return self

    def predict(self, home_team: str, away_team: str, referee: str = None) -> dict:
        """Returns expected cards and O/U probabilities."""
        exp_home = self.team_home_rates.get(home_team, self.global_home)
        exp_away = self.team_away_rates.get(away_team, self.global_away)

        # Referee factor: how strict is this ref relative to average?
        if referee and referee in self.ref_rates:
            ref_total = self.ref_rates[referee]
            ref_factor = ref_total / self.global_avg if self.global_avg > 0 else 1.0
        else:
            ref_factor = 1.0

        exp_home = exp_home * ref_factor
        exp_away = exp_away * ref_factor
        exp_total = exp_home + exp_away

        # Poisson O/U for total cards (convolution)
        cards = np.arange(0, MAX_CARDS + 1)
        ph = poisson_pmf(cards, max(0.01, exp_home))
        pa = poisson_pmf(cards, max(0.01, exp_away))
        total_dist = np.convolve(ph, pa)[:2 * MAX_CARDS + 1]

        ou_probs = {}
        for line in [1.5, 2.5, 3.5, 4.5, 5.5]:
            k = int(line - 0.5)
            over = float(np.sum(total_dist[k + 1:]))
            ou_probs[line] = {"over": round(over, 4), "under": round(1 - over, 4)}

        return {
            "exp_home_cards":  round(exp_home,  2),
            "exp_away_cards":  round(exp_away,  2),
            "exp_total_cards": round(exp_total, 2),
            "ref_factor":      round(ref_factor, 3),
            "referee":         referee,
            "ref_known":       referee in self.ref_rates if referee else False,
            "ou_probs":        ou_probs,
        }

    def save(self, path: str = None):
        path = path or PARAMS_PATH
        with open(path, "w") as f:
            json.dump({
                "global_avg":       self.global_avg,
                "global_home":      self.global_home,
                "global_away":      self.global_away,
                "team_home_rates":  self.team_home_rates,
                "team_away_rates":  self.team_away_rates,
                "ref_rates":        self.ref_rates,
                "teams":            self.teams,
            }, f, indent=2)

    @classmethod
    def load(cls, path: str = None):
        path = path or PARAMS_PATH
        with open(path) as f:
            d = json.load(f)
        m = cls()
        m.global_avg       = d["global_avg"]
        m.global_home      = d.get("global_home", d["global_avg"] / 2)
        m.global_away      = d.get("global_away", d["global_avg"] / 2)
        m.team_home_rates  = d["team_home_rates"]
        m.team_away_rates  = d["team_away_rates"]
        m.ref_rates        = d.get("ref_rates", {})
        m.teams            = d.get("teams", list(d["team_home_rates"].keys()))
        print(f"  Loaded card model ({len(m.teams)} teams, {len(m.ref_rates)} refs)")
        return m
