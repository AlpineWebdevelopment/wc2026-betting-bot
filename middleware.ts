import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { AUTH_COOKIE, isTokenValid } from "@/lib/auth";

// Paths that must stay reachable without a session.
const PUBLIC_PATHS = ["/login", "/api/login", "/api/logout"];

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  if (PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"))) {
    return NextResponse.next();
  }

  const token = req.cookies.get(AUTH_COOKIE)?.value;
  if (await isTokenValid(token)) {
    return NextResponse.next();
  }

  // Route handlers (data fetches) → 401 JSON; page navigations → /login.
  const wantsHtml = (req.headers.get("accept") ?? "").includes("text/html");
  if (!wantsHtml) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const loginUrl = req.nextUrl.clone();
  loginUrl.pathname = "/login";
  loginUrl.search = "";
  return NextResponse.redirect(loginUrl);
}

export const config = {
  // Run on everything except Next internals and static assets.
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|legacy.js|.*\\.(?:png|jpg|jpeg|svg|gif|ico|css|js|woff|woff2|ttf)).*)",
  ],
};
