"use client";
import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import type { FeedCard } from "@/lib/types";
import PieceCard from "./PieceCard";

/**
 * "More like this" — cards similar to the one currently open.
 *
 * Ranked against **that card alone**, not against the viewer's taste, so it works on the
 * very first click and cannot pull the home feed around. Browsing in here is exploring one
 * thing, not stating a preference, so the cards deliberately do **not** log impressions —
 * otherwise opening a card would quietly record a dozen "not interested" votes against
 * pieces the viewer never even scrolled to.
 */
export default function SimilarStrip({
  card,
  onSelect,
}: {
  card: FeedCard;
  onSelect: (c: FeedCard) => void;
}) {
  const [cards, setCards] = useState<FeedCard[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setCards([]);
    (async () => {
      try {
        const res = await fetch(`/api/similar?card_id=${encodeURIComponent(card.id)}&limit=12`);
        const data = (await res.json()) as { cards?: FeedCard[] };
        if (!cancelled) setCards(Array.isArray(data.cards) ? data.cards : []);
      } catch {
        if (!cancelled) setCards([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [card.id]);

  if (!loading && cards.length === 0) return null;

  return (
    <div className="border-t border-[var(--border)] p-5">
      <h3 className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
        <Sparkles size={13} className="text-[var(--accent)]" />
        More like this
      </h3>
      {loading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: 8 }, (_, i) => (
            <div key={i} className="h-32 animate-pulse rounded-2xl bg-[var(--surface-2)]" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {cards.map((c, i) => (
            <PieceCard key={c.id} card={c} index={i} onSelect={onSelect} compact track={false} />
          ))}
        </div>
      )}
    </div>
  );
}
