"use client";
import { AnimatePresence, motion } from "framer-motion";
import { FileMusic, X } from "lucide-react";
import type { FeedCard } from "@/lib/types";
import PieceCard from "./PieceCard";

/**
 * A one-column drawer of score cards (IMSLP + MuseScore) that pushes out from the
 * right. Toggled by an edge tab; on large screens it pushes the board (the parent
 * adds a right margin), on smaller screens it overlays with a backdrop. Not a route
 * change — purely in-page.
 */
export default function ScoresDrawer({
  scores,
  open,
  setOpen,
  onSelect,
}: {
  scores: FeedCard[];
  open: boolean;
  setOpen: (v: boolean) => void;
  onSelect: (c: FeedCard) => void;
}) {
  return (
    <>
      {/* edge tab (hidden while open) */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          aria-label="Open scores"
          className="fixed right-0 top-1/2 z-30 flex -translate-y-1/2 flex-col items-center gap-1.5 rounded-l-2xl bg-[var(--surface-2)] px-2.5 py-4 text-xs font-semibold ring-1 ring-[var(--border)] transition-colors hover:bg-white/10"
        >
          <FileMusic size={18} />
          <span className="rotate-180 tracking-wide [writing-mode:vertical-rl]">Scores</span>
          <span className="rounded-full bg-[var(--accent-2)] px-1.5 py-0.5 text-[10px] font-bold text-black">
            {scores.length}
          </span>
        </button>
      )}

      {/* backdrop on smaller screens */}
      <AnimatePresence>
        {open && (
          <motion.div
            className="fixed inset-0 z-30 bg-black/50 lg:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* the drawer */}
      <AnimatePresence>
        {open && (
          <motion.aside
            key="scores-drawer"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 320, damping: 34 }}
            className="fixed bottom-0 right-0 top-14 z-30 flex w-[344px] max-w-[88vw] flex-col border-l border-[var(--border)] bg-[var(--surface)]"
          >
            <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
              <div className="flex items-center gap-2">
                <FileMusic size={16} className="text-[var(--muted)]" />
                <h2 className="text-sm font-semibold">
                  Scores <span className="text-[var(--muted)]">· {scores.length}</span>
                </h2>
              </div>
              <button
                onClick={() => setOpen(false)}
                aria-label="Close scores"
                className="rounded-full p-1.5 transition-colors hover:bg-white/10"
              >
                <X size={18} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-3 pb-24">
              {scores.length === 0 ? (
                <p className="py-16 text-center text-sm text-[var(--muted)]">No scores found.</p>
              ) : (
                scores.map((card, i) => (
                  <PieceCard key={card.id} card={card} index={i} onSelect={onSelect} compact />
                ))
              )}
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  );
}
