"use client";
import { useState } from "react";
import { AnimatePresence } from "framer-motion";
import type { FeedCard } from "@/lib/types";
import PieceCard from "./PieceCard";
import CardModal from "./CardModal";

const PAGE = 24;

export default function Feed({ cards, emptyLabel }: { cards: FeedCard[]; emptyLabel?: string }) {
  const [visible, setVisible] = useState(PAGE);
  const [selected, setSelected] = useState<FeedCard | null>(null);

  if (cards.length === 0) {
    return <p className="py-24 text-center text-[var(--muted)]">{emptyLabel ?? "No cards yet."}</p>;
  }

  const shown = cards.slice(0, visible);

  return (
    <>
      <div className="columns-2 gap-3 md:columns-3 xl:columns-4">
        {shown.map((card, i) => (
          <PieceCard key={card.id} card={card} index={i} onSelect={setSelected} />
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

      <AnimatePresence>
        {selected && <CardModal card={selected} onClose={() => setSelected(null)} />}
      </AnimatePresence>
    </>
  );
}
