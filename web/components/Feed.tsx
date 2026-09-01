"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence } from "framer-motion";
import type { FeedCard } from "@/lib/types";
import PieceCard from "./PieceCard";
import CardModal from "./CardModal";

const PAGE = 24;

/**
 * Masonry board with **stable** column placement.
 *
 * CSS multi-column (`columns-2 md:columns-3`) re-flows its entire content whenever items
 * are appended, so "Load more" visually reshuffled every card already on screen. Here each
 * card is assigned a column once, into whichever column is measurably shortest at that
 * moment, and never moves again — new cards land at the bottom and everything above them
 * stays put.
 */

const BREAKPOINTS: [string, number][] = [
  ["(min-width: 1280px)", 4],
  ["(min-width: 768px)", 3],
];

function useColumnCount(): number {
  const [cols, setCols] = useState(2);
  useEffect(() => {
    const queries = BREAKPOINTS.map(([q, n]) => [window.matchMedia(q), n] as const);
    const update = () => setCols(queries.find(([m]) => m.matches)?.[1] ?? 2);
    update();
    queries.forEach(([m]) => m.addEventListener("change", update));
    return () => queries.forEach(([m]) => m.removeEventListener("change", update));
  }, []);
  return cols;
}

export default function Feed({
  cards,
  emptyLabel,
  onSelect,
}: {
  cards: FeedCard[];
  emptyLabel?: string;
  // when provided, selection is delegated to the parent (which owns the modal);
  // otherwise Feed manages its own modal.
  onSelect?: (c: FeedCard) => void;
}) {
  const [visible, setVisible] = useState(PAGE);
  const [selected, setSelected] = useState<FeedCard | null>(null);
  const [columns, setColumns] = useState<FeedCard[][]>([]);
  const colRefs = useRef<(HTMLDivElement | null)[]>([]);
  const cols = useColumnCount();
  const select = onSelect ?? setSelected;

  // Identify the list by its contents, never by array identity. Callers build these
  // arrays during render (`sortVideos(...)`, a filter), so the reference changes on every
  // parent re-render — including one caused by opening a card. Keying the reset on
  // identity therefore wiped the board on click and unmounted the card mid-transition,
  // which is why the modal never appeared.
  const signature = useMemo(() => cards.map((c) => c.id).join("|"), [cards]);

  // A genuinely different list, or a column-count change, starts the layout over; only
  // appended cards preserve their placement.
  useEffect(() => {
    setColumns([]);
    setVisible(PAGE);
  }, [signature, cols]);

  useEffect(() => {
    setColumns((prev) => {
      const placed = prev.reduce((n, c) => n + c.length, 0);
      const incoming = cards.slice(placed, visible);
      if (incoming.length === 0) return prev;

      // Measure what is actually rendered, then place new cards one at a time, tracking
      // an estimate so a whole page doesn't pile into the same column.
      const next: FeedCard[][] = Array.from({ length: cols }, (_, i) => [...(prev[i] ?? [])]);
      const heights = next.map((_, i) => colRefs.current[i]?.offsetHeight ?? 0);
      const estimate = heights.some((h) => h > 0)
        ? heights.reduce((a, b) => a + b, 0) / Math.max(1, placed)
        : 240;

      for (const card of incoming) {
        let target = 0;
        for (let c = 1; c < cols; c++) if (heights[c] < heights[target]) target = c;
        next[target].push(card);
        heights[target] += estimate;
      }
      return next;
    });
    // `columns` is intentionally absent: the functional update reads it without making
    // this effect re-run on every placement.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, visible, cols]);

  if (cards.length === 0) {
    return <p className="py-24 text-center text-[var(--muted)]">{emptyLabel ?? "No cards yet."}</p>;
  }

  return (
    <>
      <div className="flex gap-3 items-start">
        {Array.from({ length: cols }, (_, i) => (
          <div
            key={i}
            ref={(el) => {
              colRefs.current[i] = el;
            }}
            className="flex-1 min-w-0"
          >
            {(columns[i] ?? []).map((card, j) => (
              <PieceCard
                key={card.id}
                card={card}
                // position within its own column — only used to stagger the entry
                // animation, and stable so a card never re-animates on re-render
                index={j}
                onSelect={select}
              />
            ))}
          </div>
        ))}
      </div>

      {visible < cards.length && (
        <div className="mt-8 flex justify-center">
          <button
            onClick={() => setVisible((v) => v + PAGE)}
            className="rounded-full bg-[var(--surface-2)] px-6 py-3 text-sm font-semibold transition-colors hover:bg-white/10"
          >
            Load more ({cards.length - visible} left)
          </button>
        </div>
      )}

      {!onSelect && (
        <AnimatePresence>
          {selected && <CardModal card={selected} onClose={() => setSelected(null)} />}
        </AnimatePresence>
      )}
    </>
  );
}
