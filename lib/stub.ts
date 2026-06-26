import { NextResponse } from "next/server";

/**
 * Helper for endpoints that depend on the local Python pipeline (scipy model
 * training, OS subprocess control) and cannot run in the Next.js/serverless
 * runtime. Returns a clear, UI-friendly message instead of a hard failure.
 */
export function localOnly(message: string, status = 501) {
  return NextResponse.json({ status: "error", message }, { status });
}
