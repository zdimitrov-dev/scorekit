import { NextResponse } from "next/server";

// Reconciles this browser's likes and saves with the interaction log. See track.syncSignals.
export async function POST(request: Request) {
  const base = process.env.SCOREKIT_API_URL ?? "http://localhost:8000";
  try {
    const body: unknown = await request.json();
    const upstream = await fetch(new URL("/interactions/sync", base), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    if (!upstream.ok) return NextResponse.json({ inserted: 0 }, { status: 502 });
    return NextResponse.json(await upstream.json());
  } catch {
    return NextResponse.json({ inserted: 0 }, { status: 502 });
  }
}
