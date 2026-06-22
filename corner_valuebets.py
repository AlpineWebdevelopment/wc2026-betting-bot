"""
Find value bets in Tippmix corner markets using the CornerModel.
"""
from config import MIN_EDGE_PCT


def find_corner_value_bets(market_groups: list, corner_probs: dict,
                            home_hu: str, away_hu: str) -> list[dict]:
    """
    market_groups: from Tippmix (same format as find_all_value_bets receives)
    corner_probs: output of CornerModel.predict()
    Returns list of value bet dicts (same schema as valuebets.py output).
    """
    ou_probs  = corner_probs.get("ou_probs", {})
    team_ou   = corner_probs.get("team_ou", {})
    results   = []

    for mg in market_groups:
        group_name = mg.get("name", "")
        if group_name not in ("Szögletek",):
            continue

        for market in mg.get("markets", []):
            mkt_name = market.get("name", "")
            outcomes = market.get("outcomes", [])

            # Parse the line from market name or outcome name
            for outcome in outcomes:
                out_name = outcome.get("name", "")
                odds_val = outcome.get("fixedOdds") or outcome.get("odds")
                if not odds_val or float(odds_val) <= 1.0:
                    continue
                odds_val = float(odds_val)

                model_prob = _get_model_prob(mkt_name, out_name, ou_probs, team_ou, home_hu, away_hu)
                if model_prob is None or model_prob <= 0:
                    continue

                implied = 1.0 / odds_val
                edge    = (model_prob - implied) * 100
                kelly   = max(0.0, (model_prob * odds_val - 1.0) / (odds_val - 1.0))
                fair    = round(1.0 / model_prob, 2)

                results.append({
                    "market":       mkt_name,
                    "market_group": "Szögletek",
                    "outcome":      out_name,
                    "model_prob":   round(model_prob * 100, 1),
                    "implied_prob": round(implied * 100, 1),
                    "best_odds":    odds_val,
                    "fair_odds":    fair,
                    "edge_pct":     round(edge, 1),
                    "kelly_pct":    round(kelly * 100, 1),
                    "value":        bool(edge >= MIN_EDGE_PCT),
                })

    results.sort(key=lambda v: (-int(v["value"]), -v["edge_pct"]))
    return results


def _parse_line(text: str) -> float | None:
    """Extract numeric line from text like 'Több, mint 9,5' → 9.5"""
    import re
    m = re.search(r"(\d+)[,.](\d+)", text)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    m = re.search(r"(\d+)", text)
    if m:
        return float(m.group(1)) + 0.5
    return None


def _get_model_prob(mkt_name, out_name, ou_probs, team_ou, home_hu, away_hu):
    """Map a Tippmix corner market outcome to a model probability."""
    line = _parse_line(out_name) or _parse_line(mkt_name)
    if line is None:
        return None

    out_lower = out_name.lower()
    mkt_lower = mkt_name.lower()

    is_over  = any(w in out_lower for w in ("több", "over", "felett"))
    is_under = any(w in out_lower for w in ("kevesebb", "under", "alatt"))

    # Team-specific markets
    is_home = home_hu.lower() in mkt_lower or "hazai" in mkt_lower
    is_away = away_hu.lower() in mkt_lower or "vendég" in mkt_lower

    if is_home and line in team_ou:
        return team_ou[line]["home_over"] if is_over else (1 - team_ou[line]["home_over"] if is_under else None)
    if is_away and line in team_ou:
        return team_ou[line]["away_over"] if is_over else (1 - team_ou[line]["away_over"] if is_under else None)

    # Total corners
    if line in ou_probs:
        if is_over:  return ou_probs[line]["over"]
        if is_under: return ou_probs[line]["under"]

    return None
