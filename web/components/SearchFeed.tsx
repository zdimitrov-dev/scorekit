"use client";
import { useState } from "react";
import { AnimatePresence } from "framer-motion";
import { Search, Loader2 } from "lucide-react";
import type { FeedCard } from "@/lib/types";
import Feed from "./Feed";
import CardModal from "./CardModal";
import ScoresDrawer from "./ScoresDrawer";

const SORTS = [
  { key: "match", label: "Best match" },
  { key: "views", label: "Most viewed" },
  { key: "newest", label: "Newest" },
] as const;
type SortKey = (typeof SORTS)[number]["key"];

function sortVideos(cards: FeedCard[], sort: SortKey): FeedCard[] {
  const ms = (c: FeedCard) => c.metadata?.match_score ?? 0;
  const vc = (c: FeedCard) => c.metadata?.view_count ?? 0;
  const pub = (c: FeedCard) => c.metadata?.published_at ?? "";
  const arr = [...cards];
  if (sort === "views") arr.sort((a, b) => vc(b) - vc(a) || ms(b) - ms(a));
  else if (sort === "newest") arr.sort((a, b) => pub(b).localeCompare(pub(a)));
  else arr.sort((a, b) => ms(b) - ms(a) || vc(b) - vc(a));
  return arr;
}

export default function SearchFeed() {
  const [q, setQ] = useState("");
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<FeedCard[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selected, setSelected] = useState<FeedCard | null>(null);
  const [sort, setSort] = useState<SortKey>("match");

  async function runSearch(e: React.FormEvent) {
    e.preventDefault();
    const query = q.trim();
    if (!query || loading) return;
    setLoading(true);
    setError(null);
    setSubmitted(query);
    setDrawerOpen(false);
    setResults([]);
    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
      if (!res.ok || !res.body) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Search failed.");
      }
      // read the NDJSON stream and roll cards out per batch as they arrive
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let nl: number;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          try {
            const msg = JSON.parse(line) as { cards?: FeedCard[] };
            if (Array.isArray(msg.cards)) setResults((prev) => [...prev, ...msg.cards!]);
          } catch {
            /* ignore a partial line */
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed.");
    } finally {
      setLoading(false);
    }
  }

  const videos = sortVideos(
    results.filter((c) => c.source === "youtube"),
    sort,
  );
  const scores = results
    .filter((c) => c.source === "imslp" || c.source === "musescore")
    .sort((a, b) => {
      const ms = (b.metadata?.match_score ?? 0) - (a.metadata?.match_score ?? 0);
      if (ms !== 0) return ms;
      return (b.thumbnail_url ? 1 : 0) - (a.thumbnail_url ? 1 : 0);
    });

  return (
    <div>
      <form
        onSubmit={runSearch}
        className="sticky top-14 z-20 -mx-3 mb-4 bg-[var(--background)]/90 px-3 py-3 backdrop-blur sm:-mx-5 sm:px-5"
      >
        <div className="relative">
          <Search
            size={18}
            className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[var(--muted)]"
          />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search a piece — e.g. “Für Elise” or “Chopin Nocturne”"
            className="w-full rounded-full border border-[var(--border)] bg-[var(--surface)] py-3 pl-11 pr-24 text-sm outline-none transition-colors focus:border-white/25"
          />
          <button
            type="submit"
            disabled={loading || !q.trim()}
            className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-full bg-[var(--accent)] px-4 py-1.5 text-sm font-semibold text-white transition-opacity disabled:opacity-40"
          >
            Search
          </button>
        </div>
      </form>

      {submitted === null ? (
        <div className="mx-auto max-w-sm px-6 py-24 text-center text-[var(--muted)]">
          <Search size={32} className="mx-auto mb-3 opacity-50" />
          <p className="text-sm">
            Search for a piece or composer to build a board of videos and scores.
          </p>
        </div>
      ) : error && results.length === 0 ? (
        <p className="py-24 text-center text-sm text-[var(--muted)]">{error}</p>
      ) : loading && results.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-24 text-[var(--muted)]">
          <Loader2 size={28} className="animate-spin" />
          <p className="text-sm">Searching “{submitted}”…</p>
        </div>
      ) : results.length === 0 ? (
        <p className="py-24 text-center text-sm text-[var(--muted)]">No results for “{submitted}”.</p>
      ) : (
        <>
          <div className={`transition-[margin] duration-300 ${drawerOpen ? "lg:mr-[344px]" : ""}`}>
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <span className="text-xs text-[var(--muted)]">Sort</span>
              {SORTS.map((s) => (
                <button
                  key={s.key}
                  onClick={() => setSort(s.key)}
                  className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                    sort === s.key
                      ? "bg-[var(--foreground)] text-[var(--background)]"
                      : "bg-[var(--surface-2)] text-[var(--muted)] hover:text-[var(--foreground)]"
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
            <Feed key={sort} cards={videos} onSelect={setSelected} emptyLabel="No videos found." />
            {loading && (
              <div className="mt-6 flex items-center justify-center gap-2 text-xs text-[var(--muted)]">
                <Loader2 size={15} className="animate-spin" />
                finding more…
              </div>
            )}
          </div>
          {scores.length > 0 && (
            <ScoresDrawer
              scores={scores}
              open={drawerOpen}
              setOpen={setDrawerOpen}
              onSelect={setSelected}
            />
          )}
        </>
      )}

      <AnimatePresence>
        {selected && <CardModal card={selected} onClose={() => setSelected(null)} />}
      </AnimatePresence>
    </div>
  );
}
