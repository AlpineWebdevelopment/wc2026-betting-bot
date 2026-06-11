"""
Compares model probabilities against bookmaker odds to find value bets.
A value bet exists when your model probability > bookmaker's implied probability.
"""

from config import MIN_EDGE_PCT
from markets import compute_market_probs, parse_exact_score_outcome


def find_value_bets(probs: dict, odds: dict, home: str, away: str) -> list[dict]:
    """
    probs: output of PoissonModel.predict()
    odds:  output of odds.best_odds()
    Returns list of value bet dicts.
    """
    candidates = [
        ("home_win",  "Home Win",  odds.get("home_odds"), probs["home_win"]),
        ("draw",      "Draw",      odds.get("draw_odds"), probs["draw"]),
        ("away_win",  "Away Win",  odds.get("away_odds"), probs["away_win"]),
    ]

    results = []
    for key, label, decimal_odds, model_prob in candidates:
        if not decimal_odds or decimal_odds <= 1.0:
            continue

        implied_prob = 1.0 / decimal_odds
        edge_pct = (model_prob - implied_prob) * 100

        # Kelly criterion: fraction of bankroll to stake
        kelly = (model_prob * decimal_odds - 1.0) / (decimal_odds - 1.0)
        kelly = max(0.0, kelly)

        value = edge_pct >= MIN_EDGE_PCT

        results.append({
            "market": label,
            "model_prob": round(model_prob * 100, 1),
            "implied_prob": round(implied_prob * 100, 1),
            "best_odds": decimal_odds,
            "fair_odds": round(1.0 / model_prob, 2) if model_prob > 0 else None,
            "edge_pct": round(edge_pct, 1),
            "kelly_pct": round(kelly * 100, 1),
            "value": value,
        })

    return results


def _make_vbet(market_name: str, outcome_name: str, decimal_odds: float,
               model_prob: float, group_name: str = "") -> dict:
    model_prob   = float(model_prob)
    decimal_odds = float(decimal_odds)
    implied_prob = 1.0 / decimal_odds
    edge_pct     = (model_prob - implied_prob) * 100
    kelly        = max(0.0, (model_prob * decimal_odds - 1.0) / (decimal_odds - 1.0))
    return {
        "market":       str(market_name),
        "market_group": str(group_name),
        "outcome":      str(outcome_name),
        "model_prob":   float(round(model_prob * 100, 1)),
        "implied_prob": float(round(implied_prob * 100, 1)),
        "best_odds":    decimal_odds,
        "fair_odds":    float(round(1.0 / model_prob, 2)) if model_prob > 0 else None,
        "edge_pct":     float(round(edge_pct, 1)),
        "kelly_pct":    float(round(kelly * 100, 1)),
        "value":        bool(edge_pct >= MIN_EDGE_PCT),
    }


# Groups to skip entirely (player/card markets — not predictable from any model)
_SKIP_GROUPS = {
    "Játékosok", "Büntetőlapok",
}

# Market name substrings indicating non-predictable player/card/shot markets
_SKIP_MARKET_SUBSTRINGS = [
    "büntetőlap", "sárga lap", "piros lap",
    "kaput eltaláló", "kapura tartó", "szabálytalanság",
    "lesz 11-es", "lesz kiállítás", "lesz öngól", "lesz mesterhármas",
    "kezdőként",  # player-specific
]


def find_all_value_bets(
    market_groups: list,
    probs: dict,
    home_hu: str,
    away_hu: str,
) -> list[dict]:
    """
    Full market value bet analysis for WC matches with complete market data.
    Returns list of value bet dicts for ALL predictable outcomes (not just value ones).
    """
    score_matrix = probs.get("score_matrix", [])
    exp_h = probs["exp_home_goals"]
    exp_a = probs["exp_away_goals"]

    results = []
    seen_markets = set()  # deduplicate: same market can appear in multiple groups

    for group in market_groups:
        group_name = group.get("name", "")
        if group_name in _SKIP_GROUPS:
            continue

        for market in group.get("markets", []):
            market_name = market.get("name", "")
            if not market_name:
                continue

            # Skip player/stats markets by substring
            ml = market_name.lower()
            if any(s in ml for s in _SKIP_MARKET_SUBSTRINGS):
                continue

            # Deduplicate by market name — many markets repeated across groups
            if market_name in seen_markets:
                continue
            seen_markets.add(market_name)

            outcomes = market.get("outcomes", [])

            # Special handling: exact score markets
            if market_name in ("Pontos végeredmény", "1. félidő - Pontos eredmény",
                                "2. félidő - Pontos eredmény"):
                for idx, outcome in enumerate(outcomes):
                    odds_val = outcome.get("fixedOdds") or outcome.get("odds")
                    if not odds_val or odds_val <= 1.0:
                        continue
                    score = parse_exact_score_outcome(
                        outcome.get("name", ""), home_hu, away_hu
                    )
                    if score is None:
                        continue
                    h_g, a_g = score
                    if h_g < len(score_matrix) and a_g < len(score_matrix[0]):
                        model_prob = float(score_matrix[h_g][a_g])
                        if model_prob > 0:
                            results.append(_make_vbet(
                                market_name, outcome.get("name", ""),
                                float(odds_val), model_prob, group_name
                            ))
                continue

            # All other markets: use compute_market_probs
            outcome_probs = compute_market_probs(
                market_name, score_matrix, exp_h, exp_a,
                home_hu=home_hu, away_hu=away_hu
            )
            if not outcome_probs:
                continue

            for idx, outcome in enumerate(outcomes):
                if idx not in outcome_probs:
                    continue
                odds_val = outcome.get("fixedOdds") or outcome.get("odds")
                if not odds_val or odds_val <= 1.0:
                    continue
                model_prob = outcome_probs[idx]
                if model_prob <= 0:
                    continue
                results.append(_make_vbet(
                    market_name, outcome.get("name", ""),
                    float(odds_val), model_prob, group_name
                ))

    # Sort: value bets first, then by edge descending
    results.sort(key=lambda v: (-int(v["value"]), -v["edge_pct"]))
    return results


def print_match_analysis(home: str, away: str, probs: dict,
                          value_bets: list[dict], has_live_odds: bool):
    print(f"\n{'=' * 60}")
    print(f"  {home}  vs  {away}")
    print(f"  xG: {home} {probs['exp_home_goals']} vs {probs['exp_away_goals']} {away}")
    print(f"  Model:  Home {probs['home_win']*100:.1f}%  |  "
          f"Draw {probs['draw']*100:.1f}%  |  "
          f"Away {probs['away_win']*100:.1f}%")

    if not has_live_odds:
        print("  (No bookmaker odds - add THE_ODDS_API_KEY in config.py)")
        return

    print(f"\n  {'Market':<12} {'Model%':>7} {'Impl%':>7} {'B.Odds':>8} "
          f"{'FairOdds':>9} {'Edge%':>7} {'Kelly%':>8}  Verdict")
    print(f"  {'-'*80}")
    for b in value_bets:
        verdict = "[VALUE]" if b["value"] else "-"
        print(f"  {b['market']:<12} {b['model_prob']:>6.1f}% {b['implied_prob']:>6.1f}% "
              f"{b['best_odds']:>8.2f} {b['fair_odds']:>9.2f} "
              f"{b['edge_pct']:>+6.1f}% {b['kelly_pct']:>7.1f}%  {verdict}")
