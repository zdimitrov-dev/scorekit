"use client";
import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import type { FeedCard, Source } from "@/lib/types";
import { cleanInstrumentation } from "@/lib/format";
import { track } from "@/lib/track";

// A card must be this visible, for this long, before it counts as seen. Impressions are
// the recommender's negative examples, so a card that merely passed through the viewport
// during a fast scroll must not be recorded as something the user looked at and rejected.
const SEEN_RATIO = 0.5;
const SEEN_MS = 900;
// A card that never leaves the viewport is recorded after this long anyway. Without it the
// cards at the top of the feed — the ones most reliably looked at — were the ones least
// likely to be logged, because nothing ever triggered the write.
const SETTLED_MS = 8000;

// A remote thumbnail smaller than this isn't a usable preview — it's a favicon, a
// tracking pixel, or a promo strip that slipped through. We render our own titled
// tile instead, which is better than a stamp-sized image in a masonry column.
const MIN_THUMB_W = 160;
const MIN_THUMB_H = 120;

const SOURCE_STYLES: Record<Source, { label: string; cls: string }> = {
  youtube: { label: "YouTube", cls: "bg-red-500/90" },
  imslp: { label: "IMSLP", cls: "bg-emerald-500/90" },
  musescore: { label: "MuseScore", cls: "bg-sky-500/90" },
};

// Every YouTube thumbnail is 16:9, so a board of them renders as a perfectly even grid
// — measured: every card exactly 272px tall. Masonry needs varied heights to read as
// masonry, so video cards are cropped to one of a few shapes, chosen deterministically
// from the card id (stable across renders, so nothing jumps on re-render).
//
// Only video cards. Score images are portrait pages of sheet music and already vary;
// forcing them into a 16:9 crop would slice the music off.
const VIDEO_ASPECTS = ["16 / 9", "3 / 2", "4 / 3", "16 / 9", "5 / 4"];

function aspectFor(id: string): string {
  let s = 0;
  for (let i = 0; i < id.length; i++) s += id.charCodeAt(i);
  return VIDEO_ASPECTS[s % VIDEO_ASPECTS.length];
}

const PH_HEIGHTS = [180, 210, 240, 270, 200];
const PH_HEIGHTS_COMPACT = [128, 146, 164, 138, 154];
function phHeight(id: string, compact = false) {
  const set = compact ? PH_HEIGHTS_COMPACT : PH_HEIGHTS;
  let s = 0;
  for (let i = 0; i < id.length; i++) s += id.charCodeAt(i);
  return set[s % set.length];
}

export function fmtDuration(sec?: number): string | null {
  if (!sec) return null;
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

export default function PieceCard({
  card,
  index,
  position,
  onSelect,
  compact = false,
  track: shouldTrack = true,
}: {
  card: FeedCard;
  /** Position within its own column — staggers the entry animation only. */
  index: number;
  /** Rank in the feed as a whole, logged for position-bias correction. Distinct from
   *  `index`, which is per-column and would make every card look like rank 0-5. */
  position?: number;
  onSelect: (c: FeedCard) => void;
  compact?: boolean;
  /** Log impressions for this card. Off inside "more like this": browsing one card's
   *  neighbours is exploring, not rejecting, and would otherwise record a dozen
   *  "not interested" votes every time a card is opened. */
  track?: boolean;
}) {
  // Some sources hand us a dead or unusably small image (MuseScore's CDN 403s on
  // hotlinked assets, for one), so the tile is a runtime fallback, not just a
  // "no thumbnail_url" branch.
  const [thumbOk, setThumbOk] = useState(true);
  const ref = useRef<HTMLDivElement>(null);

  // Log the card as seen, with how long it actually stayed on screen.
  //
  // Recorded when it *leaves* the viewport, not when it first qualifies. Logging at the
  // threshold made every impression report the same ~900ms and the dwell column carried no
  // information at all — yet dwell is the whole point here: it separates a card someone
  // lingered on from one they scrolled straight past, even though both are negatives.
  useEffect(() => {
    const el = ref.current;
    if (!shouldTrack || !el || typeof IntersectionObserver === "undefined") return;
    const id = card.id;
    const pieceId = card.piece?.id;
    let enteredAt: number | null = null;
    let visibleMs = 0;
    let logged = false;

    const record = () => {
      if (enteredAt !== null) {
        visibleMs += Date.now() - enteredAt;
        enteredAt = null;
      }
      if (!logged && visibleMs >= SEEN_MS) {
        logged = true;
        track({
          action: "seen",
          card_id: id,
          piece_id: pieceId,
          feed_position: position,
          dwell_ms: visibleMs,
        });
      }
    };

    let settle: ReturnType<typeof setTimeout> | null = null;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          enteredAt ??= Date.now();
          settle ??= setTimeout(record, SETTLED_MS);
        } else {
          if (settle) clearTimeout(settle);
          settle = null;
          record();
        }
      },
      { threshold: SEEN_RATIO },
    );
    observer.observe(el);

    // Cards still on screen when the tab is hidden are recorded on a best effort: the
    // tracker's own flush may already have run, in which case that last screenful is
    // lost. Cheap to accept — normal scrolling records everything through the observer.
    const onHide = () => document.visibilityState === "hidden" && record();
    document.addEventListener("visibilitychange", onHide);

    return () => {
      if (settle) clearTimeout(settle);
      document.removeEventListener("visibilitychange", onHide);
      observer.disconnect();
      record();
    };
  }, [card.id, card.piece?.id, position, shouldTrack]);

  const src = SOURCE_STYLES[card.source];
  const title = card.title ?? card.piece?.title ?? "Untitled";
  const showThumb = Boolean(card.thumbnail_url) && thumbOk;
  const duration = fmtDuration(card.metadata?.duration_seconds);
  const chips = [
    cleanInstrumentation(card.metadata?.instrumentation),
    card.metadata?.piece_style,
    card.metadata?.year,
    card.metadata?.is_public_domain ? "Public domain" : null,
  ].filter(Boolean) as string[];

  return (
    <motion.div
      ref={ref}
      layoutId={`card-${card.id}`}
      role="button"
      tabIndex={0}
      onClick={() => onSelect(card)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(card);
        }
      }}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: Math.min(index, 14) * 0.025 }}
      className="group relative mb-3 block w-full cursor-pointer overflow-hidden rounded-2xl bg-[var(--surface)] break-inside-avoid ring-1 ring-[var(--border)] transition-shadow hover:shadow-xl hover:shadow-black/40 hover:ring-white/20"
    >
      {showThumb ? (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={card.thumbnail_url!}
            alt=""
            loading="lazy"
            onError={() => setThumbOk(false)}
            onLoad={(e) => {
              const img = e.currentTarget;
              if (img.naturalWidth < MIN_THUMB_W || img.naturalHeight < MIN_THUMB_H) {
                setThumbOk(false);
              }
            }}
            style={
              card.source === "youtube" && !compact
                ? { aspectRatio: aspectFor(card.id) }
                : undefined
            }
            className={`w-full object-cover ${compact ? "max-h-52" : ""}`}
          />
          {/* hover: darken + title */}
          <div className="pointer-events-none absolute inset-0 flex flex-col justify-end bg-gradient-to-t from-black/85 via-black/15 to-transparent p-3 opacity-0 transition-opacity duration-100 ease-out group-hover:opacity-100">
            <p className="line-clamp-3 text-sm font-semibold text-white">{title}</p>
            {card.author && <p className="mt-1 text-xs text-white/70">{card.author}</p>}
          </div>
        </>
      ) : (
        // themed score tile for cards without a first-page thumbnail
        // (pt-9 clears the absolute source badge in the top-left)
        <div
          style={{ minHeight: phHeight(card.id, compact) }}
          className="flex w-full flex-col gap-2.5 bg-gradient-to-br from-[#20202b] to-[#2c2c3b] p-4 pt-9"
        >
          <div className="flex-1">
            {card.author ?? card.piece?.composer ? (
              <>
                <p className="line-clamp-2 text-sm font-semibold">
                  {card.author ?? card.piece?.composer}
                </p>
                <p className="mt-0.5 line-clamp-3 text-xs text-[var(--muted)]">{title}</p>
              </>
            ) : (
              <p className="line-clamp-4 text-sm font-semibold">{title}</p>
            )}
          </div>
          {chips.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {chips.map((ch) => (
                <span
                  key={ch}
                  className="rounded-full bg-black/25 px-2 py-0.5 text-[10px] text-[var(--muted)]"
                >
                  {ch}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      <span
        className={`absolute left-2 top-2 rounded-full px-2 py-0.5 text-[10px] font-semibold text-white ${src.cls}`}
      >
        {src.label}
      </span>
      {duration && (
        <span className="absolute bottom-2 right-2 rounded bg-black/75 px-1.5 py-0.5 text-[10px] font-medium text-white">
          {duration}
        </span>
      )}
    </motion.div>
  );
}
