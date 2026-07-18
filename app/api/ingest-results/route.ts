import { NextResponse } from "next/server";
import { kvSetJson, kvEnabled } from "@/lib/kv";
import { fileKey } from "@/lib/datafiles";

export const dynamic = "force-dynamic";

// Same shared secret as the odds relay — set INGEST_TOKEN in Vercel env.
const TOKEN = process.env.INGEST_TOKEN ?? "";

// Only these filenames may be written, so a leaked token can't stuff arbitrary
// keys into KV.
const ALLOWED = new Set(["wc_results_cache.json", "predictions_log.json"]);

interface IngestBody {
  files?: Record<string, unknown>;
}

/**
 * Receives the local Python pipeline's data files (completed WC results and the
 * prediction log) pushed from the home machine — see scripts/push-results.ts.
 * Stores them in KV so the History tab works in production, where the pipeline
 * never runs and the filesystem is a read-only build artifact.
 */
export async function POST(req: Request) {
  if (!TOKEN) {
    return NextResponse.json(
      { error: "ingest disabled: set INGEST_TOKEN env" },
      { status: 503 }
    );
  }
  if (!kvEnabled) {
    return NextResponse.json(
      { error: "KV not configured: attach a Vercel KV store (KV_REST_API_*)" },
      { status: 503 }
    );
  }
  if ((req.headers.get("authorization") ?? "") !== `Bearer ${TOKEN}`) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  let body: IngestBody;
  try {
    body = (await req.json()) as IngestBody;
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const files = body.files;
  if (!files || typeof files !== "object" || !Object.keys(files).length) {
    return NextResponse.json(
      { error: "body must include a non-empty 'files' object" },
      { status: 400 }
    );
  }

  const unknown = Object.keys(files).filter((n) => !ALLOWED.has(n));
  if (unknown.length) {
    return NextResponse.json(
      { error: `unsupported file(s): ${unknown.join(", ")}` },
      { status: 400 }
    );
  }

  const now = Date.now();
  const written: Record<string, number> = {};
  const oks = await Promise.all(
    Object.entries(files).map(async ([name, data]) => {
      written[name] = Array.isArray(data)
        ? data.length
        : Object.keys(data as object).length;
      return kvSetJson(fileKey(name), { data, ts: now });
    })
  );

  if (oks.some((ok) => !ok)) {
    return NextResponse.json({ error: "KV write failed" }, { status: 500 });
  }

  return NextResponse.json({ ok: true, written, ts: now });
}
