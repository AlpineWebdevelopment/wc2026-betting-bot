# Tippmix push-relay (geo-block workaround)

`api.tippmix.hu` only accepts requests from **Hungarian IPs**, so the direct
fetch fails on Vercel (US/EU datacenters). This relay runs the fetch on a
machine that already has a Hungarian IP (your home PC) and **pushes** the odds
to the app. Purely outbound from home → Vercel: no proxy, no port-forwarding,
no exposing your home IP.

```
Home PC (HU IP) ──fetch──> tippmix.hu
       │
       └──POST odds──> Vercel /api/ingest-tippmix ──> Vercel KV ──> read routes
```

## One-time setup

### 1. Attach a Vercel KV store
Vercel dashboard → your project → **Storage** → **Create** → **KV** (Upstash).
Connect it to the project. This auto-injects `KV_REST_API_URL` and
`KV_REST_API_TOKEN` into the project's environment variables.

### 2. Set the ingest secret on Vercel
Settings → Environment Variables → add (Production, and Preview if you want):

```
INGEST_TOKEN = <a long random string>
```

Generate one, e.g.: `node -e "console.log(require('crypto').randomBytes(24).toString('hex'))"`

### 3. Redeploy
So the new env vars and the `/api/ingest-tippmix` route go live.

### 4. Configure the home push script
Copy the example config and fill it in (this file is gitignored):

```
scripts/push-odds.config.json
```
```json
{
  "INGEST_URL": "https://<your-app>.vercel.app/api/ingest-tippmix",
  "INGEST_TOKEN": "<the same value as the Vercel INGEST_TOKEN>"
}
```

### 5. Test the push
```
npm run push:odds
```
Expect: `... → HTTP 200 {"ok":true,"prematch":N,"live":M,...}`.
Then load `/tippmix-matches` in production — matches should appear.

## Keep it running (Windows Task Scheduler)

Create a task that runs every ~3 minutes:

- **Program/script:** `cmd.exe`
- **Arguments:** `/c npm run push:odds`
- **Start in:** the project folder (`c:\z_jeskoserver\z_jeskoserver\wc2026-betting-bot`)
- Trigger: repeat every 3 minutes, indefinitely.

The app serves the **last pushed snapshot**, so freshness depends on this task
running. The live route reports the snapshot age (`tippmix_cache_age`).

## How it fits together

- `scripts/push-odds.ts` — fetches via `lib/tippmix.ts` (identical payload shape),
  POSTs `{ prematch, live }`.
- `app/api/ingest-tippmix/route.ts` — token-checks, writes `tippmix:prematch`
  and `tippmix:live` to KV.
- `lib/store.ts` — read routes prefer the KV snapshot; fall back to a direct
  fetch when KV is unset (local dev still works with no setup).

## Fallback: proxy instead of relay

If you'd rather not run a home cron, set `TIPPMIX_PROXY_URL` (a Hungarian-exit
proxy) in Vercel env — `lib/tippmix.ts` will route the direct fetch through it.
The two approaches are independent; KV-pushed data always takes priority.
