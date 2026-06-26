import { NextResponse } from "next/server";
import { model } from "@/lib/model";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json([...model.teams].sort());
}
