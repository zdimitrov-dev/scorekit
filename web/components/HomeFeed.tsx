"use client";
import { useEffect, useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import type { FeedCard } from "@/lib/types";
import Feed from "./Feed";

/**
 * The home / recommendation feed — ranked by the content-based recommender.
 *
 * Likes and saves still live in localStorage (auth is Phase 5), so the browser posts its
 * own signals and the server ranks with them. The signals never persist server-side, so
 * this stays a per-browser feed until there are real accounts.
 */

type RecResponse = { cards: FeedCard[]; personalized: boolean; error?: string };

function readIds(key: string): string[] {
  try {
    const raw = localStorage.getItem(key);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((s): s is string => typeof s === "string") : [];
  } catch {
    return [];
  }
}

export default function HomeFeed({ fallback }: { fallback: FeedCard[] }) {
  const [cards, setCards] = useState<FeedCard[]>(fallback);
  const [personalized, setPersonalized] = useState(false);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const signals = [
        ...readIds("scorekit:likes").map((card_id) => ({ card_id, action: "like" })),
        ...readIds("scorekit:saves").map((card_id) => ({ card_id, action: "save" })),
      ];
      try {
        const res = await fetch("/api/recommend", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ signals, limit: 80 }),
        });
        const data = (await res.json()) as RecResponse;
        if (cancelled) return;
        if (!res.ok || !Array.isArray(data.cards)) throw new Error(data.error);
        setCards(data.cards);
        setPersonalized(data.personalized);
      } catch {
        // the server-rendered board is already on screen — keep it rather than blanking
        if (!cancelled) setFailed(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div>
      <div className="mb-4 flex items-center gap-2 text-xs text-[var(--muted)]">
        {loading ? (
          <>
            <Loader2 size={14} className="animate-spin" />
            Building your feed…
          </>
        ) : personalized ? (
          <>
            <Sparkles size={14} className="text-[var(--accent)]" />
            Picked from what you’ve liked and saved
          </>
        ) : failed ? (
          "Showing the latest — recommendations are offline."
        ) : (
          "Popular right now — like a few pieces to tune this feed."
        )}
      </div>
      <Feed cards={cards} emptyLabel="Nothing here yet — search for a piece to get started." />
    </div>
  );
}
