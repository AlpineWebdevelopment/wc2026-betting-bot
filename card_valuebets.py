"""
Find value bets in Tippmix card (yellow card) markets using the CardModel.
"""
from config import MIN_EDGE_PCT


def find_card_value_bets(market_groups: list, card_probs: dict,
                          home_hu: str, away_hu: str) -> list[dict]:
    """
    market_groups: from Tippmix
    card_probs: output of CardModel.predict()
    Returns list of value bet dicts (same schema as valuebets.py output).
    """
    ou_probs = card_probs.get("ou_probs", {})
    results  = []

    for mg in market_groups:
        for market in mg.get("markets", []):
            mkt_name = market.get("name", "")

            # Only card total markets (skip player card markets)
            if "büntetőlap-szám" not in mkt_name.lower():
                continue

            is_halftime = "félidő" in mkt_name.lower()
            outcomes = market.get("outcomes", [])

            for outcome in outcomes:
                out_name = outcome.get("name", "")
                odds_val = outcome.get("fixedOdds") or outcome.get("odds")
                if not odds_val or float(odds_val) <= 1.0:
                    continue
                odds_val = float(odds_val)

                model_prob = _get_model_prob(mkt_name, out_name, ou_probs, is_halftime)
                if model_prob is None or model_prob <= 0:
                    continue

                implied = 1.0 / odds_val
                edge    = (model_prob - implied) * 100
                kelly   = max(0.0, (model_prob * odds_val - 1.0) / (odds_val - 1.0))
                fair    = round(1.0 / model_prob, 2)

                results.append({
                    "market":       mkt_name,
                    "market_group": "Kártyák",
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
    import re
    m = re.search(r"(\d+)[,.](\d+)", text)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    m = re.search(r"(\d+)", text)
    if m:
        return float(m.group(1)) + 0.5
    return None


def _get_model_prob(mkt_name, out_name, ou_probs, is_halftime):
    """Map a Tippmix card market outcome to a model probability."""
    line = _parse_line(out_name) or _parse_line(mkt_name)
    if line is None:
        return None

    out_lower = out_name.lower()
    is_over  = any(w in out_lower for w in ("több", "over", "felett"))
    is_under = any(w in out_lower for w in ("kevesebb", "under", "alatt"))

    # Half-time: roughly half the total cards happen in HT (~45%)
    if is_halftime:
        ht_line = line * 2.0  # scale to full-match equivalent
        if ht_line in ou_probs:
            if is_over:  return ou_probs[ht_line]["over"]
            if is_under: return ou_probs[ht_line]["under"]
        return None

    if line in ou_probs:
        if is_over:  return ou_probs[line]["over"]
        if is_under: return ou_probs[line]["under"]

    return None
