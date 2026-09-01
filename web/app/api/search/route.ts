import { NextRequest, NextResponse } from "next/server";

// Proxy to the Python API's streaming search (server-to-server, no CORS). Pipes the
// NDJSON stream straight through so the browser can roll results out as they arrive.
export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get("q")?.trim();
  if (!q) return NextResponse.json({ cards: [] });

  const base = process.env.SCOREKIT_API_URL ?? "http://localhost:8000";
  const url = new URL("/search/stream", base);
  url.searchParams.set("q", q);
  const composer = req.nextUrl.searchParams.get("composer");
  if (composer) url.searchParams.set("composer", composer);

  try {
    const upstream = await fetch(url, { cache: "no-store" });
    if (!upstream.ok || !upstream.body) {
      return NextResponse.json({ error: "search backend error" }, { status: 502 });
    }
    return new Response(upstream.body, {
      headers: { "content-type": "application/x-ndjson", "cache-control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      { error: "search backend unreachable. Is the API running?" },
      { status: 502 },
    );
  }
}
