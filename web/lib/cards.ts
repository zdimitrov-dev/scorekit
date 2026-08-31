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
  // Drop cards that share a thumbnail with a higher-ranked one — e.g. an IMSLP
  // redirect page and the canonical work both resolve to the same first-page image.
  const seenThumbs = new Set<string>();
  return cards.filter((c) => {
    if (!c.thumbnail_url) return true;
    if (seenThumbs.has(c.thumbnail_url)) return false;
    seenThumbs.add(c.thumbnail_url);
    return true;
  });
}
