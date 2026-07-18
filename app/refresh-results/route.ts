import { NextResponse } from "next/server";
import { readJsonFile, pushedFileAge } from "@/lib/datafiles";

export const dynamic = "force-dynamic";

interface ResultMatch {
  home_team: string;
  away_team: string;
}

/**
 * Fetching completed matches from ESPN needs the local Python pipeline
 * (retrain.py), which can't run on serverless. What this endpoint *can* do is
 * report the state of the snapshot the relay last pushed — so the History tab
 * shows whether its data is current rather than a flat "unavailable".
 */
export async function GET() {
  const cache = await readJsonFile<Record<string, ResultMatch[]>>(
    "wc_results_cache.json",
    {}
  );

  const completed = Object.values(cache).reduce(
    (n, day) => n + (Array.isArray(day) ? day.length : 0),
    0
  );
  const age = await pushedFileAge("wc_results_cache.json");

  if (!completed) {
    return NextResponse.json({
      status: "unavailable",
      message:
        "Nincs eredmény-pillanatkép. Futtasd itthon a retrain.py-t, majd a `npm run push:results` parancsot.",
      completed_matches: 0,
      snapshot_age_s: null,
    });
  }

  return NextResponse.json({
    status: "ok",
    message:
      `${completed} befejezett mérkőzés a legutóbbi pillanatképből` +
      (age !== null ? ` (${Math.round(age / 60)} perce frissítve).` : "."),
    completed_matches: completed,
    snapshot_age_s: age,
  });
}
