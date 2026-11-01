// Read at request time, so one built image works against any backend: just set WS_URL where it runs.
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ wsUrl: process.env.WS_URL ?? "" });
}
