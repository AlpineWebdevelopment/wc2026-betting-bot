import { NextResponse } from "next/server";
import { THE_ODDS_API_KEY } from "@/lib/config";
import { refreshOdds } from "@/lib/store";

export const dynamic = "force-dynamic";

export async function GET() {
  if (!THE_ODDS_API_KEY)
    return NextResponse.json({
      status: "no_key",
      message: "Add THE_ODDS_API_KEY in the environment",
    });
  const matchesLoaded = await refreshOdds();
  return NextResponse.json({ status: "ok", matches_loaded: matchesLoaded });
}
