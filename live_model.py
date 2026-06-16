"""
Live in-play probability model for WC 2026.
Includes find_live_value_bets_from_markets() to compare live model probs
against actual Tippmix live odds and compute edge + Kelly stake.

Adjusts pre-match Poisson predictions using:
  - Current score (most important)
  - Time elapsed / remaining
  - Live xG from SofaScore (how the match is actually being played)
  - Red cards
  - Possession (secondary signal)

The key insight: if Spain has 1.4 xG but 0 goals at 62 minutes,
they are unlucky — the model correctly keeps them as heavy favorites
because the underlying performance supports it.
"""

import re
import numpy as np
from scipy.stats import poisson

_MAX_GOALS = 8   # max additional goals to consider per team


def _pmf(lam: float) -> np.ndarray:
    """Poisson PMF for 0.._MAX_GOALS additional goals."""
    lam = max(lam, 1e-6)
    return np.array([poisson.pmf(k, lam) for k in range(_MAX_GOALS + 1)])


def live_probs(
    pre_xg_home: float,     # pre-match expected goals from PoissonModel
    pre_xg_away: float,
    minute: int,            # current match minute
    home_score: int,
    away_score: int,
    live_xg_home: float,    # xG accumulated so far (SofaScore)
    live_xg_away: float,
    red_cards_home: int = 0,
    red_cards_away: int = 0,
    possession_home: float = 50.0,
) -> dict:
    """
    Returns live probability dict with all markets.
    All probabilities are floats 0..1.
    """

    # ── 1. Estimate total match minutes (add stoppage) ────────────────────────
    stoppage = 5 if minute < 45 else 7
    total_min = 90 + stoppage
    elapsed_frac   = min(minute / 90.0, 1.0)
    remaining_frac = max(0.0, (total_min - minute) / 90.0)

    # ── 2. Blend pre-match rate with live xG rate ─────────────────────────────
    # Early in the match trust pre-match more; later trust live xG more.
    # At 15 min → 20% live; at 45 min → 50% live; at 70 min → 70% live
    if minute >= 10 and (live_xg_home + live_xg_away) > 0.05:
        live_rate_h = live_xg_home / elapsed_frac
        live_rate_a = live_xg_away / elapsed_frac
        live_w = min(0.70, elapsed_frac * 0.85)
        adj_h  = (1 - live_w) * pre_xg_home + live_w * live_rate_h
        adj_a  = (1 - live_w) * pre_xg_away + live_w * live_rate_a
    else:
        adj_h = pre_xg_home
        adj_a = pre_xg_away

    # ── 3. Possession nudge (secondary, small effect) ─────────────────────────
    # 70% possession → slight upward nudge; purely defensive team adjustment
    pos_factor_h = 0.9 + 0.2 * (possession_home / 100.0)
    pos_factor_a = 0.9 + 0.2 * ((100 - possession_home) / 100.0)
    adj_h = adj_h * 0.95 + adj_h * pos_factor_h * 0.05
    adj_a = adj_a * 0.95 + adj_a * pos_factor_a * 0.05

    # ── 4. Red card penalty: 25% fewer goals per red ──────────────────────────
    adj_h *= 0.75 ** red_cards_home
    adj_a *= 0.75 ** red_cards_away

    # ── 5. Expected remaining goals ───────────────────────────────────────────
    rem_h = max(0.0, adj_h * remaining_frac)
    rem_a = max(0.0, adj_a * remaining_frac)

    # ── 6. Poisson joint distribution for remaining goals ────────────────────
    pmf_h = _pmf(rem_h)
    pmf_a = _pmf(rem_a)
    joint = np.outer(pmf_h, pmf_a)   # (MAX+1) × (MAX+1)

    home_win = draw = away_win = btts = 0.0
    over = {0.5: 0.0, 1.5: 0.0, 2.5: 0.0, 3.5: 0.0, 4.5: 0.0}

    for i in range(_MAX_GOALS + 1):
        for j in range(_MAX_GOALS + 1):
            p       = joint[i, j]
            final_h = home_score + i
            final_a = away_score + j
            total   = final_h + final_a

            if   final_h > final_a: home_win += p
            elif final_h < final_a: away_win += p
            else:                   draw     += p

            if final_h > 0 and final_a > 0:
                btts += p

            for thr in over:
                if total > thr:
                    over[thr] += p

    hw_aw = home_win + away_win
    dnb_home = home_win / hw_aw if hw_aw > 0 else 0.5
    dnb_away = away_win / hw_aw if hw_aw > 0 else 0.5

    return {
        # 1X2
        "home_win":  round(home_win, 4),
        "draw":      round(draw,     4),
        "away_win":  round(away_win, 4),
        # DNB
        "dnb_home":  round(dnb_home, 4),
        "dnb_away":  round(dnb_away, 4),
        # Goals
        "btts":      round(btts,     4),
        "over_0_5":  round(over[0.5], 4),
        "over_1_5":  round(over[1.5], 4),
        "over_2_5":  round(over[2.5], 4),
        "over_3_5":  round(over[3.5], 4),
        "over_4_5":  round(over[4.5], 4),
        # Model internals (for display)
        "exp_remaining_home": round(rem_h, 2),
        "exp_remaining_away": round(rem_a, 2),
        "adj_rate_home":      round(adj_h, 2),
        "adj_rate_away":      round(adj_a, 2),
        "live_weight":        round(min(0.70, elapsed_frac * 0.85), 2),
    }


def live_value_bets(probs: dict, min_edge: float = 5.0) -> list[dict]:
    """
    Compare live model probabilities to fair odds.
    Returns list of markets where we'd recommend betting,
    with the minimum odds needed at the lottózó/Tippmix Pro.

    Since we can't scrape Tippmix live odds reliably,
    we return fair_odds (1/prob) — user checks if Tippmix offers more.
    """
    markets = [
        ("Hazai győzelem (1)",     probs["home_win"],  "1X2",   0.125),
        ("Döntetlen (X)",          probs["draw"],      "1X2",   0.125),
        ("Vendég győzelem (2)",    probs["away_win"],  "1X2",   0.125),
        ("DNB — Hazai",            probs["dnb_home"],  "DNB",   0.25),
        ("DNB — Vendég",           probs["dnb_away"],  "DNB",   0.25),
        ("Mindkét csapat szerez",  probs["btts"],      "Gólok", 0.25),
        ("Gól O 0.5",              probs["over_0_5"],  "Gólok", 0.25),
        ("Gól O 1.5",              probs["over_1_5"],  "Gólok", 0.25),
        ("Gól O 2.5",              probs["over_2_5"],  "Gólok", 0.25),
        ("Gól O 3.5",              probs["over_3_5"],  "Gólok", 0.25),
        ("Gól O 4.5",              probs["over_4_5"],  "Gólok", 0.25),
        ("Gól U 0.5", 1 - probs["over_0_5"], "Gólok", 0.25),
        ("Gól U 1.5", 1 - probs["over_1_5"], "Gólok", 0.25),
        ("Gól U 2.5", 1 - probs["over_2_5"], "Gólok", 0.25),
    ]

    results = []
    for name, prob, group, kelly_frac in markets:
        if prob <= 0:
            continue
        fair_odds = round(1.0 / prob, 2)
        min_odds  = round(fair_odds * (1 + min_edge / 100), 2)
        results.append({
            "market":     name,
            "group":      group,
            "prob":       round(prob * 100, 1),
            "fair_odds":  fair_odds,
            "min_odds":   min_odds,
            "kelly_frac": kelly_frac,
        })

    # Sort: highest probability first (most likely outcomes at top)
    results.sort(key=lambda x: -x["prob"])
    return results


# ---------------------------------------------------------------------------
# Live value bets using actual Tippmix market odds
# ---------------------------------------------------------------------------

_GOLSZAM_RE = re.compile(r'(\d+)[,.](\d+)')


def _outcome_live_prob(market_name: str, outcome_no: int, probs: dict) -> float | None:
    """Map a Tippmix live market outcome to our live model probability. Returns None if unsupported."""
    n = market_name.strip()
    nl = n.lower()

    # 1X2
    if n == "1X2":
        return {1: probs.get("home_win"), 2: probs.get("draw"), 3: probs.get("away_win")}.get(outcome_no)

    # DNB — "Döntetlennél a tét visszajár"
    if "döntetlennél" in nl and "visszajár" in nl:
        return {1: probs.get("dnb_home"), 2: probs.get("dnb_away")}.get(outcome_no)

    # Total goals O/U — "Gólszám X,5"
    if n.startswith("Gólszám"):
        m = _GOLSZAM_RE.search(n)
        if m:
            key = f"over_{m.group(1)}_{m.group(2)}"  # e.g. over_2_5
            over_prob = probs.get(key, 0.0)
            if outcome_no == 1:   # "Kevesebb, mint X,5" = under
                return 1.0 - over_prob
            if outcome_no == 2:   # "Több, mint X,5" = over
                return over_prob

    # BTTS — "Mindkét csapat szerez gólt"
    if "mindkét csapat" in nl:
        btts = probs.get("btts", 0.0)
        if outcome_no == 1:   # "Igen"
            return btts
        if outcome_no == 2:   # "Nem"
            return 1.0 - btts

    return None


def find_live_value_bets_from_markets(
    market_groups: list,
    live_probs_dict: dict,
    bankroll: float = 10000.0,
    min_edge: float = 5.0,
) -> list[dict]:
    """
    Given Tippmix live market data and live model probabilities,
    compute real edge% and Kelly stake for each outcome.

    Returns a list of dicts (all outcomes, not just value ones)
    sorted value-first then by edge descending.
    """
    results = []
    seen_markets: set[str] = set()

    for group in market_groups:
        for market in group.get("markets", []):
            market_name = market.get("name", "")
            if not market_name or market_name in seen_markets:
                continue

            # Only markets we can model
            ml = market_name.lower()
            is_supported = (
                market_name == "1X2"
                or market_name.startswith("Gólszám")
                or ("döntetlennél" in ml and "visszajár" in ml)
                or "mindkét csapat" in ml
            )
            if not is_supported:
                continue

            seen_markets.add(market_name)

            # Kelly fraction by market type
            if market_name.startswith("Gólszám") or "mindkét csapat" in ml:
                kelly_frac = 0.25   # goals markets → ¼ Kelly
            elif "döntetlennél" in ml:
                kelly_frac = 0.25   # DNB
            else:
                kelly_frac = 0.125  # 1X2

            for outcome in market.get("outcomes", []):
                outcome_no  = outcome.get("no")
                outcome_name = outcome.get("name", "")
                odds_val    = float(outcome.get("fixedOdds") or outcome.get("odds") or 0)
                if odds_val <= 1.0:
                    continue

                prob = _outcome_live_prob(market_name, outcome_no, live_probs_dict)
                if prob is None or prob <= 0:
                    continue

                implied  = 1.0 / odds_val
                edge_pct = (prob - implied) * 100
                kelly    = max(0.0, (prob * odds_val - 1.0) / (odds_val - 1.0))
                stake    = round(kelly * kelly_frac * bankroll)

                results.append({
                    "market":      market_name,
                    "outcome":     outcome_name,
                    "model_prob":  round(prob * 100, 1),
                    "tippmix_odds": odds_val,
                    "implied_prob": round(implied * 100, 1),
                    "fair_odds":   round(1.0 / prob, 2),
                    "edge_pct":    round(edge_pct, 1),
                    "kelly_pct":   round(kelly * 100, 2),
                    "kelly_frac":  kelly_frac,
                    "stake_ft":    stake,
                    "value":       bool(edge_pct >= min_edge),
                })

    results.sort(key=lambda x: (-int(x["value"]), -x["edge_pct"]))
    return results
