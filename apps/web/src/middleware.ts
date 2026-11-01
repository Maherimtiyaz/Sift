import { NextResponse, type NextRequest } from "next/server";

// Pages need a session cookie. The API validates the token itself, so /api passes through.
export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (pathname.startsWith("/api") || ["/login", "/signup", "/welcome"].includes(pathname)) return NextResponse.next();
  if (!req.cookies.get("sift_session")) {
    if (pathname === "/") return NextResponse.rewrite(new URL("/welcome", req.url));
    return NextResponse.redirect(new URL("/welcome", req.url));
  }
  return NextResponse.next();
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
