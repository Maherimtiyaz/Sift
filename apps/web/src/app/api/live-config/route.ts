// Read at request time, so one built image works against any backend: just set WS_URL where it runs.
export const dynamic = "force-dynamic";

export async function GET() {
  const apiUrl = process.env.API_URL ?? "http://localhost:8000";
  const response = await fetch(`${apiUrl}/api/health`, {
    cache: "no-store",
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) {
    return Response.json({ detail: "Couldn’t read the API health status." }, { status: 502 });
  }
  const health: { demo_mode?: unknown } = await response.json();
  const demoMode = health.demo_mode === true;
  return Response.json({
    wsUrl: demoMode ? "" : process.env.WS_URL ?? "",
    demoMode,
  });
}
