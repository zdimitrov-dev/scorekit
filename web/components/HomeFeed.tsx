"use client";
import { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw, Sparkles } from "lucide-react";
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
  const [signalCount, setSignalCount] = useState(0);

  const refresh = useCallback(async () => {
    const likes = readIds("scorekit:likes");
    const saves = readIds("scorekit:saves");
    const signals = [
      ...likes.map((card_id) => ({ card_id, action: "like" })),
      ...saves.map((card_id) => ({ card_id, action: "save" })),
    ];
    setSignalCount(signals.length);
    setLoading(true);
    try {
      const res = await fetch("/api/recommend", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ signals, limit: 80 }),
      });
      const data = (await res.json()) as RecResponse;
      if (!res.ok || !Array.isArray(data.cards)) throw new Error(data.error);
      setCards(data.cards);
      setPersonalized(data.personalized);
      setFailed(false);
    } catch {
      // the board already on screen stays — better than blanking the page
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  // Re-rank on every mount, so navigating back from a search picks up what was liked
  // there without needing a page reload.
  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-3 text-xs text-[var(--muted)]">
        <span className="flex items-center gap-2">
          {loading ? (
            <>
              <Loader2 size={14} className="animate-spin" />
              Building your feed…
            </>
          ) : personalized ? (
            <>
              <Sparkles size={14} className="text-[var(--accent)]" />
              Picked from {signalCount} {signalCount === 1 ? "piece" : "pieces"} you’ve
              liked and saved
            </>
          ) : failed ? (
            "Showing the latest — recommendations are offline."
          ) : (
            "Popular right now — like a few pieces to tune this feed."
          )}
        </span>
        <button
          onClick={() => void refresh()}
          disabled={loading}
          title="Rebuild the feed from everything you've liked and saved since"
          className="flex shrink-0 items-center gap-1.5 rounded-full bg-[var(--surface-2)] px-3 py-1.5 font-medium transition-colors hover:text-[var(--foreground)] disabled:opacity-40"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          Refresh feed
        </button>
      </div>
      <Feed cards={cards} emptyLabel="Nothing here yet — search for a piece to get started." />
    </div>
  );
}
