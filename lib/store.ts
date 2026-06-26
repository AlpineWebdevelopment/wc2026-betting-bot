/**
 * Shared in-memory caches (per serverless instance), replacing the module-level
 * globals from app.py: the pre-match odds map and the TTL'd Tippmix live cache.
 */
import { THE_ODDS_API_KEY } from "@/lib/config";
import { getWcOdds, type OddsMatch } from "@/lib/odds";
import {
  getTippmixLiveOdds,
  getTippmixMatches,
  type TippmixMatch,
} from "@/lib/tippmix";

// ── Pre-match odds (The Odds API) ────────────────────────────────────────────
let _liveOdds: Record<string, OddsMatch> = {};
let _liveOddsTs = 0;
const ODDS_TTL = 5 * 60_000; // 5 min

export async function refreshOdds(): Promise<number> {
  _liveOdds = {};
  if (THE_ODDS_API_KEY) {
    for (const m of await getWcOdds()) {
      _liveOdds[`${m.home_team}|${m.away_team}`] = m;
    }
  }
  _liveOddsTs = Date.now();
  return Object.keys(_liveOdds).length;
}

/** Lazily refresh the odds map if never loaded or stale. */
export async function getLiveOdds(): Promise<Record<string, OddsMatch>> {
  if (!_liveOddsTs || Date.now() - _liveOddsTs > ODDS_TTL) {
    await refreshOdds();
  }
  return _liveOdds;
}

// ── Shared TTL cache for pre-match Tippmix data ──────────────────────────────
// /tippmix-matches, /tippmix-corners and /tippmix-cards all read from this cache,
// so they always see the same Tippmix snapshot.
let _prematchCache: TippmixMatch[] = [];
let _prematchTs = 0;
const PREMATCH_TTL = 300_000; // 5 minutes

export async function getTippmixPrematchCached(): Promise<TippmixMatch[]> {
  const now = Date.now();
  if (!_prematchTs || now - _prematchTs > PREMATCH_TTL) {
    _prematchCache = await getTippmixMatches();
    _prematchTs = now;
  }
  return [..._prematchCache];
}

// ── Tippmix live odds (TTL-based; safe for serverless) ───────────────────────
let _tippmixLiveCache: TippmixMatch[] = [];
let _tippmixLiveTs = 0;
const TIPPMIX_LIVE_TTL = 120_000; // 120s

/** Return cached live odds + cache age (s), refreshing if stale. */
export async function getTippmixLiveCached(): Promise<{
  data: TippmixMatch[];
  age: number | null;
}> {
  const now = Date.now();
  let age: number | null = _tippmixLiveTs
    ? Math.round((now - _tippmixLiveTs) / 1000)
    : null;

  if (!_tippmixLiveTs || now - _tippmixLiveTs > TIPPMIX_LIVE_TTL) {
    try {
      _tippmixLiveCache = await getTippmixLiveOdds();
      _tippmixLiveTs = now;
      age = 0;
    } catch (e) {
      console.log(`  [live cache] Tippmix live fetch failed: ${e}`);
    }
  }
  return { data: [..._tippmixLiveCache], age };
}
