import { NextRequest, NextResponse } from "next/server";

// Proxy to the Python API's interaction log (server-to-server, no CORS).
//
// Always answers 204, whatever happened upstream. This is the telemetry path: the client
// fires it via sendBeacon on the way out and cannot react to a failure anyway, and a
// broken logger must never surface as an error in the user's console.
export async function POST(req: NextRequest) {
  const base = process.env.SCOREKIT_API_URL ?? "http://localhost:8000";
  try {
    const body = await req.text();
    await fetch(new URL("/interactions", base), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body,
      cache: "no-store",
    });
  } catch {
    /* swallowed on purpose — see above */
  }
  return new NextResponse(null, { status: 204 });
}
