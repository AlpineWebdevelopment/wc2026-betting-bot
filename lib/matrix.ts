/**
 * Small matrix helpers replacing the numpy operations used by the model
 * and market math (outer products, triangular sums, axis sums).
 */

/** np.outer(a, b) → m[i][j] = a[i] * b[j]. */
export function outer(a: number[], b: number[]): number[][] {
  return a.map((ai) => b.map((bj) => ai * bj));
}

/** Sum of strictly-lower triangle (i > j) — home win mass. */
export function sumStrictLower(m: number[][]): number {
  let s = 0;
  for (let i = 0; i < m.length; i++)
    for (let j = 0; j < m[i].length; j++) if (i > j) s += m[i][j];
  return s;
}

/** Sum of the diagonal (i === j) — draw mass. */
export function sumDiag(m: number[][]): number {
  let s = 0;
  const n = Math.min(m.length, m[0]?.length ?? 0);
  for (let i = 0; i < n; i++) s += m[i][i];
  return s;
}

/** Sum of strictly-upper triangle (i < j) — away win mass. */
export function sumStrictUpper(m: number[][]): number {
  let s = 0;
  for (let i = 0; i < m.length; i++)
    for (let j = 0; j < m[i].length; j++) if (i < j) s += m[i][j];
  return s;
}

/** m.sum(axis=1) — P(home scores k). */
export function rowSums(m: number[][]): number[] {
  return m.map((row) => row.reduce((a, b) => a + b, 0));
}

/** m.sum(axis=0) — P(away scores k). */
export function colSums(m: number[][]): number[] {
  const n = m[0]?.length ?? 0;
  const out = new Array(n).fill(0);
  for (let i = 0; i < m.length; i++)
    for (let j = 0; j < n; j++) out[j] += m[i][j];
  return out;
}

/** np.convolve(a, b) — full discrete convolution (length a.length + b.length - 1). */
export function convolve(a: number[], b: number[]): number[] {
  const out = new Array(a.length + b.length - 1).fill(0);
  for (let i = 0; i < a.length; i++)
    for (let j = 0; j < b.length; j++) out[i + j] += a[i] * b[j];
  return out;
}

/** Sum of arr[from..end]. */
export function tailSum(arr: number[], from: number): number {
  let s = 0;
  for (let i = from; i < arr.length; i++) s += arr[i];
  return s;
}
