"use client";
import { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw, Sparkles, FlaskConical } from "lucide-react";
import type { FeedCard } from "@/lib/types";
import { currentSignals, getFresh, refreshFeed, type Ranker } from "@/lib/feedCache";
import Feed from "./Feed";

/**
 * The home / recommendation feed.
 *
 * Reads a **cache built ahead of time** (see lib/feedCache) rather than fetching on mount.
 * Ranking needs the browser's like/save history, which the server cannot see, so Home used
 * to paint a server-rendered board and then swap it once the real ranking arrived — a
 * couple of seconds of the wrong order, then a jump. Now the ranking is normally already
 * waiting, so the correct board paints immediately, and when it isn't ready the placeholder
 * is neutral instead of being a different feed.
 */
export default function HomeFeed() {
  const [cards, setCards] = useState<FeedCard[] | null>(null);
  const [personalized, setPersonalized] = useState(false);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [signalCount, setSignalCount] = useState(0);
  // Which ranker to ask for. "auto" is the real behaviour: the learned model only once it
  // has passed its gate. "model" forces a saved-but-unpromoted model so it can be tried.
  const [ranker, setRanker] = useState<Ranker>("auto");
  const [servedBy, setServedBy] = useState<string>("content");
  const [modelAvailable, setModelAvailable] = useState(false);

  const load = useCallback(async (force: boolean, want: Ranker) => {
    setSignalCount(currentSignals().length);
    const cached = force ? null : getFresh(want);
    if (cached) {
      setCards(cached.cards);
      setPersonalized(cached.personalized);
      setServedBy(cached.ranker);
      setModelAvailable(cached.modelAvailable);
      return;
    }
    setLoading(true);
    const entry = await refreshFeed(want);
    if (entry) {
      setCards(entry.cards);
      setPersonalized(entry.personalized);
      setServedBy(entry.ranker);
      setModelAvailable(entry.modelAvailable);
      setFailed(false);
    } else {
      setFailed(true);
      setCards((prev) => prev ?? []);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load(false, ranker);
  }, [load, ranker]);

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
            "Recommendations are offline."
          ) : (
            "Popular right now. Like a few pieces to tune this feed."
          )}
        </span>
        <span className="flex shrink-0 items-center gap-2">
        {modelAvailable && (
          <button
            onClick={() => setRanker(ranker === "model" ? "auto" : "model")}
            title="Rank with the trained model instead of the hand-tuned scoring"
            className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 font-medium transition-colors ${
              servedBy === "model"
                ? "bg-[var(--accent)] text-white"
                : "bg-[var(--surface-2)] hover:text-[var(--foreground)]"
            }`}
          >
            <FlaskConical size={13} />
            {servedBy === "model" ? "Trained model" : "Try trained model"}
          </button>
        )}
        <button
          onClick={() => void load(true, ranker)}
          disabled={loading}
          title="Rebuild the feed from everything you've liked and saved since"
          className="flex shrink-0 items-center gap-1.5 rounded-full bg-[var(--surface-2)] px-3 py-1.5 font-medium transition-colors hover:text-[var(--foreground)] disabled:opacity-40"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          Refresh feed
        </button>
        </span>
      </div>

      {cards === null ? (
        // Neutral placeholders, never a differently-ordered board: showing real cards in
        // the wrong order and then re-sorting them is the flash this replaces.
        <div className="flex gap-3">
          {Array.from({ length: 3 }, (_, col) => (
            <div key={col} className="flex-1 space-y-3">
              {[240, 190, 270, 210].map((h, i) => (
                <div
                  key={i}
                  style={{ height: h }}
                  className="animate-pulse rounded-2xl bg-[var(--surface)]"
                />
              ))}
            </div>
          ))}
        </div>
      ) : (
        <Feed
          cards={cards}
          maxColumns={3}
          emptyLabel="Nothing here yet. Search for a piece to get started."
        />
      )}
    </div>
  );
}
