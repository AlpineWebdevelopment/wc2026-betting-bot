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
from corner_model import CornerModel, PARAMS_PATH as _CORNER_PARAMS_PATH
from corner_valuebets import find_corner_value_bets
from card_model import CardModel, PARAMS_PATH as _CARD_PARAMS_PATH
from card_valuebets import find_card_value_bets
from tippmix import get_tippmix_matches, get_tippmix_live_odds
from sofascore import get_live_wc_matches
from live_model import live_probs, live_value_bets, find_live_value_bets_from_markets
from retrain import run_retrain

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
_corner_model = None
if _os.path.exists(_CORNER_PARAMS_PATH):
    _corner_model = CornerModel.load(_CORNER_PARAMS_PATH)
else:
    print("  Corner model not trained yet — run /retrain-corners first.")

_card_model = None
if _os.path.exists(_CARD_PARAMS_PATH):
    _card_model = CardModel.load(_CARD_PARAMS_PATH)
else:
    print("  Card model not trained yet — run /retrain-cards first.")

_live_odds: dict[str, dict] = {}   # "HomeTeam|AwayTeam" -> match dict

# ── Prediction log ────────────────────────────────────────────────────────────
import json as _json

_PRED_LOG_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "predictions_log.json")

def _load_pred_log():
    if _os.path.exists(_PRED_LOG_PATH):
        try:
            with open(_PRED_LOG_PATH, "r", encoding="utf-8") as f:
                return _json.load(f)
        except Exception:
            pass
    return []

def _save_pred_log(entries):
    """Upsert entries by (home_team, away_team, match_date), keep last 500."""
    log = _load_pred_log()
    idx = {(e["home_team"], e["away_team"], e.get("match_date", "")): i for i, e in enumerate(log)}
    for entry in entries:
        key = (entry["home_team"], entry["away_team"], entry.get("match_date", ""))
        if key in idx:
            log[idx[key]] = entry
        else:
            log.append(entry)
            idx[key] = len(log) - 1
    with open(_PRED_LOG_PATH, "w", encoding="utf-8") as f:
        _json.dump(log[-500:], f, indent=2, ensure_ascii=False)

def _eval_bet(bet, home_score, away_score, home_hu, away_hu, home_corners=None, away_corners=None, home_offsides=None, away_offsides=None):
    """Returns 'win','half_win','push','half_loss','loss','no_data','pending','unknown'."""
    import re as _re
    if not bet:
        return "unknown"
    mkt = bet.get("market", "")
    out = bet.get("outcome", "")
    mg  = bet.get("market_group", "")
    def pn(s): return float(s.strip().replace(",", "."))

    # Corner bets — evaluate if we have actual corner data
    if mg in ("Szögletek", "Statisztika"):
        if home_corners is None or away_corners is None:
            return "no_data"
        total_c = home_corners + away_corners
        # Total corners O/U  (e.g. "Szögletszám 7,5" / "Kevesebb, mint 7,5")
        if out.startswith("Több, mint "):
            try: return "win" if total_c > pn(out[11:]) else "loss"
            except: pass
        if out.startswith("Kevesebb, mint "):
            try: return "win" if total_c < pn(out[15:]) else "loss"
            except: pass
        # Team corners O/U  (e.g. "Vendégcsapat szögletszám 3,5")
        for kw, cscore in (("Hazai", home_corners), ("Vendég", away_corners)):
            if kw in mkt:
                if out.startswith("Több, mint "):
                    try: return "win" if cscore > pn(out[11:]) else "loss"
                    except: pass
                if out.startswith("Kevesebb, mint "):
                    try: return "win" if cscore < pn(out[15:]) else "loss"
                    except: pass
        return "unknown"

    # Offside count bets ("Lesszám X") — use ESPN summary offside data
    if "Lesszám" in mkt:
        if home_offsides is None or away_offsides is None:
            return "no_data"
        total_os = home_offsides + away_offsides
        if out.startswith("Több, mint "):
            try: return "win" if total_os > pn(out[11:]) else "loss"
            except: pass
        if out.startswith("Kevesebb, mint "):
            try: return "win" if total_os < pn(out[15:]) else "loss"
            except: pass
        # Team-specific offsides
        for kw, oscore in (("Hazai", home_offsides), ("Vendég", away_offsides)):
            if kw in mkt:
                if out.startswith("Több, mint "):
                    try: return "win" if oscore > pn(out[11:]) else "loss"
                    except: pass
                if out.startswith("Kevesebb, mint "):
                    try: return "win" if oscore < pn(out[15:]) else "loss"
                    except: pass
        return "unknown"

    total = home_score + away_score

    # Total goals O/U
    if out.startswith("Több, mint "):
        try:
            line = pn(out[11:])
            return "win" if total > line else ("push" if total == line else "loss")
        except: pass
    if out.startswith("Kevesebb, mint "):
        try:
            line = pn(out[15:])
            return "win" if total < line else ("push" if total == line else "loss")
        except: pass

    # Team-specific goals
    for kw, score in (("Hazai", home_score), ("Vendég", away_score)):
        if kw in mkt:
            if out.startswith("Több, mint "):
                try: return "win" if score > pn(out[11:]) else "loss"
                except: pass
            if out.startswith("Kevesebb, mint "):
                try: return "win" if score < pn(out[15:]) else "loss"
                except: pass

    # DNB
    if "Döntetlennél" in mkt:
        is_home = bool(home_hu and home_hu in out) or "Hazai" in out
        is_away = bool(away_hu and away_hu in out) or "Vendég" in out
        if is_home:
            return "win" if home_score > away_score else ("push" if home_score == away_score else "loss")
        if is_away:
            return "win" if away_score > home_score else ("push" if home_score == away_score else "loss")

    # 1X2
    if mkt == "1X2":
        if "Hazai győzelem" in out or (home_hu and out == home_hu):
            return "win" if home_score > away_score else "loss"
        if "Döntetlen" in out:
            return "win" if home_score == away_score else "loss"
        if "Vendég győzelem" in out or (away_hu and out == away_hu):
            return "win" if away_score > home_score else "loss"

    # Asian Handicap
    if "Hendikep" in mkt:
        m = _re.search(r"([+-]?\d+[,.]?\d*)\s*$", out)
        if m:
            try:
                hcap = pn(m.group(1))
                is_home = bool(home_hu and home_hu in out)
                margin = (home_score - away_score) if is_home else (away_score - home_score)
                fq = int(round(abs(hcap) * 4)) % 4  # 0=whole, 1=.25, 2=.5, 3=.75
                if fq == 0:
                    adj = margin + hcap
                    return "win" if adj > 0 else ("push" if adj == 0 else "loss")
                elif fq == 2:
                    return "win" if margin + hcap > 0 else "loss"
                elif fq == 3:  # -0.75: split into -0.5 and -1.0
                    p_half  = hcap + (0.25 if hcap < 0 else -0.25)   # -0.5 part
                    p_whole = hcap - (0.25 if hcap < 0 else -0.25)   # -1.0 part
                    r_half  = "win" if margin + p_half  > 0 else "loss"
                    r_whole = "win" if margin + p_whole > 0 else ("push" if margin + p_whole == 0 else "loss")
                    if r_half == "win"  and r_whole == "win":   return "win"
                    if r_half == "loss" and r_whole == "loss":  return "loss"
                    if r_half == "win"  and r_whole == "push":  return "half_win"
                    if r_half == "loss" and r_whole == "push":  return "half_loss"
                    return "half_win"
                else:  # .25: split into 0 (DNB) and -0.5
                    p_dnb  = hcap + (0.25 if hcap < 0 else -0.25)
                    p_half = hcap - (0.25 if hcap < 0 else -0.25)
                    r_dnb  = "win" if margin + p_dnb  > 0 else ("push" if margin + p_dnb  == 0 else "loss")
                    r_half = "win" if margin + p_half > 0 else "loss"
                    if r_dnb == "win"  and r_half == "win":  return "win"
                    if r_dnb == "loss" and r_half == "loss": return "loss"
                    if r_dnb == "push" and r_half == "win":  return "half_win"
                    if r_dnb == "push" and r_half == "loss": return "half_loss"
                    if r_dnb == "win"  and r_half == "loss": return "half_win"
                    return "half_win"
            except: pass

    # Asian total goals (Ázsiai Gólszám X)
    if "Gólszám" in mkt:
        m2 = _re.search(r"(\d+[,.]?\d*)\s*$", mkt)
        if m2:
            try:
                line = pn(m2.group(1))
                if "Kevesebb" in out: return "win" if total < line else ("push" if total == line else "loss")
                if "Több" in out:    return "win" if total > line else ("push" if total == line else "loss")
            except: pass

    # BTTS
    if "Mindkét" in mkt:
        btts = home_score > 0 and away_score > 0
        if "Igen" in out: return "win" if btts else "loss"
        if "Nem" in out:  return "win" if not btts else "loss"

    # Complex "team wins or under X goals" market
    if "Vendégcsapat nyer" in mkt and "Igen" in out:
        return "win" if (away_score > home_score or total <= 2) else "loss"
    if "Hazai csapat nyer" in mkt and "Igen" in out:
        return "win" if (home_score > away_score or total <= 2) else "loss"

    return "unknown"

def _refresh_odds():
    global _live_odds
    _live_odds = {}
    if THE_ODDS_API_KEY:
        for m in get_wc_odds():
            key = f"{m['home_team']}|{m['away_team']}"
            _live_odds[key] = m

_refresh_odds()
print("Model ready.\n")

# ── Shared TTL cache for pre-match Tippmix data ───────────────────────────────
# Both /tippmix-matches (UI) and /top-bets (bot) read from this cache,
# so they always see the same Tippmix snapshot.
_tippmix_prematch_cache: list[dict] = []
_tippmix_prematch_lock  = threading.Lock()
_tippmix_prematch_ts    = 0.0
_TIPPMIX_PREMATCH_TTL   = 300   # 5 minutes


def _get_tippmix_prematch_cached() -> list[dict]:
    global _tippmix_prematch_cache, _tippmix_prematch_ts
    now = _time.time()
    with _tippmix_prematch_lock:
        if not _tippmix_prematch_ts or now - _tippmix_prematch_ts > _TIPPMIX_PREMATCH_TTL:
            data = get_tippmix_matches()
            _tippmix_prematch_cache = data
            _tippmix_prematch_ts    = now
        return list(_tippmix_prematch_cache)


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

_MAINTENANCE = _os.environ.get("MAINTENANCE", "").lower() in ("1", "true", "yes")

@app.route("/")
def index():
    if _MAINTENANCE:
        return """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Karbantartás</title>
<style>body{background:#060d1a;color:#a0b0ff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;flex-direction:column;gap:16px}
h1{font-size:2rem;color:#fff;margin:0}p{color:#555;margin:0}</style></head>
<body><h1>🔧 Karbantartás alatt</h1><p>Hamarosan visszatérünk.</p></body></html>""", 503
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
        matches = _get_tippmix_prematch_cached()
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
            "value_bets":     [v for v in vbets if not _is_corner_bet(v)],
            "has_value":      any(v["value"] for v in vbets if not _is_corner_bet(v)),
        })

    results.sort(key=lambda r: (-int(r["is_wc"]), -int(r["has_value"]),
                                 -max((v["edge_pct"] for v in r["value_bets"]), default=0)))
    return jsonify(results)


def _is_corner_bet(v):
    """True if this bet belongs to the corner model (must be excluded from goal model Tab 1)."""
    mg = v.get("market_group", "")
    mkt = v.get("market", "")
    return mg == "Szögletek" or "szöglet" in mkt.lower() or "szöglet" in mg.lower()

def _is_approx(v):
    return v.get("market_group") in ("Szögletek", "Statisztika") or _is_corner_bet(v)

def _mkt_prio(name):
    if "félidő" in name.lower(): return 0  # half-time sub-markets never win the headline pick
    if "Döntetlennél" in name: return 3
    if "Gólszám" in name or "Mindkét" in name: return 2
    if name == "1X2": return 1
    return 0

def _bet_score(v):
    return v["kelly_pct"] / (8 if _is_approx(v) else 4)


@app.route("/top-bets")
def top_bets():
    """Return the Absolute Top 10 right-column bets (same logic as UI), for the Telegram bot."""
    try:
        matches = _get_tippmix_prematch_cached()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    flat = []
    for m in matches:
        if not m.get("is_wc"):
            continue
        home, away = m["home_team"], m["away_team"]
        probs = _model.predict(home, away, neutral=(home not in WC_HOSTS))
        mgs = m.get("market_groups", [])
        if mgs:
            vbets = find_all_value_bets(mgs, probs, m["home_team_hu"], m["away_team_hu"])
        else:
            vbets = find_value_bets(
                probs,
                {"home_odds": m["home_odds"], "draw_odds": m["draw_odds"], "away_odds": m["away_odds"]},
                home, away,
            )

        all_bets = [v for v in vbets if v.get("value") and not _is_corner_bet(v)]
        if not all_bets:
            continue

        trusted = sorted(
            [v for v in all_bets if not _is_approx(v) and v["edge_pct"] >= 7],
            key=lambda v: (-_mkt_prio(v["market"]), -v["edge_pct"]),
        )
        fallback = sorted(
            [v for v in all_bets if not _is_approx(v)],
            key=lambda v: -v["edge_pct"],
        )
        primary = (trusted[0] if trusted else None) or (fallback[0] if fallback else None) or all_bets[0]
        secondary = next(
            (v for v in all_bets
             if v["market"] != primary["market"] or v.get("outcome") != primary.get("outcome")),
            None,
        )

        mkey = f"{home}|{away}"
        flat.append({"bet": primary,   "is_primary": True,  "mkey": mkey, "m": m})
        if secondary:
            flat.append({"bet": secondary, "is_primary": False, "mkey": mkey, "m": m})

    # Left column: one primary per match, sorted by kick-off time
    primaries = [e for e in flat if e["is_primary"]]
    primaries.sort(key=lambda x: x["m"].get("event_date") or "9999")
    top10 = primaries[:10]

    return jsonify([{
        "home_team_hu": e["m"]["home_team_hu"],
        "away_team_hu": e["m"]["away_team_hu"],
        "event_date":   e["m"].get("event_date", ""),
        "bet":          e["bet"],
    } for e in top10])


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


@app.route("/retrain")
def retrain():
    """Fetch WC 2026 results, re-train model, reload into memory."""
    global _model
    try:
        import json as _json
        from datetime import datetime as _dt
        result = run_retrain()
        # Stamp trained_at into model_params.json
        with open(_PARAMS_PATH) as f: mp = _json.load(f)
        mp["trained_at"] = _dt.now().strftime("%Y-%m-%d %H:%M")
        with open(_PARAMS_PATH, "w") as f: _json.dump(mp, f)
        _model = PoissonModel.load(_PARAMS_PATH)
        return jsonify({"status": "ok", **result})
    except Exception as e:
        import traceback
        return jsonify({"status": "error", "message": str(e), "trace": traceback.format_exc()}), 500


@app.route("/tippmix-corners")
def tippmix_corners():
    """Corner model value bets for all WC matches."""
    if _corner_model is None:
        return jsonify({"error": "Corner model not trained yet. Click 'Sarok modell tanítása'."}), 503
    try:
        matches = _get_tippmix_prematch_cached()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    results = []
    for m in matches:
        if not m.get("is_wc"):
            continue
        home, away = m["home_team"], m["away_team"]
        try:
            corner_probs = _corner_model.predict(home, away)
        except Exception:
            continue
        mgs = m.get("market_groups", [])
        if not mgs:
            continue
        vbets = find_corner_value_bets(mgs, corner_probs, m["home_team_hu"], m["away_team_hu"])
        results.append({
            "home_team":      home,
            "away_team":      away,
            "home_team_hu":   m["home_team_hu"],
            "away_team_hu":   m["away_team_hu"],
            "event_date":     m.get("event_date", ""),
            "exp_home_corners": corner_probs["exp_home_corners"],
            "exp_away_corners": corner_probs["exp_away_corners"],
            "exp_total_corners": corner_probs["exp_total_corners"],
            "value_bets":     vbets,
            "has_value":      any(v["value"] for v in vbets),
        })

    results.sort(key=lambda r: r.get("event_date") or "9999")
    return jsonify(results)


@app.route("/tippmix-cards")
def tippmix_cards():
    """Card model value bets for all WC matches."""
    if _card_model is None:
        return jsonify({"error": "Card model not trained yet. Click 'Kártya modell tanítása'."}), 503
    try:
        matches = _get_tippmix_prematch_cached()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Load WC cache once for referee lookups
    _wc_ref_map = {}
    try:
        import json as _cj
        _wc_cache_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "wc_results_cache.json")
        if _os.path.exists(_wc_cache_path):
            with open(_wc_cache_path) as _cf:
                _wc = _cj.load(_cf)
            for _day in _wc.values():
                if isinstance(_day, list):
                    for _mx in _day:
                        if _mx.get("referee"):
                            _wc_ref_map[(_mx["home_team"], _mx["away_team"])] = _mx["referee"]
    except Exception:
        pass

    results = []
    for m in matches:
        if not m.get("is_wc"):
            continue
        home, away = m["home_team"], m["away_team"]
        referee = _wc_ref_map.get((home, away))
        try:
            card_probs = _card_model.predict(home, away, referee=referee)
        except Exception:
            continue
        mgs = m.get("market_groups", [])
        if not mgs:
            continue
        vbets = find_card_value_bets(mgs, card_probs, m["home_team_hu"], m["away_team_hu"])
        results.append({
            "home_team":       home,
            "away_team":       away,
            "home_team_hu":    m["home_team_hu"],
            "away_team_hu":    m["away_team_hu"],
            "event_date":      m.get("event_date", ""),
            "exp_home_cards":  card_probs["exp_home_cards"],
            "exp_away_cards":  card_probs["exp_away_cards"],
            "exp_total_cards": card_probs["exp_total_cards"],
            "ref_factor":      card_probs["ref_factor"],
            "referee":         referee,
            "ref_known":       card_probs["ref_known"],
            "value_bets":      vbets,
            "has_value":       any(v["value"] for v in vbets),
        })

    results.sort(key=lambda r: r.get("event_date") or "9999")
    return jsonify(results)


@app.route("/retrain-corners")
def retrain_corners():
    """Fetch corner training data and retrain the corner model (incremental)."""
    global _corner_model
    try:
        import json as _json
        from datetime import datetime as _dt
        from corner_data import fetch_corner_training_data

        # Load last trained-through date from existing params
        last_date = None
        if _os.path.exists(_CORNER_PARAMS_PATH):
            try:
                with open(_CORNER_PARAMS_PATH) as f:
                    cp = _json.load(f)
                last_date = cp.get("trained_through_date")  # YYYY-MM-DD of newest match used
            except Exception:
                pass

        matches = fetch_corner_training_data()
        if not matches:
            return jsonify({"status": "error", "message": "No corner data found from ESPN."}), 500

        # Find the newest match date in this data
        newest_date = max(m["date"] for m in matches)

        # If no new matches since last training, skip expensive optimization
        if last_date and newest_date <= last_date:
            return jsonify({
                "status": "up_to_date",
                "message": "Nincs új meccs az utolsó tanítás óta.",
                "last_trained_through": last_date,
                "total_matches": len(matches),
                "teams": len(_corner_model.teams) if _corner_model else 0,
            })

        # Count truly new matches (WC 2026 matches since last training)
        new_matches = sum(1 for m in matches if m["date"] > last_date) if last_date else 0
        is_first_run = last_date is None

        cm = CornerModel().fit(matches)
        cm.save()
        # Stamp trained_at and trained_through_date
        with open(_CORNER_PARAMS_PATH) as f:
            cp = _json.load(f)
        cp["trained_at"] = _dt.now().strftime("%Y-%m-%d %H:%M")
        cp["trained_through_date"] = newest_date
        with open(_CORNER_PARAMS_PATH, "w") as f:
            _json.dump(cp, f)
        _corner_model = CornerModel.load(_CORNER_PARAMS_PATH)
        return jsonify({
            "status": "ok",
            "matches_used": len(matches),
            "new_matches": new_matches,
            "is_first_run": is_first_run,
            "teams": len(_corner_model.teams),
        })
    except Exception as e:
        import traceback
        return jsonify({"status": "error", "message": str(e), "trace": traceback.format_exc()}), 500


@app.route("/retrain-cards")
def retrain_cards():
    """Fetch yellow card training data and retrain the card model."""
    global _card_model
    try:
        import json as _json
        from datetime import datetime as _dt
        from card_data import fetch_card_training_data

        last_date = None
        if _os.path.exists(_CARD_PARAMS_PATH):
            try:
                with open(_CARD_PARAMS_PATH) as f:
                    cp = _json.load(f)
                last_date = cp.get("trained_through_date")
            except Exception:
                pass

        matches = fetch_card_training_data()
        if not matches:
            return jsonify({"status": "error", "message": "No card data found from ESPN."}), 500

        newest_date = max(m["date"] for m in matches)

        if last_date and newest_date <= last_date:
            return jsonify({
                "status": "up_to_date",
                "message": "Nincs új meccs az utolsó tanítás óta.",
                "last_trained_through": last_date,
                "total_matches": len(matches),
                "teams": len(_card_model.teams) if _card_model else 0,
            })

        new_matches = sum(1 for m in matches if m["date"] > last_date) if last_date else 0
        is_first_run = last_date is None

        from card_model import CardModel
        cm = CardModel().fit(matches)
        cm.save()
        with open(_CARD_PARAMS_PATH) as f:
            cp = _json.load(f)
        cp["trained_at"] = _dt.now().strftime("%Y-%m-%d %H:%M")
        cp["trained_through_date"] = newest_date
        with open(_CARD_PARAMS_PATH, "w") as f:
            _json.dump(cp, f)
        _card_model = CardModel.load(_CARD_PARAMS_PATH)
        return jsonify({
            "status":        "ok",
            "matches_used":  len(matches),
            "new_matches":   new_matches,
            "is_first_run":  is_first_run,
            "teams":         len(_card_model.teams),
            "refs":          len(_card_model.ref_rates),
            "global_avg":    round(_card_model.global_avg, 2),
        })
    except Exception as e:
        import traceback
        return jsonify({"status": "error", "message": str(e), "trace": traceback.format_exc()}), 500


@app.route("/best-combined")
def best_combined():
    """Combined goal + corner recommendations per WC match."""
    try:
        matches = _get_tippmix_prematch_cached()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    results = []
    for m in matches:
        if not m.get("is_wc"):
            continue
        home, away = m["home_team"], m["away_team"]
        neutral = home not in WC_HOSTS
        probs = _model.predict(home, away, neutral=neutral)
        mgs = m.get("market_groups", [])

        from valuebets import find_all_value_bets
        goal_vbets = find_all_value_bets(mgs, probs, m["home_team_hu"], m["away_team_hu"]) if mgs else []
        # Filter out all corner bets (Szögletek group + any corner market in Népszerű etc.)
        goal_vbets = [v for v in goal_vbets if not _is_corner_bet(v) and v.get("market_group") != "Statisztika"]

        corner_vbets = []
        exp_corners = None
        if _corner_model and mgs:
            try:
                cp = _corner_model.predict(home, away)
                corner_vbets = find_corner_value_bets(mgs, cp, m["home_team_hu"], m["away_team_hu"])
                exp_corners = {"home": cp["exp_home_corners"], "away": cp["exp_away_corners"], "total": cp["exp_total_corners"]}
            except Exception:
                exp_corners = None

        # Best goal bet (primary pick logic)
        def _mkt_prio(n):
            if "félidő" in n.lower(): return 0  # half-time sub-markets never win the headline pick
            if "Döntetlennél" in n: return 3
            if "Gólszám" in n or "Mindkét" in n: return 2
            if n == "1X2": return 1
            return 0

        goal_trusted = sorted(
            [v for v in goal_vbets if v["value"] and v["edge_pct"] >= 7],
            key=lambda v: (-_mkt_prio(v["market"]), -v["edge_pct"])
        )
        best_goal = goal_trusted[0] if goal_trusted else None

        secondary_goal = next(
            (v for v in sorted([v for v in goal_vbets if v["value"]], key=lambda v: -v["edge_pct"])
             if v["market"] != best_goal["market"] or v.get("outcome") != best_goal.get("outcome")),
            None
        ) if best_goal else None

        corner_value = [v for v in corner_vbets if v["value"]]
        best_corner = sorted(corner_value, key=lambda v: -v["edge_pct"])[0] if corner_value else None

        results.append({
            "home_team":      home,
            "away_team":      away,
            "home_team_hu":   m["home_team_hu"],
            "away_team_hu":   m["away_team_hu"],
            "event_date":     m.get("event_date", ""),
            "best_goal":      best_goal,
            "secondary_goal": secondary_goal,
            "best_corner":    best_corner,
            "exp_corners":    exp_corners,
            "has_any_value":  bool(best_goal or best_corner),
        })

    results.sort(key=lambda r: r.get("event_date") or "9999")
    return jsonify(results)


@app.route("/model-info")
def model_info():
    """Return last-trained timestamps for both models."""
    import json as _json
    info = {}
    for key, path in [("match_bot", _PARAMS_PATH), ("corner_bot", _CORNER_PARAMS_PATH)]:
        if _os.path.exists(path):
            try:
                with open(path) as f:
                    d = _json.load(f)
                info[key] = {"trained_at": d.get("trained_at"), "teams": len(d.get("teams", []))}
            except Exception:
                info[key] = {"trained_at": None, "teams": 0}
        else:
            info[key] = {"trained_at": None, "teams": 0}
    return jsonify(info)


@app.route("/restart-server")
def restart_server():
    """Restart the Flask process (spawns a new instance then exits)."""
    import threading, sys, subprocess
    def _do():
        _time.sleep(0.6)
        subprocess.Popen([sys.executable, _os.path.abspath(__file__)],
                         cwd=_os.path.dirname(_os.path.abspath(__file__)))
        _os._exit(0)
    threading.Thread(target=_do, daemon=True).start()
    return jsonify({"status": "restarting"})


@app.route("/bot-daily")
def bot_daily():
    """
    Returns today's WC matches with primary + secondary Match Bot pick
    and best Corner Bot pick. Used by the Telegram bot.
    Only includes matches in the next 48 hours with edge >= 10%.
    """
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    try:
        matches = _get_tippmix_prematch_cached()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    now = _dt.now(_tz.utc)
    cutoff = now + _td(hours=48)
    results = []

    for m in matches:
        if not m.get("is_wc"):
            continue

        # Date filter: next 48h
        event_date = m.get("event_date", "")
        if event_date:
            try:
                ed = _dt.fromisoformat(event_date)
                if ed.tzinfo is None:
                    ed = ed.replace(tzinfo=_tz.utc)
                if ed < now or ed > cutoff:
                    continue
            except Exception:
                pass

        home, away = m["home_team"], m["away_team"]
        neutral = home not in WC_HOSTS
        probs = _model.predict(home, away, neutral=neutral)
        mgs = m.get("market_groups", [])

        from valuebets import find_all_value_bets
        vbets = find_all_value_bets(mgs, probs, m["home_team_hu"], m["away_team_hu"]) if mgs else []
        # Strip corners from goal bets
        goal_bets = [v for v in vbets if not _is_corner_bet(v) and v.get("market_group") != "Statisztika"]

        # Primary pick (mirrors UI logic, min edge 7%)
        trusted = sorted(
            [v for v in goal_bets if v["value"] and v["edge_pct"] >= 7],
            key=lambda v: (-_mkt_prio(v["market"]), -v["edge_pct"])
        )
        fallback = sorted(
            [v for v in goal_bets if v["value"]],
            key=lambda v: -v["edge_pct"]
        )
        primary = (trusted[0] if trusted else None) or (fallback[0] if fallback else None)
        if not primary:
            continue  # skip matches with no goal value bets at all

        # Secondary: highest-edge value bet with different market/outcome (mirrors Match Bot tab)
        secondary = next(
            (v for v in sorted([v for v in goal_bets if v["value"]], key=lambda v: -v["edge_pct"])
             if v["market"] != primary["market"] or v.get("outcome") != primary.get("outcome")),
            None
        )

        # Best corner bet (edge >= 10%)
        best_corner = None
        if _corner_model and mgs:
            try:
                cp = _corner_model.predict(home, away)
                cvbets = find_corner_value_bets(mgs, cp, m["home_team_hu"], m["away_team_hu"])
                strong = [v for v in cvbets if v["value"] and v["edge_pct"] >= 10]
                if strong:
                    best_corner = max(strong, key=lambda v: v["edge_pct"])
            except Exception:
                pass

        # Best card bet (edge >= 10%)
        best_card = None
        if _card_model and mgs:
            try:
                # Try to find referee from wc_results_cache for this match (if completed today)
                referee = None
                try:
                    import json as _cj
                    _wc_cache_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "wc_results_cache.json")
                    if _os.path.exists(_wc_cache_path):
                        with open(_wc_cache_path) as _cf:
                            _wc = _cj.load(_cf)
                        for _day in _wc.values():
                            if isinstance(_day, list):
                                for _mx in _day:
                                    if (_mx.get("home_team") == home and _mx.get("away_team") == away
                                            and _mx.get("referee")):
                                        referee = _mx["referee"]
                                        break
                except Exception:
                    pass
                cardp = _card_model.predict(home, away, referee=referee)
                cardvbets = find_card_value_bets(mgs, cardp, m["home_team_hu"], m["away_team_hu"])
                strong_cards = [v for v in cardvbets if v["value"] and v["edge_pct"] >= 10]
                if strong_cards:
                    best_card = max(strong_cards, key=lambda v: v["edge_pct"])
            except Exception:
                pass

        results.append({
            "home_team":      home,
            "away_team":      away,
            "home_team_hu":   m["home_team_hu"],
            "away_team_hu":   m["away_team_hu"],
            "event_date":     event_date,
            "primary_goal":   primary,
            "secondary_goal": secondary,
            "best_corner":    best_corner,
            "best_card":      best_card,
        })

    results.sort(key=lambda r: r.get("event_date") or "9999")

    # Log predictions for history tab
    if results:
        from datetime import datetime as _dt2
        now_str = _dt2.now().isoformat(timespec="seconds")
        _save_pred_log([{
            "logged_at":      now_str,
            "match_date":     r.get("event_date", "")[:10],
            "home_team":      r["home_team"],
            "away_team":      r["away_team"],
            "home_team_hu":   r["home_team_hu"],
            "away_team_hu":   r["away_team_hu"],
            "primary_goal":   r.get("primary_goal"),
            "secondary_goal": r.get("secondary_goal"),
            "best_corner":    r.get("best_corner"),
        } for r in results])

    return jsonify(results)


@app.route("/refresh-results")
def refresh_results():
    """Fetch latest ESPN match results into cache without retraining the model."""
    try:
        from retrain import fetch_completed_wc_matches
        matches = fetch_completed_wc_matches()
        return jsonify({"status": "ok", "completed_matches": len(matches)})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/model-accuracy")
def model_accuracy():
    """Run model on all completed WC matches and compare to actual results."""
    from retrain import _load_cache
    cache = _load_cache()

    all_matches = sorted(
        [m for day in cache.values() for m in day],
        key=lambda m: m["date"]
    )

    results = []
    for m in all_matches:
        home, away = m["home_team"], m["away_team"]
        hs, as_ = m["home_score"], m["away_score"]
        neutral = home not in WC_HOSTS
        try:
            probs = _model.predict(home, away, neutral=neutral)
        except Exception:
            probs = None

        actual = "home" if hs > as_ else ("draw" if hs == as_ else "away")

        if probs:
            hw = round(probs["home_win"] * 100, 1)
            d  = round(probs["draw"]     * 100, 1)
            aw = round(probs["away_win"] * 100, 1)
            xh = round(float(probs["exp_home_goals"]), 2)
            xa = round(float(probs["exp_away_goals"]), 2)
            if probs["home_win"] >= probs["draw"] and probs["home_win"] >= probs["away_win"]:
                model_pick = "home"
            elif probs["draw"] >= probs["away_win"]:
                model_pick = "draw"
            else:
                model_pick = "away"
            correct = model_pick == actual
        else:
            hw = d = aw = xh = xa = None
            model_pick = None
            correct = None

        results.append({
            "date":        m["date"],
            "home_team":   m["home_team_raw"],
            "away_team":   m["away_team_raw"],
            "home_score":  hs,
            "away_score":  as_,
            "home_win_pct": hw,
            "draw_pct":     d,
            "away_win_pct": aw,
            "exp_home":     xh,
            "exp_away":     xa,
            "model_pick":   model_pick,
            "actual":       actual,
            "correct":      correct,
        })

    decided = [r for r in results if r["correct"] is not None]
    correct_count = sum(1 for r in decided if r["correct"])
    return jsonify({
        "matches":  results,
        "summary": {
            "total":   len(results),
            "correct": correct_count,
            "accuracy": round(correct_count / len(decided) * 100, 1) if decided else 0,
        }
    })


@app.route("/prediction-history")
def prediction_history():
    """Return logged predictions with actual results and outcome evaluation."""
    from retrain import _load_cache
    log = _load_pred_log()
    cache = _load_cache()

    from tippmix import HU_TO_EN as _HU_TO_EN
    def _n(s): return s.lower().replace("-", " ").replace("&", "and").strip()

    # Flatten results cache: (norm_home, norm_away) -> match dict
    _all_results = {}
    for day_matches in cache.values():
        for rm in day_matches:
            k = (_n(rm["home_team"]), _n(rm["away_team"]))
            _all_results[k] = rm
            k2 = (_n(rm.get("home_team_raw", "")), _n(rm.get("away_team_raw", "")))
            if k2[0]: _all_results[k2] = rm

    def _find_result(home, away):
        # Try direct lookup first
        result = _all_results.get((_n(home), _n(away)))
        if result:
            return result
        # If home/away might be Hungarian names (fallback for old log entries), try translating
        home_en = _HU_TO_EN.get(home, home)
        away_en = _HU_TO_EN.get(away, away)
        return _all_results.get((_n(home_en), _n(away_en)))

    out = []
    for entry in sorted(log, key=lambda e: (e.get("match_date", ""), e.get("logged_at", ""))):
        home    = entry.get("home_team", "")
        away    = entry.get("away_team", "")
        home_hu = entry.get("home_team_hu", home)
        away_hu = entry.get("away_team_hu", away)
        result  = _find_result(home, away)

        if result:
            hs, as_ = result["home_score"], result["away_score"]
            hc  = result.get("home_corners")
            ac  = result.get("away_corners")
            hos = result.get("home_offsides")
            aos = result.get("away_offsides")
            def ev(bet, _hc=hc, _ac=ac, _hos=hos, _aos=aos):
                return _eval_bet(bet, hs, as_, home_hu, away_hu, _hc, _ac, _hos, _aos)
        else:
            hs = as_ = hc = ac = hos = aos = None
            def ev(bet): return "pending"

        primary   = entry.get("primary_goal")
        secondary = entry.get("secondary_goal")
        corner    = entry.get("best_corner")

        out.append({
            "logged_at":        entry.get("logged_at", ""),
            "match_date":       entry.get("match_date", ""),
            "home_team_hu":     home_hu,
            "away_team_hu":     away_hu,
            "home_score":       hs,
            "away_score":       as_,
            "home_corners":     hc,
            "away_corners":     ac,
            "home_offsides":    hos,
            "away_offsides":    aos,
            "has_result":       result is not None,
            "primary_goal":     primary,
            "primary_result":   ev(primary),
            "secondary_goal":   secondary,
            "secondary_result": ev(secondary),
            "best_corner":      corner,
            "corner_result":    ev(corner) if corner else None,
        })

    return jsonify(out)


@app.route("/restart-telegram")
def restart_telegram():
    """Kill the running telegram_bot.py (via PID file) and start a fresh one."""
    import sys, subprocess, signal
    pid_file = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "telegram_bot.pid")
    bot_script = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "telegram_bot.py")

    # Kill existing process
    killed = False
    if _os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            subprocess.call(["taskkill", "/F", "/PID", str(pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            killed = True
        except Exception as e:
            print(f"  [restart-telegram] kill failed: {e}")

    # Start fresh
    try:
        _time.sleep(1)
        subprocess.Popen([sys.executable, bot_script],
                        cwd=_os.path.dirname(_os.path.abspath(__file__)))
        return jsonify({"status": "ok", "killed": killed})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3001, debug=False, threaded=True)
