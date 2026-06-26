/**
 * Read-only access to runtime data files that the local Python pipeline writes
 * (wc_results_cache.json, predictions_log.json). These don't exist on a fresh
 * serverless deploy, so every read degrades gracefully to a default value.
 */
import { promises as fs } from "fs";
import path from "path";

export async function readJsonFile<T>(name: string, fallback: T): Promise<T> {
  try {
    const p = path.join(process.cwd(), name);
    const raw = await fs.readFile(p, "utf-8");
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}
