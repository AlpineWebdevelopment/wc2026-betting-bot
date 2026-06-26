/**
 * Tiny Poisson PMF — direct TypeScript port of stats.py.
 *
 * poisson.pmf(k, lam) = exp(-lam) * lam**k / k!
 * computed in log-space via lgamma for numerical stability.
 */

// Lanczos approximation for the log-gamma function (g=7, n=9).
// Accurate to ~1e-13 for x > 0, which is all we ever pass (k + 1 >= 1).
const LANCZOS_G = 7;
const LANCZOS_C = [
  0.99999999999980993, 676.5203681218851, -1259.1392167224028,
  771.32342877765313, -176.61502916214059, 12.507343278686905,
  -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7,
];

export function lgamma(x: number): number {
  if (x < 0.5) {
    // Reflection formula: Gamma(x)Gamma(1-x) = pi / sin(pi x)
    return (
      Math.log(Math.PI / Math.sin(Math.PI * x)) - lgamma(1 - x)
    );
  }
  x -= 1;
  let a = LANCZOS_C[0];
  const t = x + LANCZOS_G + 0.5;
  for (let i = 1; i < LANCZOS_G + 2; i++) {
    a += LANCZOS_C[i] / (x + i);
  }
  return (
    0.5 * Math.log(2 * Math.PI) +
    (x + 0.5) * Math.log(t) -
    t +
    Math.log(a)
  );
}

/**
 * P(X=k) for X ~ Poisson(lam), for each k in `ks` (scalar lam).
 * Mirrors stats.poisson_pmf in the Python codebase.
 */
export function poissonPmf(ks: number[], lam: number): number[] {
  if (lam <= 0) {
    return ks.map((k) => (k === 0 ? 1.0 : 0.0));
  }
  const logLam = Math.log(lam);
  return ks.map((k) => Math.exp(k * logLam - lam - lgamma(k + 1.0)));
}

/** Single-value Poisson PMF. */
export function poissonPmfScalar(k: number, lam: number): number {
  return poissonPmf([k], lam)[0];
}

/** Integer range [0, n] inclusive — replaces np.arange(0, n + 1). */
export function arange(n: number): number[] {
  return Array.from({ length: n + 1 }, (_, i) => i);
}
