import { supabaseServer } from "./supabase";
import type { FeedCard } from "./types";

const SELECT =
  "id,source,kind,external_id,url,title,thumbnail_url,author,metadata,piece:pieces(id,title,composer)";

/** Relevance-first ordering: match_score desc, then view_count desc. */
function byRelevance(a: FeedCard, b: FeedCard): number {
  const ms = (b.metadata?.match_score ?? 0) - (a.metadata?.match_score ?? 0);
  if (ms !== 0) return ms;
  return (b.metadata?.view_count ?? 0) - (a.metadata?.view_count ?? 0);
}

/**
 * Fetch cards for the feed, newest pieces' cards included, sorted by relevance.
 * Small dataset today, so we fetch a cap and sort in JS; SQL-side ranking is a
 * scale-time refinement.
 */
export async function getCards(limit = 300): Promise<FeedCard[]> {
  const sb = supabaseServer();
  const { data, error } = await sb.from("cards").select(SELECT).limit(limit);
  if (error) throw new Error(error.message);
  const cards = (data ?? []) as unknown as FeedCard[];
  cards.sort(byRelevance);
  // Dedupe only *true* duplicates: cards that resolve to the same canonical page
  // (e.g. an IMSLP redirect and the work it points at). Cards that merely reuse a
  // thumbnail but resolve to different pages are kept — thumbnail != content.
  const seen = new Set<string>();
  return cards.filter((c) => {
    const key = `${c.source}:${c.metadata?.canonical_page ?? c.external_id}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
