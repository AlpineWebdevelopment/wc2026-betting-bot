import { NextResponse } from "next/server";
import { AUTH_COOKIE, checkCredentials, expectedToken } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  let user = "";
  let pass = "";
  try {
    const body = await req.json();
    user = String(body.user ?? "");
    pass = String(body.pass ?? "");
  } catch {
    return NextResponse.json({ error: "Invalid request" }, { status: 400 });
  }

  if (!checkCredentials(user, pass)) {
    return NextResponse.json({ error: "Hibás felhasználónév vagy jelszó" }, { status: 401 });
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set(AUTH_COOKIE, await expectedToken(), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24 * 30, // 30 days
  });
  return res;
}
