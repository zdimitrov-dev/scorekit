import { NextResponse } from "next/server";

// Proxy for the dev dashboard. Development surface, remove before release.
export async function GET() {
  const base = process.env.SCOREKIT_API_URL ?? "http://localhost:8000";
  try {
    const upstream = await fetch(new URL("/dev/stats", base), { cache: "no-store" });
    if (!upstream.ok) return NextResponse.json({ error: "api error" }, { status: 502 });
    return NextResponse.json(await upstream.json(), {
      headers: { "cache-control": "no-store" },
    });
  } catch {
    return NextResponse.json({ error: "api unreachable" }, { status: 502 });
  }
}

// Clears the interaction log. Destructive and unauthenticated: acceptable only because
// this whole surface is removed before release.
export async function POST(request: Request) {
  const base = process.env.SCOREKIT_API_URL ?? "http://localhost:8000";
  try {
    const body: unknown = await request.json().catch(() => ({}));
    const upstream = await fetch(new URL("/dev/clear-interactions", base), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body ?? {}),
      cache: "no-store",
    });
    if (!upstream.ok) return NextResponse.json({ error: "api error" }, { status: 502 });
    return NextResponse.json(await upstream.json());
  } catch {
    return NextResponse.json({ error: "api unreachable" }, { status: 502 });
  }
}
