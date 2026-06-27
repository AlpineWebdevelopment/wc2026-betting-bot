import { NextResponse } from "next/server";
import { kvSetJson, kvEnabled } from "@/lib/kv";
import type { TippmixMatch } from "@/lib/tippmix";

export const dynamic = "force-dynamic";

// Shared secret — set INGEST_TOKEN in Vercel env AND in the push script's config.
const TOKEN = process.env.INGEST_TOKEN ?? "";

interface IngestBody {
  prematch?: TippmixMatch[];
  live?: TippmixMatch[];
}

/**
 * Receives Tippmix odds pushed from a Hungarian-hosted machine (see
 * scripts/push-odds.ts) and stores them in KV for the read routes to serve.
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

  const now = Date.now();
  const writes: Promise<boolean>[] = [];
  let prematch = 0;
  let live = 0;

  if (Array.isArray(body.prematch)) {
    prematch = body.prematch.length;
    writes.push(kvSetJson("tippmix:prematch", { data: body.prematch, ts: now }));
  }
  if (Array.isArray(body.live)) {
    live = body.live.length;
    writes.push(kvSetJson("tippmix:live", { data: body.live, ts: now }));
  }

  if (!writes.length) {
    return NextResponse.json(
      { error: "body must include 'prematch' and/or 'live' arrays" },
      { status: 400 }
    );
  }

  const oks = await Promise.all(writes);
  if (oks.some((ok) => !ok)) {
    return NextResponse.json({ error: "KV write failed" }, { status: 500 });
  }

  return NextResponse.json({ ok: true, prematch, live, ts: now });
}
