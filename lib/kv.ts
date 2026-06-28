/**
 * Minimal Vercel KV / Upstash Redis REST client (no SDK dependency).
 *
 * Used by the push-relay: a Hungarian-hosted machine fetches Tippmix odds and
 * POSTs them to /api/ingest-tippmix, which stores them here. The read routes
 * then serve this pushed snapshot — sidestepping the tippmix.hu geo-block,
 * since Vercel's serverless instances are stateless and can't share in-memory
 * cache between the ingest request and the read requests.
 *
 * Configured automatically when a Vercel KV store is attached to the project
 * (KV_REST_API_URL / KV_REST_API_TOKEN). No-ops gracefully when unset, so
 * local dev keeps working via the direct fetch fallback in lib/store.ts.
 */
// Accept either the legacy Vercel KV names or the Upstash-for-Redis Marketplace
// names — depending on how the store was provisioned, Vercel injects one pair.
const KV_URL =
  process.env.KV_REST_API_URL ?? process.env.UPSTASH_REDIS_REST_URL;
const KV_TOKEN =
  process.env.KV_REST_API_TOKEN ?? process.env.UPSTASH_REDIS_REST_TOKEN;

export const kvEnabled = Boolean(KV_URL && KV_TOKEN);

/** Store a JSON-serialisable value. Returns false if KV is unconfigured or the write fails. */
export async function kvSetJson(key: string, value: unknown): Promise<boolean> {
  if (!kvEnabled) return false;
  try {
    const r = await fetch(`${KV_URL}/set/${encodeURIComponent(key)}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${KV_TOKEN}` },
      body: JSON.stringify(value),
      cache: "no-store",
    });
    return r.ok;
  } catch {
    return false;
  }
}

/** Read and parse a JSON value. Returns null if KV is unconfigured, empty, or the read fails. */
export async function kvGetJson<T>(key: string): Promise<T | null> {
  if (!kvEnabled) return null;
  try {
    const r = await fetch(`${KV_URL}/get/${encodeURIComponent(key)}`, {
      headers: { Authorization: `Bearer ${KV_TOKEN}` },
      cache: "no-store",
    });
    if (!r.ok) return null;
    const j = await r.json();
    if (j?.result == null) return null;
    return JSON.parse(j.result as string) as T;
  } catch {
    return null;
  }
}
