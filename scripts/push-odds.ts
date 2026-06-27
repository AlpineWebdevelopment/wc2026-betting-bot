/**
 * Push-relay: run this on a machine with a Hungarian IP (your home PC) to fetch
 * Tippmix odds and POST them to the Vercel app, bypassing the geo-block.
 *
 * It reuses lib/tippmix.ts, so the pushed payload matches exactly what the API
 * routes expect.
 *
 * Config — via env vars or scripts/push-odds.config.json (gitignored):
 *   INGEST_URL    https://<your-app>.vercel.app/api/ingest-tippmix
 *   INGEST_TOKEN  must equal the INGEST_TOKEN env var set in Vercel
 *
 * Run once:        npm run push:odds
 * Schedule:        Windows Task Scheduler → run `npm run push:odds` every ~3 min
 *                  in this project directory (see PUSH-RELAY.md).
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { getTippmixMatches, getTippmixLiveOdds } from "../lib/tippmix";

function loadConfig(): { url: string; token: string } {
  let url = process.env.INGEST_URL;
  let token = process.env.INGEST_TOKEN;
  if (!url || !token) {
    try {
      const here = dirname(fileURLToPath(import.meta.url));
      const cfg = JSON.parse(
        readFileSync(join(here, "push-odds.config.json"), "utf8")
      );
      url ||= cfg.INGEST_URL;
      token ||= cfg.INGEST_TOKEN;
    } catch {
      /* no config file — rely on env */
    }
  }
  if (!url || !token) {
    console.error(
      "[push-odds] Missing INGEST_URL / INGEST_TOKEN " +
        "(set env vars or scripts/push-odds.config.json)"
    );
    process.exit(1);
  }
  return { url, token };
}

async function main() {
  const { url, token } = loadConfig();

  const [prematch, live] = await Promise.all([
    getTippmixMatches(),
    getTippmixLiveOdds(),
  ]);

  if (!prematch.length && !live.length) {
    console.error("[push-odds] Tippmix returned no matches — not pushing.");
    process.exit(1);
  }

  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ prematch, live }),
  });

  const text = await res.text();
  console.log(
    `[push-odds] pushed ${prematch.length} prematch + ${live.length} live → ` +
      `HTTP ${res.status} ${text}`
  );
  if (!res.ok) process.exit(1);
}

main().catch((e) => {
  console.error("[push-odds]", e);
  process.exit(1);
});
