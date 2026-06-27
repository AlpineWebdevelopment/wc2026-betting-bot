/**
 * Tippmix.hu odds fetcher — port of tippmix.py.
 * Calls the public tippmix.hu JSON API directly via fetch (no browser).
 */
import { ProxyAgent } from "undici";
import type { MarketGroup } from "@/lib/valuebets";

const API_BASE = "https://api.tippmix.hu";

// tippmix.hu geo-blocks non-Hungarian IPs. On Vercel (US/EU datacenters) the
// requests are refused, so route them through a Hungarian-exit proxy when
// TIPPMIX_PROXY_URL is set (e.g. "http://user:pass@hu-proxy.example.com:8080").
// Inert locally / when unset — falls back to a direct connection.
const PROXY_URL = process.env.TIPPMIX_PROXY_URL;
const proxyDispatcher = PROXY_URL ? new ProxyAgent(PROXY_URL) : undefined;

/** Merge the proxy dispatcher into fetch options when a proxy is configured. */
function withProxy(init: RequestInit): RequestInit {
  return proxyDispatcher
    ? ({ ...init, dispatcher: proxyDispatcher } as RequestInit)
    : init;
}

const HEADERS: Record<string, string> = {
  Accept: "application/json, text/plain, */*",
  "Content-Type": "application/json;charset=UTF-8",
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)",
  Referer: "https://www.tippmix.hu/",
  "Accept-Language": "hu-HU",
};

// Hungarian name → English name mapping for WC 2026 teams
export const HU_TO_EN: Record<string, string> = {
  Mexikó: "Mexico",
  "Dél-Afrika": "South Africa",
  Marokkó: "Morocco",
  Portugália: "Portugal",
  Argentína: "Argentina",
  "Szaúd-Arábia": "Saudi Arabia",
  Lengyelország: "Poland",
  Németország: "Germany",
  Japán: "Japan",
  Spanyolország: "Spain",
  "Costa Rica": "Costa Rica",
  Belgium: "Belgium",
  Kanada: "Canada",
  Horvátország: "Croatia",
  Szerbia: "Serbia",
  Brazília: "Brazil",
  Svájc: "Switzerland",
  Kamerun: "Cameroon",
  "Dél-Korea": "Korea Republic",
  Ghána: "Ghana",
  Uruguay: "Uruguay",
  Franciaország: "France",
  Ausztrália: "Australia",
  Dánia: "Denmark",
  Tunézia: "Tunisia",
  Szenegál: "Senegal",
  Hollandia: "Netherlands",
  Ecuador: "Ecuador",
  Anglia: "England",
  Irán: "Iran",
  Wales: "Wales",
  Katar: "Qatar",
  "Egyesült Államok": "United States",
  USA: "United States",
  Panamá: "Panama",
  Jamaika: "Jamaica",
  Bolívia: "Bolivia",
  Venezuela: "Venezuela",
  Kolumbia: "Colombia",
  Chile: "Chile",
  Peru: "Peru",
  Paraguay: "Paraguay",
  Honduras: "Honduras",
  Nigéria: "Nigeria",
  Elefántcsontpart: "Ivory Coast",
  Mali: "Mali",
  Kenya: "Kenya",
  Egyiptom: "Egypt",
  "DR Kongó": "DR Congo",
  Algéria: "Algeria",
  Szlovénia: "Slovenia",
  Ausztria: "Austria",
  Törökország: "Turkey",
  Csehország: "Czech Republic",
  "Új-Zéland": "New Zealand",
  Norvégia: "Norway",
  Svédország: "Sweden",
  Skócia: "Scotland",
  Görögország: "Greece",
  Románia: "Romania",
  Ukrajna: "Ukraine",
  Magyarország: "Hungary",
  Olaszország: "Italy",
  "Bosznia-Hercegovina": "Bosnia & Herzegovina",
  // AFC teams missing from original map
  Üzbegisztán: "Uzbekistan",
  Irak: "Iraq",
  Tadzsikisztán: "Tajikistan",
  Indonézia: "Indonesia",
  Kína: "China",
  Kuvait: "Kuwait",
  Omán: "Oman",
  Bahrain: "Bahrain",
  Jordánia: "Jordan",
  // Other missing teams
  Izland: "Iceland",
  Grúzia: "Georgia",
  Albánia: "Albania",
  "Észak-Macedónia": "North Macedonia",
  Kongó: "Congo",
  Mozambik: "Mozambique",
  Tanzánia: "Tanzania",
  Zambia: "Zambia",
  Etiópia: "Ethiopia",
  Angola: "Angola",
  Finnország: "Finland",
  "Trinidad és Tobago": "Trinidad and Tobago",
  Guatemala: "Guatemala",
  "El Salvador": "El Salvador",
  Guyana: "Guyana",
  Suriname: "Suriname",
};

function en(name: string): string {
  return HU_TO_EN[name] ?? name;
}

export interface TippmixMatch {
  home_team_hu: string;
  away_team_hu: string;
  home_team: string;
  away_team: string;
  competition: string;
  is_wc: boolean;
  event_date?: string;
  home_odds: number | null;
  draw_odds: number | null;
  away_odds: number | null;
  event_id?: number;
  market_groups?: MarketGroup[];
}

function parseEvents(data: any): TippmixMatch[] {
  const matches: TippmixMatch[] = [];
  for (const sportBlock of data?.data ?? []) {
    if (sportBlock.sportId !== 1) continue;
    for (const ev of sportBlock.events ?? []) {
      if (ev.isLive || ev.bettingStatus !== 0) continue;
      const participants = ev.eventParticipants ?? [];
      if (participants.length < 2) continue;

      const homeHu = participants[0].participantName;
      const awayHu = participants[1].participantName;
      const eventDate = ev.eventDate ?? "";

      const market1x2 = (ev.markets ?? []).find(
        (m: any) => m.marketName === "1X2"
      );
      if (!market1x2) continue;

      const outcomes: Record<number, number> = {};
      for (const o of market1x2.outcomes ?? []) outcomes[o.outcomeNo] = o.fixedOdds;
      const homeOdds = outcomes[1];
      const drawOdds = outcomes[2];
      const awayOdds = outcomes[3];
      if (!homeOdds || !drawOdds || !awayOdds) continue;

      const competition = ev.competitionName ?? "";
      const isWc = (ev.competitions ?? []).some((c: any) => c.name === "vb");

      matches.push({
        home_team_hu: homeHu,
        away_team_hu: awayHu,
        home_team: en(homeHu),
        away_team: en(awayHu),
        competition,
        is_wc: isWc,
        event_date: eventDate,
        home_odds: homeOdds,
        draw_odds: drawOdds,
        away_odds: awayOdds,
        event_id: ev.eventId,
      });
    }
  }
  return matches;
}

function parseLiveEvents(data: any): TippmixMatch[] {
  const matches: TippmixMatch[] = [];
  for (const sportBlock of data?.data ?? []) {
    if (sportBlock.sportId !== 1) continue;
    for (const ev of sportBlock.events ?? []) {
      if (!ev.isLive) continue;
      const participants = ev.eventParticipants ?? [];
      if (participants.length < 2) continue;

      const homeHu = participants[0].participantName;
      const awayHu = participants[1].participantName;

      const market1x2 = (ev.markets ?? []).find(
        (m: any) => m.marketName === "1X2"
      );
      let homeOdds: number | null = null;
      let drawOdds: number | null = null;
      let awayOdds: number | null = null;
      if (market1x2) {
        const outcomes: Record<number, number> = {};
        for (const o of market1x2.outcomes ?? [])
          outcomes[o.outcomeNo] = o.fixedOdds;
        homeOdds = outcomes[1] ?? null;
        drawOdds = outcomes[2] ?? null;
        awayOdds = outcomes[3] ?? null;
      }

      const competition = ev.competitionName ?? "";
      const isWc = (ev.competitions ?? []).some((c: any) => c.name === "vb");

      matches.push({
        home_team_hu: homeHu,
        away_team_hu: awayHu,
        home_team: en(homeHu),
        away_team: en(awayHu),
        competition,
        is_wc: isWc,
        home_odds: homeOdds,
        draw_odds: drawOdds,
        away_odds: awayOdds,
        event_id: ev.eventId,
      });
    }
  }
  return matches;
}

async function fetchEventMarkets(eventId: number): Promise<MarketGroup[]> {
  try {
    const r = await fetch(`${API_BASE}/v2/tippmix/event/${eventId}`, withProxy({
      headers: HEADERS,
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
    }));
    if (!r.ok) return [];
    const j = await r.json();
    return j?.event?.marketGroups ?? [];
  } catch {
    return [];
  }
}

async function fetchEventsList(): Promise<any | null> {
  for (const path of ["/tippmix/best-games", "/tippmix/last-minute"]) {
    try {
      const r = await fetch(`${API_BASE}${path}`, withProxy({
        method: "POST",
        headers: HEADERS,
        body: "{}",
        cache: "no-store",
        signal: AbortSignal.timeout(20000),
      }));
      const body = await r.text();
      if (r.status === 200) {
        try {
          return JSON.parse(body);
        } catch {
          // 200 but HTML → a block / anti-bot challenge page, not real data.
          const server = r.headers.get("server") ?? "?";
          const snippet = body.slice(0, 160).replace(/\s+/g, " ");
          console.log(
            `  [tippmix] ${path} -> HTTP 200 non-JSON (server=${server}, ${body.length}b): ${snippet}`
          );
          continue;
        }
      }
      const snippet = body.slice(0, 160).replace(/\s+/g, " ");
      console.log(`  [tippmix] ${path} -> HTTP ${r.status}: ${snippet}`);
    } catch (e) {
      console.log(`  [tippmix] ${path} fetch error: ${e}`);
      continue;
    }
  }
  return null;
}

export async function getTippmixMatches(): Promise<TippmixMatch[]> {
  console.log("  Fetching Tippmix.hu odds via API...");
  const data = await fetchEventsList();
  const baseMatches = data ? parseEvents(data) : [];

  const wc = baseMatches.filter((m) => m.is_wc && m.event_id);
  if (wc.length) {
    const groups = await Promise.all(
      wc.map((m) => fetchEventMarkets(m.event_id as number))
    );
    wc.forEach((m, i) => {
      m.market_groups = groups[i];
    });
  }
  for (const m of baseMatches) m.market_groups ??= [];

  const other = baseMatches.filter((m) => !m.is_wc);
  console.log(
    `  Got ${wc.length} WC matches + ${other.length} other football matches from Tippmix`
  );
  return baseMatches;
}

export async function getTippmixLiveOdds(): Promise<TippmixMatch[]> {
  console.log("  Fetching Tippmix.hu LIVE odds via API...");
  const data = await fetchEventsList();
  const matches = data ? parseLiveEvents(data) : [];

  const wcLive = matches.filter((m) => m.is_wc && m.event_id);
  if (wcLive.length) {
    const groups = await Promise.all(
      wcLive.map((m) => fetchEventMarkets(m.event_id as number))
    );
    wcLive.forEach((m, i) => {
      m.market_groups = Array.isArray(groups[i]) ? groups[i] : [];
    });
  }
  for (const m of matches) m.market_groups ??= [];

  const wc = matches.filter((m) => m.is_wc);
  console.log(
    `  Got ${wc.length} live WC matches from Tippmix (${matches.length} total live)`
  );
  return matches;
}
