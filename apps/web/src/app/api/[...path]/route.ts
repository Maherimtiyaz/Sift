import type { NextRequest } from "next/server";
import { API, COOKIE } from "@/lib/session";

// Same-origin proxy: reads the session cookie and forwards the JWT to FastAPI as a Bearer token.
async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const headers = new Headers();
  const token = req.cookies.get(COOKIE)?.value;
  if (token) headers.set("authorization", `Bearer ${token}`);
  const type = req.headers.get("content-type");
  if (type) headers.set("content-type", type);
  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const res = await fetch(`${API}/api/${path.join("/")}${req.nextUrl.search}`, {
    method: req.method,
    headers,
    body: hasBody ? await req.arrayBuffer() : undefined,
    redirect: "manual",
    cache: "no-store",
  });
  return new Response(res.body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
  });
}

export { proxy as GET, proxy as POST, proxy as PATCH, proxy as DELETE };
