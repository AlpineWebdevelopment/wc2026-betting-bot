"""
Flask web server — serves the WC 2026 betting model on localhost:3000
Run: python app.py
"""

from flask import Flask, render_template, request, jsonify
from data import fetch_data
from model import PoissonModel
from odds import get_wc_odds, best_odds
from valuebets import find_value_bets
from config import THE_ODDS_API_KEY, WC_HOSTS
from tippmix import get_tippmix_matches

app = Flask(__name__)

# ── Boot: load pre-trained params (fast) or train from scratch ───────────────
print("\nBooting WC 2026 Betting Model...")
import os as _os
if _os.path.exists("model_params.json"):
    _model = PoissonModel.load("model_params.json")
else:
    _df    = fetch_data()
    _model = PoissonModel().fit(_df)
_live_odds: dict[str, dict] = {}   # "HomeTeam|AwayTeam" -> match dict

def _refresh_odds():
    global _live_odds
    _live_odds = {}
    if THE_ODDS_API_KEY:
        for m in get_wc_odds():
            key = f"{m['home_team']}|{m['away_team']}"
            _live_odds[key] = m

_refresh_odds()
print("Model ready.\n")


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/predict")
def predict():
    home    = request.args.get("home", "").strip()
    away    = request.args.get("away", "").strip()
    neutral = request.args.get("neutral", "true").lower() != "false"

    if not home or not away:
        return jsonify({"error": "Provide home and away team names."}), 400
    if home == away:
        return jsonify({"error": "Teams must be different."}), 400

    # Hosts get home advantage at their own venues
    if home in WC_HOSTS:
        neutral = False

    probs = _model.predict(home, away, neutral=neutral)

    # Try exact match in live odds, then reversed
    match_data  = _live_odds.get(f"{home}|{away}")
    reversed_   = _live_odds.get(f"{away}|{home}")
    value_bets  = []

    if match_data:
        bo = best_odds(match_data)
        value_bets = find_value_bets(probs, bo, home, away)
    elif reversed_:
        # Odds were fetched with teams swapped — flip probabilities
        flipped = {
            "home_win": probs["away_win"],
            "draw":     probs["draw"],
            "away_win": probs["home_win"],
            "exp_home_goals": probs["exp_away_goals"],
            "exp_away_goals": probs["exp_home_goals"],
        }
        bo = best_odds(reversed_)
        value_bets = find_value_bets(flipped, bo, away, home)

    return jsonify({
        "home_team":       home,
        "away_team":       away,
        "home_win":        round(probs["home_win"], 4),
        "draw":            round(probs["draw"],     4),
        "away_win":        round(probs["away_win"], 4),
        "exp_home_goals":  probs["exp_home_goals"],
        "exp_away_goals":  probs["exp_away_goals"],
        "value_bets":      value_bets,
    })


@app.route("/teams")
def teams():
    return jsonify(sorted(_model.teams))


@app.route("/refresh-odds")
def refresh_odds():
    if not THE_ODDS_API_KEY:
        return jsonify({"status": "no_key", "message": "Add THE_ODDS_API_KEY in config.py"}), 200
    _refresh_odds()
    return jsonify({"status": "ok", "matches_loaded": len(_live_odds)})


@app.route("/live-matches")
def live_matches():
    """Return all matches that have live odds, with full value bet analysis."""
    results = []
    for key, m in _live_odds.items():
        home, away = m["home_team"], m["away_team"]
        neutral = home not in WC_HOSTS
        probs   = _model.predict(home, away, neutral=neutral)
        bo      = best_odds(m)
        vbets   = find_value_bets(probs, bo, home, away)
        results.append({
            "home_team":      home,
            "away_team":      away,
            "commence_time":  m.get("commence_time", ""),
            "home_win":       round(probs["home_win"], 4),
            "draw":           round(probs["draw"],     4),
            "away_win":       round(probs["away_win"], 4),
            "exp_home_goals": probs["exp_home_goals"],
            "exp_away_goals": probs["exp_away_goals"],
            "value_bets":     vbets,
            "has_value":      any(v["value"] for v in vbets),
        })
    # Sort: value bets first, then by max edge
    results.sort(key=lambda r: (
        -int(r["has_value"]),
        -max((v["edge_pct"] for v in r["value_bets"]), default=0)
    ))
    return jsonify(results)


@app.route("/tippmix-matches")
def tippmix_matches():
    """Fetch live Tippmix.hu odds, run model, return value bets."""
    try:
        matches = get_tippmix_matches()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    results = []
    for m in matches:
        home, away = m["home_team"], m["away_team"]
        neutral = home not in WC_HOSTS
        probs   = _model.predict(home, away, neutral=neutral)
        tm_odds = {
            "home_odds": m["home_odds"],
            "draw_odds": m["draw_odds"],
            "away_odds": m["away_odds"],
        }
        vbets = find_value_bets(probs, tm_odds, home, away)
        results.append({
            "home_team":      home,
            "away_team":      away,
            "home_team_hu":   m["home_team_hu"],
            "away_team_hu":   m["away_team_hu"],
            "competition":    m["competition"],
            "is_wc":          m["is_wc"],
            "event_date":     m["event_date"],
            "home_odds":      m["home_odds"],
            "draw_odds":      m["draw_odds"],
            "away_odds":      m["away_odds"],
            "home_win":       round(probs["home_win"], 4),
            "draw":           round(probs["draw"],     4),
            "away_win":       round(probs["away_win"], 4),
            "exp_home_goals": probs["exp_home_goals"],
            "exp_away_goals": probs["exp_away_goals"],
            "value_bets":     vbets,
            "has_value":      any(v["value"] for v in vbets),
        })

    results.sort(key=lambda r: (-int(r["is_wc"]), -int(r["has_value"]),
                                 -max((v["edge_pct"] for v in r["value_bets"]), default=0)))
    return jsonify(results)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3001, debug=False)
