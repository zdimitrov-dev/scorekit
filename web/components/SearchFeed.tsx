"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence } from "framer-motion";
import { Search, Loader2, Clock } from "lucide-react";
import type { FeedCard } from "@/lib/types";
import Feed, { step } from "./Feed";
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
  // the source's own relevance position, kept at ingest
  const rank = (c: FeedCard) => c.metadata?.rank ?? Number.MAX_SAFE_INTEGER;
  const arr = [...cards];
  if (sort === "views") arr.sort((a, b) => vc(b) - vc(a) || ms(b) - ms(a));
  else if (sort === "newest") arr.sort((a, b) => pub(b).localeCompare(pub(a)));
  // Ties break on the source's relevance rank, NOT on views: tying back to view
  // count made "Best match" and "Most viewed" render an identical board whenever
  // scores clustered, which looked like the toggle was broken.
  else arr.sort((a, b) => ms(b) - ms(a) || rank(a) - rank(b));
  return arr;
}

const RECENT_KEY = "scorekit:recent-searches";
const RECENT_MAX = 4;

function loadRecent(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((s) => typeof s === "string").slice(0, RECENT_MAX) : [];
  } catch {
    return []; // private mode / blocked storage — recents are a convenience, not state
  }
}

function saveRecent(query: string, prev: string[]): string[] {
  const next = [query, ...prev.filter((s) => s.toLowerCase() !== query.toLowerCase())].slice(
    0,
    RECENT_MAX,
  );
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    /* ignore */
  }
  return next;
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
  const [recent, setRecent] = useState<string[]>([]);
  const [recentOpen, setRecentOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  // read on mount, not during render: localStorage doesn't exist on the server
  useEffect(() => setRecent(loadRecent()), []);

  useEffect(() => {
    if (!recentOpen) return;
    function onDown(e: MouseEvent) {
      if (!boxRef.current?.contains(e.target as Node)) setRecentOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [recentOpen]);

  async function search(raw: string) {
    const query = raw.trim();
    if (!query || loading) return;
    setQ(query);
    setRecentOpen(false);
    setRecent((prev) => saveRecent(query, prev));
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

  // Memoized so opening a card — which re-renders this component — doesn't hand Feed and
  // ScoresDrawer brand-new arrays and make them rebuild their layout from scratch.
  const videos = useMemo(
    () => sortVideos(results.filter((c) => c.source === "youtube"), sort),
    [results, sort],
  );
  const scores = useMemo(
    () =>
      results
        .filter((c) => c.source === "imslp" || c.source === "musescore")
        .sort((a, b) => {
          const ms = (b.metadata?.match_score ?? 0) - (a.metadata?.match_score ?? 0);
          if (ms !== 0) return ms;
          return (b.thumbnail_url ? 1 : 0) - (a.thumbnail_url ? 1 : 0);
        }),
    [results],
  );

  return (
    <div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void search(q);
        }}
        className="sticky top-14 z-20 -mx-3 mb-4 bg-[var(--background)]/90 px-3 py-3 backdrop-blur sm:-mx-5 sm:px-5"
      >
        <div ref={boxRef} className="relative">
          <Search
            size={18}
            className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[var(--muted)]"
          />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            // Click, not focus. The input autofocuses on mount, so opening on focus put
            // the panel over the top row of results on every visit to /search and
            // swallowed clicks meant for those cards. Click also covers the case focus
            // would miss: after a search the input still holds focus, so clicking back
            // into it fires no focus event at all.
            onClick={() => setRecentOpen(true)}
            onKeyDown={(e) => e.key === "Escape" && setRecentOpen(false)}
            placeholder="Search a piece, e.g. “Für Elise” or “Chopin Nocturne”"
            className="w-full rounded-full border border-[var(--border)] bg-[var(--surface)] py-3 pl-11 pr-24 text-sm outline-none transition-colors focus:border-white/25"
          />
          <button
            type="submit"
            disabled={loading || !q.trim()}
            className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-full bg-[var(--accent)] px-4 py-1.5 text-sm font-semibold text-white transition-opacity disabled:opacity-40"
          >
            Search
          </button>

          {recentOpen && recent.length > 0 && (
            <div className="absolute left-0 right-0 top-full z-30 mt-2 overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] py-1 shadow-xl shadow-black/40">
              <p className="px-4 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-[var(--muted)]">
                Recent
              </p>
              {recent.map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => void search(r)}
                  className="flex w-full items-center gap-2.5 px-4 py-2 text-left text-sm transition-colors hover:bg-[var(--surface-2)]"
                >
                  <Clock size={14} className="shrink-0 text-[var(--muted)]" />
                  <span className="truncate">{r}</span>
                </button>
              ))}
            </div>
          )}
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
        {selected && (
          <CardModal
            card={selected}
            onClose={() => setSelected(null)}
            onSelectSimilar={setSelected}
            // step within the list the card came from: the board and the scores drawer
            // are separate runs, and jumping between them would be disorienting
            {...step(selected.source === "youtube" ? videos : scores, selected, setSelected)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
