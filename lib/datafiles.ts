/**
 * Access to runtime data files that the local Python pipeline writes
 * (wc_results_cache.json, predictions_log.json).
 *
 * Two sources, in priority order:
 *   1. KV — pushed by scripts/push-results.ts via /api/ingest-results. This is
 *      the only source that works on Vercel, where the filesystem is a
 *      read-only build artifact and the Python pipeline never runs.
 *   2. Disk — the local pipeline's own output, so `npm run dev` works with no
 *      KV setup at all.
 *
 * Both degrade to `fallback`, since neither exists on a fresh deploy.
 */
import { promises as fs } from "fs";
import path from "path";
import { kvEnabled, kvGetJson } from "@/lib/kv";

/** KV key for a pushed data file. Mirrors the key scheme in the ingest route. */
export const fileKey = (name: string) => `file:${name}`;

interface PushedFile<T> {
  data: T;
  ts: number;
}

export async function readJsonFile<T>(name: string, fallback: T): Promise<T> {
  if (kvEnabled) {
    const pushed = await kvGetJson<PushedFile<T>>(fileKey(name));
    if (pushed?.data != null) {
      const age = pushed.ts ? Math.round((Date.now() - pushed.ts) / 1000) : null;
      console.log(`  [datafiles] serving pushed ${name} from KV, age ${age}s`);
      return pushed.data;
    }
  }

  try {
    const p = path.join(process.cwd(), name);
    const raw = await fs.readFile(p, "utf-8");
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

/** Age in seconds of the pushed snapshot, or null if none / KV unset. */
export async function pushedFileAge(name: string): Promise<number | null> {
  if (!kvEnabled) return null;
  const pushed = await kvGetJson<PushedFile<unknown>>(fileKey(name));
  if (!pushed?.ts) return null;
  return Math.round((Date.now() - pushed.ts) / 1000);
}
