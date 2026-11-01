import { NextResponse } from "next/server";

export const API = process.env.API_URL ?? "http://localhost:8000";
export const COOKIE = "sift_session";

// Secure cookies need HTTPS. Trust the proxy header (Render, Vercel, Caddy and others set it), and keep plain
// http://localhost working for local Docker runs, where some browsers reject Secure cookies.
function isSecure(req: Request) {
  const proto = req.headers.get("x-forwarded-proto")?.split(",")[0].trim() ?? new URL(req.url).protocol.replace(":", "");
  const host = (req.headers.get("host") ?? "").split(":")[0];
  return proto === "https" || (process.env.NODE_ENV === "production" && !["localhost", "127.0.0.1"].includes(host));
}

// The JWT lives in an httpOnly cookie, so page scripts can never read it.
export function setSession(res: NextResponse, token: string, secure: boolean) {
  res.cookies.set(COOKIE, token, {
    httpOnly: true, sameSite: "lax", secure,
    path: "/", maxAge: 60 * 60 * 24 * 7,
  });
}

export async function authenticate(req: Request, action: "login" | "register") {
  let res: Response;
  try {
    res = await fetch(`${API}/api/auth/${action}`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify(await req.json().catch(() => ({}))), cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
  } catch (error) {
    const detail = error instanceof DOMException && error.name === "TimeoutError"
      ? "The authentication service took too long. Please try again."
      : "The authentication service is unavailable. Please try again.";
    return NextResponse.json({ detail }, { status: 503 });
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return NextResponse.json({ detail: data.detail ?? "Request failed" }, { status: res.status });
  const out = NextResponse.json({ ok: true });
  setSession(out, data.access_token, isSecure(req));
  return out;
}
