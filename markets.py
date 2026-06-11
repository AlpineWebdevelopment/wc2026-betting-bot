"""
Probability calculations for all predictable Tippmix markets.
Derived from the Poisson score matrix (home goals x away goals joint PMF).
"""
import re
import numpy as np
from scipy.stats import poisson

HT_FRAC = 0.42   # fraction of total xG that occurs in the 1st half

MAX_G = 10       # goals cap (matches config.MAX_GOALS)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _half_matrix(exp_h: float, exp_a: float, frac: float) -> np.ndarray:
    g = np.arange(0, MAX_G + 1)
    return np.outer(poisson.pmf(g, frac * exp_h), poisson.pmf(g, frac * exp_a))


def _ou(m: np.ndarray, line: float) -> tuple[float, float]:
    """(under, over) for total goals O/U `line`."""
    n = m.shape[0]
    over = float(sum(m[i, j] for i in range(n) for j in range(n) if i + j > line))
    return 1.0 - over, over


def _team_ou(marginal: np.ndarray, line: float) -> tuple[float, float]:
    over = float(sum(marginal[k] for k in range(len(marginal)) if k > line))
    return 1.0 - over, over


def _asian_total(m: np.ndarray, line: float) -> tuple[float, float]:
    """Effective (under, over) for Asian total lines (handles quarter-ball)."""
    n = m.shape[0]
    frac = round(line % 1.0, 2)

    def exact_total(t):
        return float(sum(m[i, j] for i in range(n) for j in range(n) if i + j == int(t)))

    if frac == 0.5:
        return _ou(m, line)
    if frac == 0.0:
        exact = exact_total(line)
        _, over_full = _ou(m, line)
        eff_over = over_full + 0.5 * exact
        return 1.0 - eff_over, eff_over
    if abs(frac - 0.25) < 0.01:
        base = int(line)
        exact = exact_total(base)
        _, over_xp5 = _ou(m, base + 0.5)
        eff_over = over_xp5 + 0.5 * exact
        return 1.0 - eff_over, eff_over
    if abs(frac - 0.75) < 0.01:
        base = int(line)
        _, over_x5 = _ou(m, base + 0.5)
        exact_xp1 = exact_total(base + 1)
        _, over_xp1 = _ou(m, base + 1.0)
        eff_over_xp1 = over_xp1 + 0.5 * exact_xp1
        eff_over = 0.5 * over_x5 + 0.5 * eff_over_xp1
        return 1.0 - eff_over, eff_over
    return _ou(m, line)


def _asian_handicap(m: np.ndarray, line: float) -> tuple[float, float]:
    """
    Effective (home, away) probs for Asian handicap.
    line is from HOME perspective (e.g. -1.75 = home gives 1.75 goals to away).
    """
    n = m.shape[0]
    frac = round(abs(line) % 1.0, 2)

    home_p = 0.0
    away_p = 0.0
    for i in range(n):
        for j in range(n):
            p = float(m[i, j])
            net = (i - j) + line   # > 0 means home wins AH

            if abs(frac) < 0.01:
                # Whole-number line: push at net=0
                if abs(net) < 0.01:
                    home_p += 0.5 * p
                    away_p += 0.5 * p
                elif net > 0:
                    home_p += p
                else:
                    away_p += p
            elif abs(frac - 0.5) < 0.01:
                # Half-line: no push
                if net > 0:
                    home_p += p
                else:
                    away_p += p
            else:
                # Quarter ball: split between two adjacent lines
                sign = -1.0 if line < 0 else 1.0
                l1 = line - 0.25 * sign
                l2 = line + 0.25 * sign
                for lx in [l1, l2]:
                    net2 = (i - j) + lx
                    lx_frac = round(abs(lx) % 1.0, 2)
                    if abs(lx_frac) < 0.01 and abs(net2) < 0.01:
                        home_p += 0.25 * p
                        away_p += 0.25 * p
                    elif net2 > 0:
                        home_p += 0.5 * p
                    elif net2 < 0:
                        away_p += 0.5 * p
    return home_p, away_p


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

def compute_market_probs(
    market_name: str,
    score_matrix: list,
    exp_h: float,
    exp_a: float,
    home_hu: str = "",
    away_hu: str = "",
) -> dict[int, float]:
    """
    Returns {outcome_index: probability} for predictable markets.
    outcome_index is 0-based position in Tippmix's outcomes array.
    Returns {} for non-predictable markets.
    """
    m = np.array(score_matrix, dtype=float)
    n = m.shape[0]

    home_g = m.sum(axis=1)   # P(home scores k)
    away_g = m.sum(axis=0)   # P(away scores k)

    hw = float(np.sum(np.tril(m, -1)))
    dr = float(np.sum(np.diag(m)))
    aw = float(np.sum(np.triu(m, 1)))

    ht = _half_matrix(exp_h, exp_a, HT_FRAC)
    sh = _half_matrix(exp_h, exp_a, 1.0 - HT_FRAC)

    ht_hw = float(np.sum(np.tril(ht, -1)))
    ht_dr = float(np.sum(np.diag(ht)))
    ht_aw = float(np.sum(np.triu(ht, 1)))
    sh_hw = float(np.sum(np.tril(sh, -1)))
    sh_dr = float(np.sum(np.diag(sh)))
    sh_aw = float(np.sum(np.triu(sh, 1)))

    ht_hg = ht.sum(axis=1)
    ht_ag = ht.sum(axis=0)
    sh_hg = sh.sum(axis=1)
    sh_ag = sh.sum(axis=0)

    name = market_name

    # ── 1X2 ─────────────────────────────────────────────────────────────────
    if name == "1X2":
        return {0: hw, 1: dr, 2: aw}

    # ── Double Chance ────────────────────────────────────────────────────────
    # outcomes: [1X (home or draw), 12 (home or away), X2 (draw or away)]
    if name == "Kétesély":
        return {0: hw + dr, 1: hw + aw, 2: dr + aw}

    # ── Draw No Bet ──────────────────────────────────────────────────────────
    # outcomes: [home, away]
    if name == "Döntetlennél a tét visszajár":
        d = hw + aw
        return {0: hw / d if d > 0 else 0.5, 1: aw / d if d > 0 else 0.5}

    # ── BTTS ─────────────────────────────────────────────────────────────────
    # outcomes: [Igen/yes, Nem/no]
    if name in ("Mindkét csapat szerez gólt",
                "1. félidő - Mindkét csapat szerez gólt?",
                "2. félidő - Mindkét csapat szerez gólt?"):
        if "1. félid" in name:
            btts = float(np.sum(ht[1:, 1:]))
        elif "2. félid" in name:
            btts = float(np.sum(sh[1:, 1:]))
        else:
            btts = float(np.sum(m[1:, 1:]))
        return {0: btts, 1: 1.0 - btts}

    # ── Over/Under total goals ────────────────────────────────────────────────
    # Gólszám X,5   →  outcomes: [under, over]
    for line in [0.5, 1.5, 2.5, 3.5, 4.5]:
        hu_line = f"{line:.1f}".replace(".", ",")
        if name == f"Gólszám {hu_line}":
            u, o = _ou(m, line)
            return {0: u, 1: o}
        if name == f"1. félidő - Gólszám {hu_line}":
            u, o = _ou(ht, line)
            return {0: u, 1: o}
        if name == f"2. félidő - Gólszám {hu_line}":
            u, o = _ou(sh, line)
            return {0: u, 1: o}

    # ── Goal ranges ───────────────────────────────────────────────────────────
    # Gólszám (0-1, 2-3, 4-5, 6+)
    if name == "Gólszám":
        r01 = float(sum(m[i, j] for i in range(n) for j in range(n) if i + j <= 1))
        r23 = float(sum(m[i, j] for i in range(n) for j in range(n) if 2 <= i + j <= 3))
        r45 = float(sum(m[i, j] for i in range(n) for j in range(n) if 4 <= i + j <= 5))
        r6p = float(sum(m[i, j] for i in range(n) for j in range(n) if i + j >= 6))
        return {0: r01, 1: r23, 2: r45, 3: r6p}

    # 1. félidő - Gólszám  (0, 1, 2+)
    if name == "1. félidő - Gólszám":
        g0 = float(sum(ht[i, j] for i in range(n) for j in range(n) if i + j == 0))
        g1 = float(sum(ht[i, j] for i in range(n) for j in range(n) if i + j == 1))
        g2p = 1.0 - g0 - g1
        return {0: g0, 1: g1, 2: max(0.0, g2p)}

    if name == "2. félidő - Gólszám":
        g0 = float(sum(sh[i, j] for i in range(n) for j in range(n) if i + j == 0))
        g1 = float(sum(sh[i, j] for i in range(n) for j in range(n) if i + j == 1))
        g2p = 1.0 - g0 - g1
        return {0: g0, 1: g1, 2: max(0.0, g2p)}

    # ── Exact goal count ─────────────────────────────────────────────────────
    if name == "Gólszám (pontosan)":
        probs = {}
        for k in range(5):
            probs[k] = float(sum(m[i, j] for i in range(n) for j in range(n) if i + j == k))
        return probs

    # ── 1X2 + BTTS combo ─────────────────────────────────────────────────────
    # outcomes: [home+yes, home+no, draw+yes, draw+no, away+yes, away+no]
    if name == "1X2 + Mindkét csapat szerez gólt":
        h_y = float(sum(m[i, j] for i in range(1, n) for j in range(1, n) if i > j))
        h_n = float(sum(m[i, j] for i in range(n) for j in range(n) if i > j and (i == 0 or j == 0)))
        d_y = float(sum(m[i, j] for i in range(1, n) for j in range(1, n) if i == j))
        d_n = float(m[0, 0])
        a_y = float(sum(m[i, j] for i in range(1, n) for j in range(1, n) if j > i))
        a_n = float(sum(m[i, j] for i in range(n) for j in range(n) if j > i and (i == 0 or j == 0)))
        return {0: h_y, 1: h_n, 2: d_y, 3: d_n, 4: a_y, 5: a_n}

    # ── 1X2 + Over/Under combo ───────────────────────────────────────────────
    # outcomes: [home+under, draw+under, away+under, home+over, draw+over, away+over]
    for line in [1.5, 2.5, 3.5, 4.5]:
        hu_line = f"{line:.1f}".replace(".", ",")
        if name == f"1X2 + Gólszám {hu_line}":
            h_u = float(sum(m[i, j] for i in range(n) for j in range(n) if i > j and i + j <= line))
            d_u = float(sum(m[i, j] for i in range(n) for j in range(n) if i == j and i + j <= line))
            a_u = float(sum(m[i, j] for i in range(n) for j in range(n) if j > i and i + j <= line))
            h_o = float(sum(m[i, j] for i in range(n) for j in range(n) if i > j and i + j > line))
            d_o = float(sum(m[i, j] for i in range(n) for j in range(n) if i == j and i + j > line))
            a_o = float(sum(m[i, j] for i in range(n) for j in range(n) if j > i and i + j > line))
            return {0: h_u, 1: d_u, 2: a_u, 3: h_o, 4: d_o, 5: a_o}
        if name == f"1. félidő - 1X2 + Gólszám {hu_line}":
            h_u = float(sum(ht[i, j] for i in range(n) for j in range(n) if i > j and i + j <= line))
            d_u = float(sum(ht[i, j] for i in range(n) for j in range(n) if i == j and i + j <= line))
            a_u = float(sum(ht[i, j] for i in range(n) for j in range(n) if j > i and i + j <= line))
            h_o = float(sum(ht[i, j] for i in range(n) for j in range(n) if i > j and i + j > line))
            d_o = float(sum(ht[i, j] for i in range(n) for j in range(n) if i == j and i + j > line))
            a_o = float(sum(ht[i, j] for i in range(n) for j in range(n) if j > i and i + j > line))
            return {0: h_u, 1: d_u, 2: a_u, 3: h_o, 4: d_o, 5: a_o}

    # ── Home team goals O/U ───────────────────────────────────────────────────
    for line in [0.5, 1.5, 2.5]:
        hu_line = f"{line:.1f}".replace(".", ",")
        if name == f"Hazai csapat - Gólszám {hu_line}":
            u, o = _team_ou(home_g, line)
            return {0: u, 1: o}
        if name == f"1. félidő - Hazai csapat - Gólszám {hu_line}":
            u, o = _team_ou(ht_hg, line)
            return {0: u, 1: o}
        if name == f"2. félidő - Hazai csapat - Gólszám {hu_line}":
            u, o = _team_ou(sh_hg, line)
            return {0: u, 1: o}

    # ── Away team goals O/U ───────────────────────────────────────────────────
    for line in [0.5, 1.5]:
        hu_line = f"{line:.1f}".replace(".", ",")
        if name == f"Vendégcsapat - Gólszám {hu_line}":
            u, o = _team_ou(away_g, line)
            return {0: u, 1: o}
        if name == f"1. félidő - Vendégcsapat - Gólszám {hu_line}":
            u, o = _team_ou(ht_ag, line)
            return {0: u, 1: o}
        if name == f"2. félidő - Vendégcsapat - Gólszám {hu_line}":
            u, o = _team_ou(sh_ag, line)
            return {0: u, 1: o}

    # ── BTTS + Over 2.5 ─────────────────────────────────────────────────────
    # outcomes: [yes+over, yes+under, no+over, no+under]
    if name == "Mindkét csapat szerez gólt + Gólszám 2,5":
        y_o = float(sum(m[i, j] for i in range(1, n) for j in range(1, n) if i + j > 2.5))
        y_u = float(sum(m[i, j] for i in range(1, n) for j in range(1, n) if i + j <= 2.5))
        n_o = float(sum(m[i, j] for i in range(n) for j in range(n) if (i == 0 or j == 0) and i + j > 2.5))
        n_u = float(sum(m[i, j] for i in range(n) for j in range(n) if (i == 0 or j == 0) and i + j <= 2.5))
        return {0: y_o, 1: y_u, 2: n_o, 3: n_u}

    # ── European Handicap ────────────────────────────────────────────────────
    # outcomes: [home hcap win, draw, away hcap win]
    for h_start, a_start in [(0, 2), (0, 1), (1, 0)]:
        if name == f"Hendikep {h_start}:{a_start}":
            h_w = float(sum(m[i, j] for i in range(n) for j in range(n) if (i + h_start) > (j + a_start)))
            h_d = float(sum(m[i, j] for i in range(n) for j in range(n) if (i + h_start) == (j + a_start)))
            h_a = float(sum(m[i, j] for i in range(n) for j in range(n) if (i + h_start) < (j + a_start)))
            return {0: h_w, 1: h_d, 2: h_a}
        if name == f"1. félidő - Hendikep {h_start}:{a_start}":
            h_w = float(sum(ht[i, j] for i in range(n) for j in range(n) if (i + h_start) > (j + a_start)))
            h_d = float(sum(ht[i, j] for i in range(n) for j in range(n) if (i + h_start) == (j + a_start)))
            h_a = float(sum(ht[i, j] for i in range(n) for j in range(n) if (i + h_start) < (j + a_start)))
            return {0: h_w, 1: h_d, 2: h_a}
        if name == f"2. félidő - Hendikep {h_start}:{a_start}":
            h_w = float(sum(sh[i, j] for i in range(n) for j in range(n) if (i + h_start) > (j + a_start)))
            h_d = float(sum(sh[i, j] for i in range(n) for j in range(n) if (i + h_start) == (j + a_start)))
            h_a = float(sum(sh[i, j] for i in range(n) for j in range(n) if (i + h_start) < (j + a_start)))
            return {0: h_w, 1: h_d, 2: h_a}

    # ── Win margin ───────────────────────────────────────────────────────────
    # outcomes: [home 3+, home 2, home 1, away 1, away 2, away 3+]
    if name == "Nyertes különbség":
        h3p = float(sum(m[i, j] for i in range(n) for j in range(n) if i - j >= 3))
        h2  = float(sum(m[i, j] for i in range(n) for j in range(n) if i - j == 2))
        h1  = float(sum(m[i, j] for i in range(n) for j in range(n) if i - j == 1))
        a1  = float(sum(m[i, j] for i in range(n) for j in range(n) if j - i == 1))
        a2  = float(sum(m[i, j] for i in range(n) for j in range(n) if j - i == 2))
        a3p = float(sum(m[i, j] for i in range(n) for j in range(n) if j - i >= 3))
        return {0: h3p, 1: h2, 2: h1, 3: a1, 4: a2, 5: a3p}

    # ── Clean sheet / wins to nil ─────────────────────────────────────────────
    if name == "Hazai csapat kapott gól nélkül játssza le a mérkőzést":
        p = float(away_g[0])
        return {0: p, 1: 1.0 - p}

    if name == "Vendégcsapat kapott gól nélkül játssza le a mérkőzést":
        p = float(home_g[0])
        return {0: p, 1: 1.0 - p}

    if name == "Hazai csapat kapott gól nélkül játssza le az 1. félidőt":
        p = float(ht_ag[0])
        return {0: p, 1: 1.0 - p}

    if name == "Vendégcsapat kapott gól nélkül játssza le az 1. félidőt":
        p = float(ht_hg[0])
        return {0: p, 1: 1.0 - p}

    if name == "Hazai csapat kapott gól nélkül játssza le a 2. félidőt":
        p = float(sh_ag[0])
        return {0: p, 1: 1.0 - p}

    if name == "Vendégcsapat kapott gól nélkül játssza le a 2. félidőt":
        p = float(sh_hg[0])
        return {0: p, 1: 1.0 - p}

    if name == "Hazai csapat 0-ra nyeri a mérkőzést":
        p = float(sum(m[i, 0] for i in range(1, n)))
        return {0: p, 1: 1.0 - p}

    if name == "Vendégcsapat 0-ra nyeri a mérkőzést":
        p = float(sum(m[0, j] for j in range(1, n)))
        return {0: p, 1: 1.0 - p}

    # ── Exact goals per team ─────────────────────────────────────────────────
    # outcomes: [0, 1, 2, 3+]
    if name == "Hazai csapat góljainak a száma":
        p0 = float(home_g[0])
        p1 = float(home_g[1]) if n > 1 else 0.0
        p2 = float(home_g[2]) if n > 2 else 0.0
        p3p = max(0.0, 1.0 - p0 - p1 - p2)
        return {0: p0, 1: p1, 2: p2, 3: p3p}

    if name == "Vendégcsapat góljainak a száma":
        p0 = float(away_g[0])
        p1 = float(away_g[1]) if n > 1 else 0.0
        p2 = float(away_g[2]) if n > 2 else 0.0
        p3p = max(0.0, 1.0 - p0 - p1 - p2)
        return {0: p0, 1: p1, 2: p2, 3: p3p}

    # ── Goal odd/even ────────────────────────────────────────────────────────
    # outcomes: [odd, even]
    if name == "Gólszám: páros vagy páratlan":
        odd = float(sum(m[i, j] for i in range(n) for j in range(n) if (i + j) % 2 == 1))
        return {0: odd, 1: 1.0 - odd}

    # ── Which team scores ────────────────────────────────────────────────────
    # outcomes: [only home, only away, both, neither]
    if name == "Melyik csapat szerez gólt?":
        only_h = float(sum(m[i, 0] for i in range(1, n)))
        only_a = float(sum(m[0, j] for j in range(1, n)))
        both   = float(np.sum(m[1:, 1:]))
        none   = float(m[0, 0])
        return {0: only_h, 1: only_a, 2: both, 3: none}

    # ── First goal scorer (team) ─────────────────────────────────────────────
    # outcomes: [home, no goal, away]
    if name == "Melyik csapat szerzi a(z) 1. gólt?":
        no_goal = float(m[0, 0])
        total_g = exp_h + exp_a
        if total_g > 0:
            p_home = (1.0 - no_goal) * exp_h / total_g
            p_away = (1.0 - no_goal) * exp_a / total_g
        else:
            p_home = p_away = 0.0
        return {0: p_home, 1: no_goal, 2: p_away}

    # ── Which half more goals ────────────────────────────────────────────────
    # outcomes: [more in 1H, equal, more in 2H]
    if name == "Melyik félidőben lesz több gól?":
        # P(more in 1H), P(equal halves), P(more in 2H)
        # HT and 2H are independent Poisson, joint distribution over (ht_total, sh_total)
        probs_more1h = 0.0
        probs_equal  = 0.0
        probs_more2h = 0.0
        for g1 in range(n):
            ph1 = float(sum(ht[i, j] for i in range(n) for j in range(n) if i + j == g1))
            for g2 in range(n):
                ph2 = float(sum(sh[i, j] for i in range(n) for j in range(n) if i + j == g2))
                p = ph1 * ph2
                if g1 > g2:
                    probs_more1h += p
                elif g1 == g2:
                    probs_equal  += p
                else:
                    probs_more2h += p
        return {0: probs_more1h, 1: probs_equal, 2: probs_more2h}

    # ── Home/away scores in both halves ──────────────────────────────────────
    if name == "Hazai csapat szerez gólt mindkét félidőben?":
        p_ht = 1.0 - float(ht_hg[0])   # P(home scores 1+ in HT)
        p_sh = 1.0 - float(sh_hg[0])   # P(home scores 1+ in 2H)
        p = p_ht * p_sh                 # independent
        return {0: p, 1: 1.0 - p}

    if name == "Vendégcsapat szerez gólt mindkét félidőben?":
        p_ht = 1.0 - float(ht_ag[0])
        p_sh = 1.0 - float(sh_ag[0])
        p = p_ht * p_sh
        return {0: p, 1: 1.0 - p}

    # ── Both halves with/without goals ───────────────────────────────────────
    if name == "Mindkét félidőben kevesebb, mint 1,5 gól lesz?":
        _, ht_u = _ou(ht, 1.5)
        ht_u_val = 1.0 - ht_u   # wait, _ou returns (under, over)
        ht_u15, _ = _ou(ht, 1.5)  # P(HT total <= 1)
        sh_u15, _ = _ou(sh, 1.5)  # P(SH total <= 1)
        p = ht_u15 * sh_u15
        return {0: p, 1: 1.0 - p}

    if name == "Mindkét félidőben több, mint 1,5 gól lesz?":
        _, ht_o15 = _ou(ht, 1.5)
        _, sh_o15 = _ou(sh, 1.5)
        p = ht_o15 * sh_o15
        return {0: p, 1: 1.0 - p}

    # ── Mindk t f lid ben lesz g l? (both halves with at least 1 goal) ──────
    if name == "Mindkét félidőben lesz gól?" or name == "Mindkét félidőben lesz gól?":
        p_ht = 1.0 - float(sum(ht[i, j] for i in range(n) for j in range(n) if i + j == 0))
        p_sh = 1.0 - float(sum(sh[i, j] for i in range(n) for j in range(n) if i + j == 0))
        p = p_ht * p_sh
        return {0: p, 1: 1.0 - p}

    # ── HT/FT result combo ───────────────────────────────────────────────────
    # outcomes: [home/home, home/draw, home/away, draw/home, draw/draw, draw/away, away/home, away/draw, away/away]
    if name == "Félidő/végeredmény":
        results = {}
        idx = 0
        # We need P(HT=r1, FT=r2)
        # Since HT and 2H are independent, FT = HT + 2H
        for ht_r in ["home", "draw", "away"]:
            for ft_r in ["home", "draw", "away"]:
                p = 0.0
                for ht_h in range(n):
                    for ht_a in range(n):
                        ht_prob = float(ht[ht_h, ht_a])
                        if ht_prob < 1e-9:
                            continue
                        # Determine HT result
                        if ht_h > ht_a:
                            this_ht = "home"
                        elif ht_h == ht_a:
                            this_ht = "draw"
                        else:
                            this_ht = "away"
                        if this_ht != ht_r:
                            continue
                        # For FT result, sum over 2H outcomes
                        for sh_h in range(n):
                            for sh_a in range(n):
                                sh_prob = float(sh[sh_h, sh_a])
                                if sh_prob < 1e-9:
                                    continue
                                ft_h = ht_h + sh_h
                                ft_a = ht_a + sh_a
                                if ft_h > ft_a:
                                    this_ft = "home"
                                elif ft_h == ft_a:
                                    this_ft = "draw"
                                else:
                                    this_ft = "away"
                                if this_ft == ft_r:
                                    p += ht_prob * sh_prob
                results[idx] = p
                idx += 1
        return results

    # ── 1st half 1X2 variants ────────────────────────────────────────────────
    if name == "1. félidő - 1X2":
        return {0: ht_hw, 1: ht_dr, 2: ht_aw}

    if name == "1. félidő - Kétesély":
        return {0: ht_hw + ht_dr, 1: ht_hw + ht_aw, 2: ht_dr + ht_aw}

    if name == "1. félidő - Döntetlennél a tét visszajár":
        d = ht_hw + ht_aw
        return {0: ht_hw / d if d > 0 else 0.5, 1: ht_aw / d if d > 0 else 0.5}

    # ── 2nd half 1X2 variants ────────────────────────────────────────────────
    if name == "2. félidő - 1X2":
        return {0: sh_hw, 1: sh_dr, 2: sh_aw}

    if name == "2. félidő - Kétesély":
        return {0: sh_hw + sh_dr, 1: sh_hw + sh_aw, 2: sh_dr + sh_aw}

    if name in ("2. félidő - Döntetlennél tét visszajár", "2. félidő - Döntetlennél tét visszajár"):
        d = sh_hw + sh_aw
        return {0: sh_hw / d if d > 0 else 0.5, 1: sh_aw / d if d > 0 else 0.5}

    # ── Asian Total (Ázsiai Gólszám) ─────────────────────────────────────────
    # Parse: "Ázsiai Gólszám 2,25" → line=2.25
    match = re.match(r"Ázsiai Gólszám (\d+)(?:,(\d+))?$", name)
    if match:
        whole = int(match.group(1))
        frac_str = match.group(2) or "0"
        # Convert: "5" → 0.5, "25" → 0.25, "75" → 0.75, "0" → 0.0
        if len(frac_str) == 1:
            frac_val = int(frac_str) / 10.0
        elif len(frac_str) == 2:
            frac_val = int(frac_str) / 100.0
        else:
            frac_val = 0.0
        line_val = whole + frac_val
        u, o = _asian_total(m, line_val)
        return {0: u, 1: o}

    # ── Asian Handicap (Ázsiai Hendikep) ─────────────────────────────────────
    # Parse: "Ázsiai Hendikep -1,75" → line=-1.75
    match = re.match(r"Ázsiai Hendikep ([+-]?\d+)(?:,(\d+))?$", name)
    if match:
        whole = int(match.group(1))
        frac_str = match.group(2) or "0"
        if len(frac_str) == 1:
            frac_val = int(frac_str) / 10.0
        elif len(frac_str) == 2:
            frac_val = int(frac_str) / 100.0
        else:
            frac_val = 0.0
        sign = -1 if whole < 0 else 1
        line_val = whole - sign * frac_val  # e.g. -1 - (-1)*0.75 = -1.75
        if whole < 0:
            line_val = whole - frac_val  # -1.75
        else:
            line_val = whole + frac_val
        home_p, away_p = _asian_handicap(m, line_val)
        return {0: home_p, 1: away_p}

    # ── Home/away which half more goals ─────────────────────────────────────
    # outcomes: [more in 1H, equal, more in 2H]
    for team, tg_ht, tg_sh in [
        ("Hazai csapat melyik félidőben szerez több gólt?", ht_hg, sh_hg),
        ("Vendégcsapat melyik félidőben szerez több gólt?", ht_ag, sh_ag),
    ]:
        if name == team:
            p1h = p_eq = p2h = 0.0
            for g1 in range(n):
                p1 = float(tg_ht[g1]) if g1 < len(tg_ht) else 0.0
                for g2 in range(n):
                    p2 = float(tg_sh[g2]) if g2 < len(tg_sh) else 0.0
                    p = p1 * p2
                    if g1 > g2:
                        p1h += p
                    elif g1 == g2:
                        p_eq += p
                    else:
                        p2h += p
            return {0: p1h, 1: p_eq, 2: p2h}

    # ── Home/away wins both halves / at least one half ────────────────────────
    if name == "Hazai csapat nyeri mindkét félidőt?":
        return {0: ht_hw * sh_hw, 1: 1.0 - ht_hw * sh_hw}

    if name == "Hazai csapat nyer legalább egy félidőt?":
        p_none = (1.0 - ht_hw) * (1.0 - sh_hw)
        return {0: 1.0 - p_none, 1: p_none}

    if name == "Vendégcsapat nyer legalább egy félidőt?":
        p_none = (1.0 - ht_aw) * (1.0 - sh_aw)
        return {0: 1.0 - p_none, 1: p_none}

    # ── 1st/2nd half BTTS combo ──────────────────────────────────────────────
    # outcomes: [Nem/Nem, Igen/Nem, Igen/Igen, Nem/Igen]
    if name == "1.félidő/2.félidő - Mindkét csapat szerez gólt":
        ht_btts = float(np.sum(ht[1:, 1:]))
        sh_btts = float(np.sum(sh[1:, 1:]))
        nn = (1.0 - ht_btts) * (1.0 - sh_btts)
        yn = ht_btts * (1.0 - sh_btts)
        yy = ht_btts * sh_btts
        ny = (1.0 - ht_btts) * sh_btts
        return {0: nn, 1: yn, 2: yy, 3: ny}

    # ── Combination OR markets ─────────────────────────────────────────────
    # Home win OR BTTS
    if name == "Hazai csapat nyer vagy mindkét csapat szerez gólt":
        btts = float(np.sum(m[1:, 1:]))
        hw_btts = float(sum(m[i, j] for i in range(1, n) for j in range(1, n) if i > j))
        p = hw + btts - hw_btts
        return {0: p, 1: 1.0 - p}

    if name == "Döntetlen vagy mindkét csapat szerez gólt":
        btts = float(np.sum(m[1:, 1:]))
        dr_btts = float(sum(m[i, j] for i in range(1, n) for j in range(1, n) if i == j))
        p = dr + btts - dr_btts
        return {0: p, 1: 1.0 - p}

    if name == "Vendégcsapat nyer vagy mindkét csapat szerez gólt":
        btts = float(np.sum(m[1:, 1:]))
        aw_btts = float(sum(m[i, j] for i in range(1, n) for j in range(1, n) if j > i))
        p = aw + btts - aw_btts
        return {0: p, 1: 1.0 - p}

    # Home win or under/over 2.5
    for result, r_prob in [("Hazai csapat nyer", hw), ("Döntetlen", dr), ("Vendégcsapat nyer", aw)]:
        for direction, dir_fn in [("kevesebb", lambda t: t <= 2.5), ("több", lambda t: t > 2.5)]:
            cname = f"{result} vagy {direction} gól lesz, mint 2,5?"
            if name == cname:
                # P(result OR direction) = P(result) + P(direction) - P(result AND direction)
                if result == "Hazai csapat nyer":
                    r_key = lambda i, j: i > j
                elif result == "Döntetlen":
                    r_key = lambda i, j: i == j
                else:
                    r_key = lambda i, j: j > i
                p_dir = float(sum(m[i, j] for i in range(n) for j in range(n) if dir_fn(i + j)))
                p_and = float(sum(m[i, j] for i in range(n) for j in range(n) if r_key(i, j) and dir_fn(i + j)))
                return {0: r_prob + p_dir - p_and, 1: 1.0 - (r_prob + p_dir - p_and)}

    # ── Goal in first 30 minutes ─────────────────────────────────────────────
    if name == "Lesz gól az első 30 percben (0:00-29:59)?":
        # Approximate: 30/90 = 1/3 of match xG
        m30 = _half_matrix(exp_h, exp_a, 1.0 / 3.0)
        p_no_goal = float(sum(m30[i, j] for i in range(n) for j in range(n) if i + j == 0))
        return {0: 1.0 - p_no_goal, 1: p_no_goal}

    return {}  # not predictable


# ---------------------------------------------------------------------------
# Exact score parser (for Pontos végeredmény market)
# ---------------------------------------------------------------------------

def parse_exact_score_outcome(outcome_name: str, home_hu: str, away_hu: str) -> tuple[int, int] | None:
    """
    Parse exact score outcome name to (home_score, away_score).
    Format: "{TeamName} H:A" where H:A may be winner's goals : loser's goals.
    """
    rx = re.match(r"^(.+?)\s+(\d+):(\d+)$", outcome_name.strip())
    if not rx:
        return None
    team_name = rx.group(1).strip()
    score1, score2 = int(rx.group(2)), int(rx.group(3))

    if team_name in ("Döntetlen", "Egyenlő"):
        return (score1, score2)  # draw: home:away format

    # Normalise team name matching (strip accents won't work easily, use direct compare)
    if home_hu and team_name.lower() == home_hu.lower():
        return (score1, score2)  # home wins: score1 = home goals
    if away_hu and team_name.lower() == away_hu.lower():
        return (score2, score1)  # away wins: score1 = away goals, score2 = home goals

    # Fallback: check if score1 > score2 (assume team listed won)
    # Can't determine home/away reliably — skip
    return None
