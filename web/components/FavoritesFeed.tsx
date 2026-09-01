"use client";
import { useEffect, useState } from "react";
import { Bookmark } from "lucide-react";
import type { FeedCard } from "@/lib/types";
import Feed from "./Feed";

/**
 * The Saved tab — **saved cards only**.
 *
 * It used to merge saves with likes, which made the two indistinguishable: a like says
 * "more of this please" and feeds the recommender, while a save says "I want to come back
 * to this". Mixing them meant the bookmark list filled with things that were never
 * bookmarked.
 *
 * Saved ids live in the browser, so the cards are fetched **by id**. The previous version
 * pulled a capped slice of the corpus server-side and filtered it down to the saved ones,
 * which silently dropped anything saved that fell outside the cap — with 1200 cards behind
 * a cap of 300, most of a collection could simply fail to appear.
 */
export default function FavoritesFeed() {
  const [cards, setCards] = useState<FeedCard[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let ids: string[] = [];
      try {
        const raw = localStorage.getItem("scorekit:saves");
        const parsed: unknown = raw ? JSON.parse(raw) : [];
        // newest save first — `useCollection` appends, so stored order is oldest-first
        ids = Array.isArray(parsed)
          ? parsed.filter((v): v is string => typeof v === "string").reverse()
          : [];
      } catch {
        ids = [];
      }
      if (ids.length === 0) {
        if (!cancelled) setCards([]);
        return;
      }
      try {
        const res = await fetch("/api/cards", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ ids }),
        });
        const data = (await res.json()) as { cards?: FeedCard[] };
        if (!cancelled) setCards(Array.isArray(data.cards) ? data.cards : []);
      } catch {
        if (!cancelled) setCards([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // null while loading, so the empty state never flashes before localStorage is read
  if (cards === null) return null;

  return (
    <div>
      <h1 className="mb-1 flex items-center gap-2 px-1 text-xl font-bold tracking-tight">
        <Bookmark size={19} className="text-[var(--accent-2)]" />
        Saved
      </h1>
      <p className="mb-4 px-1 text-xs text-[var(--muted)]">
        {cards.length > 0
          ? `${cards.length} saved ${cards.length === 1 ? "card" : "cards"}`
          : "Cards you save are kept here."}
      </p>
      <Feed
        cards={cards}
        maxColumns={3}
        emptyLabel="Nothing saved yet — press Save on a card to keep it here."
      />
    </div>
  );
}
