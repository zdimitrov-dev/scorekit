"use client";
import { useMemo, useState } from "react";
import { AnimatePresence } from "framer-motion";
import { Search } from "lucide-react";
import type { FeedCard } from "@/lib/types";
import Feed from "./Feed";
import CardModal from "./CardModal";
import ScoresDrawer from "./ScoresDrawer";

export default function SearchFeed({ cards }: { cards: FeedCard[] }) {
  const [q, setQ] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selected, setSelected] = useState<FeedCard | null>(null);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return cards;
    return cards.filter((c) =>
      `${c.title ?? ""} ${c.author ?? ""} ${c.piece?.title ?? ""} ${c.piece?.composer ?? ""}`
        .toLowerCase()
        .includes(needle),
    );
  }, [q, cards]);

  const videos = filtered.filter((c) => c.source === "youtube");
  // scores keep relevance order; within equal match_score, show ones with a real
  // first-page thumbnail before the themed placeholders (nicer at the top).
  const scores = filtered
    .filter((c) => c.source === "imslp" || c.source === "musescore")
    .sort((a, b) => {
      const ms = (b.metadata?.match_score ?? 0) - (a.metadata?.match_score ?? 0);
      if (ms !== 0) return ms;
      return (b.thumbnail_url ? 1 : 0) - (a.thumbnail_url ? 1 : 0);
    });

  return (
    <div>
      {/* search bar (sticks below the top bar) */}
      <div className="sticky top-14 z-20 -mx-3 mb-4 bg-[var(--background)]/90 px-3 py-3 backdrop-blur sm:-mx-5 sm:px-5">
        <div className="relative">
          <Search
            size={18}
            className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[var(--muted)]"
          />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search pieces, composers, channels…"
            className="w-full rounded-full border border-[var(--border)] bg-[var(--surface)] py-3 pl-11 pr-4 text-sm outline-none transition-colors focus:border-white/25"
          />
        </div>
      </div>

      {/* videos — the centerpiece board; pushed left on large screens when the drawer is open */}
      <div className={`transition-[margin] duration-300 ${drawerOpen ? "lg:mr-[344px]" : ""}`}>
        <Feed
          cards={videos}
          onSelect={setSelected}
          emptyLabel={q ? `No videos for “${q}”.` : "Type to search."}
        />
      </div>

      {/* scores — IMSLP + MuseScore in a slide-out drawer */}
      <ScoresDrawer scores={scores} open={drawerOpen} setOpen={setDrawerOpen} onSelect={setSelected} />

      {/* shared expand modal for both the board and the drawer */}
      <AnimatePresence>
        {selected && <CardModal card={selected} onClose={() => setSelected(null)} />}
      </AnimatePresence>
    </div>
  );
}
