"use client";
import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import type { FeedCard } from "@/lib/types";
import Feed from "./Feed";

export default function SearchFeed({ cards }: { cards: FeedCard[] }) {
  const [q, setQ] = useState("");

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return cards;
    return cards.filter((c) =>
      `${c.title ?? ""} ${c.author ?? ""} ${c.piece?.title ?? ""} ${c.piece?.composer ?? ""}`
        .toLowerCase()
        .includes(needle),
    );
  }, [q, cards]);

  return (
    <div>
      <div className="sticky top-0 z-30 -mx-3 mb-4 bg-[var(--background)]/90 px-3 py-3 backdrop-blur sm:-mx-5 sm:px-5">
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
      <Feed cards={filtered} emptyLabel={q ? `No results for “${q}”.` : "Type to search."} />
    </div>
  );
}
