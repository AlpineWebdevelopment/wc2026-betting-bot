/**
 * Lightweight auth — hardcoded single username/password.
 *
 * Override the defaults with env vars in production:
 *   AUTH_USER, AUTH_PASS, AUTH_SECRET
 *
 * The cookie never stores the credentials; it stores a SHA-256 token
 * derived from user+pass+secret+week, so it can't be forged without the
 * secret — and it rotates automatically every week (see WEEK_MS below),
 * which forces everyone to log in again. No cron or storage needed.
 */

export const AUTH_COOKIE = "wc_auth";

const AUTH_USER = process.env.AUTH_USER ?? "admin";
const AUTH_PASS = process.env.AUTH_PASS ?? "wc2026";
const AUTH_SECRET = process.env.AUTH_SECRET ?? "wc2026-default-secret-change-me";

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

/** Whole weeks since the Unix epoch — the rotating part of the secret. */
function weekBucket(offset = 0): number {
  return Math.floor(Date.now() / WEEK_MS) - offset;
}

// Works in both the edge (middleware) and node runtimes via Web Crypto.
async function sha256(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const hash = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function tokenForWeek(week: number): Promise<string> {
  return sha256(`${AUTH_USER}:${AUTH_PASS}:${AUTH_SECRET}:${week}`);
}

/** The cookie value issued at login (current week). */
export function expectedToken(): Promise<string> {
  return tokenForWeek(weekBucket());
}

/**
 * True if a cookie token is still valid. Accepts the current week and the
 * previous week so a session started just before a week boundary isn't
 * killed instantly — effective lifetime is ~1–2 weeks, then re-login.
 */
export async function isTokenValid(token: string | undefined): Promise<boolean> {
  if (!token) return false;
  const [current, previous] = await Promise.all([
    tokenForWeek(weekBucket(0)),
    tokenForWeek(weekBucket(1)),
  ]);
  return token === current || token === previous;
}

/** True if the submitted login credentials are correct. */
export function checkCredentials(user: string, pass: string): boolean {
  return user === AUTH_USER && pass === AUTH_PASS;
}
