import { NextResponse } from "next/server";

// Starts and polls a training run. Development surface, remove before release.
const base = () => process.env.SCOREKIT_API_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  try {
    const body: unknown = await request.json().catch(() => ({}));
    const upstream = await fetch(new URL("/dev/train", base()), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body ?? {}),
      cache: "no-store",
    });
    return NextResponse.json(await upstream.json(), { status: upstream.ok ? 200 : 502 });
  } catch {
    return NextResponse.json({ error: "api unreachable" }, { status: 502 });
  }
}

export async function GET() {
  try {
    const upstream = await fetch(new URL("/dev/train", base()), { cache: "no-store" });
    return NextResponse.json(await upstream.json(), { status: upstream.ok ? 200 : 502 });
  } catch {
    return NextResponse.json({ error: "api unreachable" }, { status: 502 });
  }
}
