"""
Tiny numpy-only Poisson PMF — replaces scipy.stats.poisson at request time so the
Vercel serverless bundle stays small (no scipy needed to serve predictions).

poisson.pmf(k, lam) = exp(-lam) * lam**k / k!
computed in log-space via lgamma for numerical stability.
"""
import numpy as np
from math import lgamma

_lgamma = np.vectorize(lgamma)


def poisson_pmf(k, lam):
    """P(X=k) for X ~ Poisson(lam). Accepts scalar or array k; scalar lam."""
    k = np.asarray(k, dtype=float)
    lam = float(lam)
    if lam <= 0.0:
        out = np.zeros_like(k)
        out[k == 0] = 1.0
        return out
    return np.exp(k * np.log(lam) - lam - _lgamma(k + 1.0))
