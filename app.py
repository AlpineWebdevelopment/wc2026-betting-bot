"""
Flask web server — serves the WC 2026 betting model on localhost:3000
Run: python app.py
"""

import threading
import time as _time

from flask import Flask, render_template, request, jsonify
from model import PoissonModel
from odds import get_wc_odds, best_odds
from valuebets import find_value_bets, find_all_value_bets
from config import THE_ODDS_API_KEY, WC_HOSTS, TELEGRAM_BANKROLL
from tippmix import get_tippmix_matches, get_tippmix_live_odds
from sofascore import get_live_wc_matches
from live_model import live_probs, live_value_bets, find_live_value_bets_from_markets

app = Flask(__name__)

# ── Boot: load pre-trained params (fast) or train from scratch ───────────────
print("\nBooting WC 2026 Betting Model...")
import os as _os
_PARAMS_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "model_params.json")
if _os.path.exists(_PARAMS_PATH):
    _model = PoissonModel.load(_PARAMS_PATH)
else:
    # Training path (local only) — pulls in pandas/scipy via data.py.
    from data import fetch_data
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

# ── In-memory cache for Tippmix live odds (TTL-based, works on both local + Vercel) ──
_tippmix_live_cache: list[dict] = []
_tippmix_live_lock  = threading.Lock()
_tippmix_live_ts    = 0.0
_TIPPMIX_LIVE_TTL   = 120   # seconds before we re-fetch


def _get_tippmix_live_cached() -> tuple[list[dict], float | None]:
    """Return cached live odds, refreshing if stale. Safe for serverless."""
    global _tippmix_live_cache, _tippmix_live_ts
    now = _time.time()
    with _tippmix_live_lock:
        age = round(now - _tippmix_live_ts) if _tippmix_live_ts else None
        if not _tippmix_live_ts or now - _tippmix_live_ts > _TIPPMIX_LIVE_TTL:
            try:
                data = get_tippmix_live_odds()
                _tippmix_live_cache = data
                _tippmix_live_ts    = now
                age = 0
            except Exception as e:
                print(f"  [live cache] Tippmix live fetch failed: {e}")
        return list(_tippmix_live_cache), age


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
    })  # score_matrix intentionally excluded from public response


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

        market_groups = m.get("market_groups", [])
        if m.get("is_wc") and market_groups:
            # Full market analysis for WC matches
            vbets = find_all_value_bets(
                market_groups, probs, m["home_team_hu"], m["away_team_hu"]
            )
        else:
            # 1X2 only for non-WC / missing market data
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


@app.route("/live-wc-matches")
def live_wc_matches():
    """Fetch live WC matches: ESPN stats + Tippmix live odds → full value bet analysis."""
    try:
        espn_matches = get_live_wc_matches()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    tippmix_live, cache_age = _get_tippmix_live_cached()

    # Index Tippmix live matches by team pair for fast lookup
    def _tkey(h, a):
        return f"{h.lower().strip()}|{a.lower().strip()}"

    tippmix_index: dict[str, dict] = {}
    for tm in tippmix_live:
        if tm.get("is_wc"):
            tippmix_index[_tkey(tm["home_team"], tm["away_team"])] = tm

    bankroll = TELEGRAM_BANKROLL
    results = []

    for m in espn_matches:
        home, away = m["home_team"], m["away_team"]
        neutral = home not in WC_HOSTS

        # Pre-match baseline from Poisson model
        try:
            pre = _model.predict(home, away, neutral=neutral)
            pre_xg_h = pre["exp_home_goals"]
            pre_xg_a = pre["exp_away_goals"]
        except Exception:
            pre_xg_h, pre_xg_a = 1.2, 1.0

        # Live probability calculation using ESPN stats
        lp = live_probs(
            pre_xg_home=pre_xg_h,
            pre_xg_away=pre_xg_a,
            minute=m["minute"] + m.get("extra_time", 0),
            home_score=m["home_score"],
            away_score=m["away_score"],
            live_xg_home=m["xg_home"],
            live_xg_away=m["xg_away"],
            red_cards_home=m["red_cards_home"],
            red_cards_away=m["red_cards_away"],
            possession_home=m["possession_home"],
        )

        # Try to find matching Tippmix live event
        tm_match = tippmix_index.get(_tkey(home, away))
        has_tippmix_odds = bool(tm_match and tm_match.get("market_groups"))

        if has_tippmix_odds:
            # Full value bet cards with actual Tippmix odds + Kelly stake
            live_vbets = find_live_value_bets_from_markets(
                tm_match["market_groups"], lp, bankroll=bankroll, min_edge=5.0
            )
        else:
            # Fallback: minimum odds table (no Tippmix data yet)
            live_vbets = live_value_bets(lp, min_edge=5.0)

        results.append({
            **m,
            "pre_xg_home":       round(pre_xg_h, 2),
            "pre_xg_away":       round(pre_xg_a, 2),
            "live_probs":        lp,
            "live_bets":         live_vbets,
            "has_tippmix_odds":  has_tippmix_odds,
        })

    return jsonify({"matches": results, "tippmix_cache_age": cache_age})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3001, debug=False)
