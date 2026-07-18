/**
 * Push-relay for the Python pipeline's data files.
 *
 * The History tab reads wc_results_cache.json (completed WC results, written by
 * retrain.py) and predictions_log.json (the bot's logged picks). Neither exists
 * on Vercel — the pipeline only runs at home. This pushes them to KV so
 * production serves the same data your local instance sees.
 *
 * Config — same env vars / config file as push-odds (scripts/push-odds.config.json):
 *   INGEST_URL    https://<your-app>.vercel.app/api/ingest-tippmix
 *                 (the results URL is derived from it, or set INGEST_RESULTS_URL)
 *   INGEST_TOKEN  must equal the INGEST_TOKEN env var set in Vercel
 *
 * Run once:  npm run push:results
 * Schedule:  after each retrain (see PUSH-RELAY.md) — hourly is plenty, these
 *            files only change when a match finishes.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const FILES = ["wc_results_cache.json", "predictions_log.json"];

function loadConfig(): { url: string; token: string } {
  let url = process.env.INGEST_RESULTS_URL;
  let base = process.env.INGEST_URL;
  let token = process.env.INGEST_TOKEN;

  if (!url || !token) {
    try {
      const here = dirname(fileURLToPath(import.meta.url));
      const cfg = JSON.parse(
        readFileSync(join(here, "push-odds.config.json"), "utf8")
      );
      url ||= cfg.INGEST_RESULTS_URL;
      base ||= cfg.INGEST_URL;
      token ||= cfg.INGEST_TOKEN;
    } catch {
      /* no config file — rely on env */
    }
  }

  // Derive the results endpoint from the odds one so a single config entry
  // keeps working: .../api/ingest-tippmix → .../api/ingest-results
  if (!url && base) url = base.replace(/ingest-tippmix\/?$/, "ingest-results");

  if (!url || !token) {
    console.error(
      "[push-results] Missing INGEST_URL / INGEST_TOKEN " +
        "(set env vars or scripts/push-odds.config.json)"
    );
    process.exit(1);
  }
  return { url, token };
}

async function main() {
  const { url, token } = loadConfig();
  const root = join(dirname(fileURLToPath(import.meta.url)), "..");

  const files: Record<string, unknown> = {};
  for (const name of FILES) {
    try {
      files[name] = JSON.parse(readFileSync(join(root, name), "utf8"));
    } catch {
      console.warn(`[push-results] ${name} not found locally — skipping.`);
    }
  }

  if (!Object.keys(files).length) {
    console.error(
      "[push-results] No data files found — run retrain.py first. Not pushing."
    );
    process.exit(1);
  }

  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ files }),
  });

  const text = await res.text();
  console.log(
    `[push-results] pushed ${Object.keys(files).join(", ")} → ` +
      `HTTP ${res.status} ${text}`
  );
  if (!res.ok) process.exit(1);
}

main().catch((e) => {
  console.error("[push-results]", e);
  process.exit(1);
});
