"""
WC 2026 Value Bet Finder
Usage:
  python main.py                      — scan all WC 2026 fixtures with live odds
  python main.py "Brazil" "Germany"   — predict one specific match
  python main.py --refresh            — force re-download of historical data
"""

import sys
import argparse
from data import fetch_data
from model import PoissonModel
from odds import get_wc_odds, best_odds
from valuebets import find_value_bets, print_match_analysis
from fixtures import GROUP_STAGE, WC_TEAMS
from config import THE_ODDS_API_KEY, WC_HOSTS


def build_model(force_refresh: bool = False) -> PoissonModel:
    print("\n[1/3] Loading historical match data...")
    df = fetch_data(force_refresh=force_refresh)

    print("\n[2/3] Fitting Poisson model...")
    model = PoissonModel()
    model.fit(df)
    return model


def scan_live_odds(model: PoissonModel):
    print("\n[3/3] Fetching live WC 2026 odds...")
    matches = get_wc_odds()

    if not matches:
        if not THE_ODDS_API_KEY:
            print("\n  ⚠  No API key set. Add THE_ODDS_API_KEY in config.py")
            print("     Free signup: https://the-odds-api.com\n")
        return

    value_count = 0
    for m in matches:
        home, away = m["home_team"], m["away_team"]
        neutral = home not in WC_HOSTS
        probs = model.predict(home, away, neutral=neutral)
        b_odds = best_odds(m)
        vbets = find_value_bets(probs, b_odds, home, away)
        print_match_analysis(home, away, probs, vbets, has_live_odds=True)
        value_count += sum(1 for v in vbets if v["value"])

    print(f"\n{'=' * 60}")
    print(f"  SUMMARY: {value_count} value bet(s) found across {len(matches)} matches.")
    print(f"  Rule: stake Kelly% of your bankroll. Never chase losses.\n")


def predict_one(model: PoissonModel, home: str, away: str):
    neutral = home not in WC_HOSTS
    probs = model.predict(home, away, neutral=neutral)
    print_match_analysis(home, away, probs, [], has_live_odds=False)
    print(f"\n  Expected score: {home} {probs['exp_home_goals']} - "
          f"{probs['exp_away_goals']} {away}\n")


def scan_all_fixtures(model: PoissonModel):
    """Show model predictions for all known WC fixtures (no odds needed)."""
    print("\n[3/3] Generating predictions for all group stage fixtures...")
    for home, away, date in GROUP_STAGE:
        neutral = home not in WC_HOSTS
        probs = model.predict(home, away, neutral=neutral)
        print_match_analysis(home, away, probs, [], has_live_odds=False)


def main():
    parser = argparse.ArgumentParser(description="WC 2026 Value Bet Finder")
    parser.add_argument("teams", nargs="*", help="Two team names: 'Brazil' 'Germany'")
    parser.add_argument("--refresh", action="store_true", help="Re-download data")
    parser.add_argument("--fixtures", action="store_true", help="Predict all known fixtures")
    args = parser.parse_args()

    print("\nWC 2026 Betting Model -- Poisson + Value Bet Detector")
    print("=" * 60)

    model = build_model(force_refresh=args.refresh)

    if len(args.teams) == 2:
        predict_one(model, args.teams[0], args.teams[1])
    elif args.fixtures:
        scan_all_fixtures(model)
    elif THE_ODDS_API_KEY:
        scan_live_odds(model)
    else:
        # No args, no key — show a demo
        print("\n[3/3] Demo mode (no API key). Showing model predictions...")
        demo_matches = [
            ("Brazil", "Argentina"),
            ("Germany", "France"),
            ("Spain", "England"),
            ("United States", "Mexico"),
            ("Portugal", "Morocco"),
        ]
        for home, away in demo_matches:
            neutral = home not in WC_HOSTS
            probs = model.predict(home, away, neutral=neutral)
            print_match_analysis(home, away, probs, [], has_live_odds=False)

        print("\n  To get value bets with real bookmaker odds:")
        print("  1. Sign up free at https://the-odds-api.com")
        print("  2. Paste your key into config.py -> THE_ODDS_API_KEY")
        print("  3. Run: python main.py\n")


if __name__ == "__main__":
    main()
