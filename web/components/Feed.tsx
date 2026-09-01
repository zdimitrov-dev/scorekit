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

/**
 * `onNext` / `onPrev` for stepping through a list from inside the modal. Returns only the
 * directions that exist, so the modal doesn't render an arrow that goes nowhere at either
 * end of the feed.
 */
export function step(
  list: FeedCard[],
  current: FeedCard,
  select: (c: FeedCard) => void,
): { onNext?: () => void; onPrev?: () => void } {
  const i = list.findIndex((c) => c.id === current.id);
  if (i < 0) return {};
  return {
    onPrev: i > 0 ? () => select(list[i - 1]) : undefined,
    onNext: i < list.length - 1 ? () => select(list[i + 1]) : undefined,
  };
}

function useColumnCount(maxColumns: number): number {
  const [cols, setCols] = useState(2);
  useEffect(() => {
    const queries = BREAKPOINTS.map(([q, n]) => [window.matchMedia(q), n] as const);
    // `maxColumns` caps the widest layout: the home board reads better with fewer,
    // larger cards than with everything the viewport could technically fit.
    const update = () =>
      setCols(Math.min(maxColumns, queries.find(([m]) => m.matches)?.[1] ?? 2));
    update();
    queries.forEach(([m]) => m.addEventListener("change", update));
    return () => queries.forEach(([m]) => m.removeEventListener("change", update));
  }, [maxColumns]);
  return cols;
}

export default function Feed({
  cards,
  emptyLabel,
  onSelect,
  maxColumns = 4,
}: {
  cards: FeedCard[];
  emptyLabel?: string;
  /** Upper bound on columns at the widest breakpoint. */
  maxColumns?: number;
  // when provided, selection is delegated to the parent (which owns the modal);
  // otherwise Feed manages its own modal.
  onSelect?: (c: FeedCard) => void;
}) {
  const [visible, setVisible] = useState(PAGE);
  const [selected, setSelected] = useState<FeedCard | null>(null);
  const [columns, setColumns] = useState<FeedCard[][]>([]);
  const colRefs = useRef<(HTMLDivElement | null)[]>([]);
  const cols = useColumnCount(maxColumns);
  const select = onSelect ?? setSelected;

  // Identify the list by its contents, never by array identity. Callers build these
  // arrays during render (`sortVideos(...)`, a filter), so the reference changes on every
  // parent re-render — including one caused by opening a card. Keying the reset on
  // identity therefore wiped the board on click and unmounted the card mid-transition,
  // which is why the modal never appeared.
  const signature = useMemo(() => cards.map((c) => c.id).join("|"), [cards]);

  // Rank in the ordered feed, kept as a lookup so rendering stays linear — the columns
  // interleave the list, so a card's column position is not its feed position.
  const rank = useMemo(() => new Map(cards.map((c, i) => [c.id, i])), [cards]);

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
      //
      // On a fresh list the columns are treated as empty rather than measured: the reset
      // has not painted yet, so the DOM still holds the *previous* board and its tall
      // columns would push the new cards into whichever columns the old list happened to
      // leave short — a two-result search rendered into columns 3 and 4 with 1 and 2 blank.
      const next: FeedCard[][] = Array.from({ length: cols }, (_, i) => [...(prev[i] ?? [])]);
      const heights =
        placed === 0 ? next.map(() => 0) : next.map((_, i) => colRefs.current[i]?.offsetHeight ?? 0);
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
                position={rank.get(card.id)}
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
          {selected && (
            <CardModal
              card={selected}
              onClose={() => setSelected(null)}
              onSelectSimilar={setSelected}
              {...step(cards, selected, setSelected)}
            />
          )}
        </AnimatePresence>
      )}
    </>
  );
}
