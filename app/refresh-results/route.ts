import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

/**
 * Result tracking (fetching completed ESPN matches into wc_results_cache.json)
 * requires the local Python pipeline + persistent storage, neither of which
 * exists on serverless. Reported gracefully so the History tab keeps working.
 */
export async function GET() {
  return NextResponse.json({
    status: "unavailable",
    message:
      "Az eredmények frissítése a helyi Python pipeline-t igényli (perzisztens tároló). A meglévő előzmények csak olvashatók.",
    completed_matches: 0,
  });
}
