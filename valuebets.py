"""
Compares model probabilities against bookmaker odds to find value bets.
A value bet exists when your model probability > bookmaker's implied probability.
"""

from config import MIN_EDGE_PCT


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
