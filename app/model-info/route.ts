import { NextResponse } from "next/server";
import matchParams from "@/model_params.json";
import cornerParams from "@/corner_model_params.json";

export const dynamic = "force-dynamic";

/** Last-trained timestamps + team counts for both models. */
export async function GET() {
  const info = (p: any) => ({
    trained_at: p?.trained_at ?? null,
    teams: Array.isArray(p?.teams) ? p.teams.length : 0,
  });
  return NextResponse.json({
    match_bot: info(matchParams),
    corner_bot: info(cornerParams),
  });
}
