import { NextRequest, NextResponse } from "next/server";

// Proxy to the Python API's content-based ranker (server-to-server, no CORS).
// The browser posts its own like/save signals because they still live in localStorage
// until auth lands; the ranking itself happens server-side.
export async function POST(req: NextRequest) {
  const base = process.env.SCOREKIT_API_URL ?? "http://localhost:8000";
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    body = { signals: [] };
  }

  try {
    const upstream = await fetch(new URL("/recommend", base), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    if (!upstream.ok) {
      return NextResponse.json({ error: "recommend backend error" }, { status: 502 });
    }
    return NextResponse.json(await upstream.json(), {
      headers: { "cache-control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      { error: "recommend backend unreachable — is the API running?" },
      { status: 502 },
    );
  }
}
