/** Round to `n` decimal places (mirrors Python's round() for display purposes). */
export function round(x: number, n = 0): number {
  const m = Math.pow(10, n);
  return Math.round((x + Number.EPSILON) * m) / m;
}
