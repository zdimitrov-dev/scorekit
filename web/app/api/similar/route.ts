import { NextRequest, NextResponse } from "next/server";

// Proxy to the Python API's "more like this" ranking (server-to-server, no CORS).
export async function GET(req: NextRequest) {
  const cardId = req.nextUrl.searchParams.get("card_id");
  if (!cardId) return NextResponse.json({ cards: [] });

  const base = process.env.SCOREKIT_API_URL ?? "http://localhost:8000";
  const url = new URL("/similar", base);
  url.searchParams.set("card_id", cardId);
  url.searchParams.set("limit", req.nextUrl.searchParams.get("limit") ?? "12");

  try {
    const upstream = await fetch(url, { cache: "no-store" });
    if (!upstream.ok) return NextResponse.json({ cards: [] }, { status: 502 });
    return NextResponse.json(await upstream.json(), {
      headers: { "cache-control": "no-store" },
    });
  } catch {
    // the modal simply shows nothing rather than an error — this is a nice-to-have strip
    return NextResponse.json({ cards: [] }, { status: 502 });
  }
}
