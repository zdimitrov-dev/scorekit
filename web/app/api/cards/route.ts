import { NextRequest, NextResponse } from "next/server";
import { supabaseServer } from "@/lib/supabase";
import type { FeedCard } from "@/lib/types";

const SELECT =
  "id,source,kind,external_id,url,title,thumbnail_url,author,metadata,piece:pieces(id,title,composer)";

// Postgres rejects absurdly long `IN` lists, and a saved collection should never get near
// this — but a malformed request must not become a database error.
const MAX_IDS = 500;

/**
 * Fetch specific cards by id.
 *
 * Saved and liked collections live in the browser, so the server cannot know which cards a
 * page needs until the browser asks. Previously the Saved tab worked the other way round —
 * it pulled a capped slice of the corpus and filtered it down — which silently dropped any
 * saved card that happened to fall outside the cap.
 */
export async function POST(req: NextRequest) {
  let ids: string[] = [];
  try {
    const body = (await req.json()) as { ids?: unknown };
    if (Array.isArray(body.ids)) {
      ids = body.ids.filter((v): v is string => typeof v === "string").slice(0, MAX_IDS);
    }
  } catch {
    return NextResponse.json({ cards: [] });
  }
  if (ids.length === 0) return NextResponse.json({ cards: [] });

  const { data, error } = await supabaseServer().from("cards").select(SELECT).in("id", ids);
  if (error) return NextResponse.json({ cards: [], error: error.message }, { status: 502 });

  // Return them in the order asked for, so the caller controls presentation.
  const byId = new Map((data ?? []).map((c) => [(c as unknown as FeedCard).id, c]));
  return NextResponse.json(
    { cards: ids.map((id) => byId.get(id)).filter(Boolean) },
    { headers: { "cache-control": "no-store" } },
  );
}
