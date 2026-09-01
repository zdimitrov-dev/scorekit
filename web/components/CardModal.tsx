"use client";
import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import {
  X, Heart, Bookmark, ExternalLink, FileMusic, ChevronLeft, ChevronRight,
} from "lucide-react";
import type { FeedCard, Source } from "@/lib/types";
import { useCollection } from "@/lib/useCollection";
import { cleanInstrumentation } from "@/lib/format";
import { track, trackNow } from "@/lib/track";
import { refreshFeed } from "@/lib/feedCache";
import SimilarStrip from "./SimilarStrip";

const SOURCE_LABEL: Record<Source, string> = {
  youtube: "YouTube",
  imslp: "IMSLP",
  musescore: "MuseScore",
};

// Below this, an open is a mis-click rather than a view, and not training data.
const MIN_VIEW_MS = 400;

const SAMPLE_COMMENTS = [
  { user: "pianoDreamer", text: "This arrangement is gorgeous.", when: "2d" },
  { user: "chopin_fan", text: "Finally a version I can actually play!", when: "5d" },
  { user: "keys_and_tea", text: "The left hand at 1:12 is so satisfying.", when: "1w" },
];

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-[var(--surface-2)] px-2.5 py-1 text-xs text-[var(--muted)]">
      {children}
    </span>
  );
}

export default function CardModal({
  card,
  onClose,
  onNext,
  onPrev,
  onSelectSimilar,
}: {
  card: FeedCard;
  onClose: () => void;
  // Supplied by whichever component owns the list, so the modal can move through it
  // without the user closing and reopening cards one at a time.
  onNext?: () => void;
  onPrev?: () => void;
  /** Open one of the "more like this" cards in place. */
  onSelectSimilar?: (c: FeedCard) => void;
}) {
  const likes = useCollection("scorekit:likes");
  const saves = useCollection("scorekit:saves");
  const liked = likes.has(card.id);
  const saved = saves.has(card.id);
  const openedAt = useRef(Date.now());

  // How long a card was held open is the strongest engagement signal the feed produces —
  // stronger than a like, which most people rarely click. Logged when moving on, so
  // stepping through cards builds the training set as a side effect of normal use.
  useEffect(() => {
    openedAt.current = Date.now();
    const id = card.id;
    const pieceId = card.piece?.id;
    return () => {
      const dwell = Date.now() - openedAt.current;
      // Sub-threshold opens aren't views: a mis-click, or React's development
      // double-invoked effect, which was writing 1ms rows into the training data.
      if (dwell < MIN_VIEW_MS) return;
      track({ action: "click", card_id: id, piece_id: pieceId, dwell_ms: dwell });
    };
  }, [card.id, card.piece?.id]);

  function toggleLike() {
    // trackNow, not track: a like is a user action, and the batch queue swallows
    // failures. See track.ts.
    if (!liked) void trackNow({ action: "like", card_id: card.id, piece_id: card.piece?.id });
    likes.toggle(card.id);
    queueFeedRebuild();
  }

  function toggleSave() {
    if (!saved) void trackNow({ action: "save", card_id: card.id, piece_id: card.piece?.id });
    saves.toggle(card.id);
    queueFeedRebuild();
  }

  /** Start rebuilding the home ranking now, so it is ready before Home is next opened.
   *  Deferred a beat because `toggle` writes localStorage during the state update, and the
   *  rebuild reads it — running immediately would rank against the previous signals. */
  function queueFeedRebuild() {
    setTimeout(() => void refreshFeed(), 50);
  }

  const title = card.title ?? card.piece?.title ?? "Untitled";
  const composer = card.piece?.composer ?? card.metadata?.composer;
  const m = card.metadata ?? {};
  const sheetLink =
    (m.sheet_music_links && m.sheet_music_links[0]) ||
    (card.source !== "youtube" ? card.url : undefined);
  // Only link the title when the "view score" button doesn't already open the same
  // URL — otherwise it's a redundant duplicate link (IMSLP/MuseScore case).
  const titleLinks = card.url !== sheetLink;

  // lock background scroll while open; Escape closes, arrows move through the feed
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      // ignore arrows while typing, so the comment box keeps working
      if ((e.target as HTMLElement)?.tagName === "INPUT") return;
      if (e.key === "ArrowRight") onNext?.();
      if (e.key === "ArrowLeft") onPrev?.();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose, onNext, onPrev]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6">
      <motion.div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      />

      {/* Step through the feed without closing. Sits above the backdrop but outside the
          card, so the arrows stay put while the card itself animates between pieces. */}
      {onPrev && (
        <button
          onClick={onPrev}
          aria-label="Previous card"
          className="absolute left-1 z-20 hidden rounded-full bg-black/55 p-2.5 text-white transition-colors hover:bg-black/85 sm:block sm:left-3"
        >
          <ChevronLeft size={22} />
        </button>
      )}
      {onNext && (
        <button
          onClick={onNext}
          aria-label="Next card"
          className="absolute right-1 z-20 hidden rounded-full bg-black/55 p-2.5 text-white transition-colors hover:bg-black/85 sm:block sm:right-3"
        >
          <ChevronRight size={22} />
        </button>
      )}

      <motion.div
        layoutId={`card-${card.id}`}
        className="relative z-10 flex max-h-[90vh] w-full max-w-5xl flex-col overflow-y-auto overscroll-contain rounded-3xl bg-[var(--surface)] ring-1 ring-[var(--border)]"
      >
        <button
          onClick={onClose}
          aria-label="Close"
          className="absolute right-3 top-3 z-20 rounded-full bg-black/55 p-2 text-white transition-colors hover:bg-black/80"
        >
          <X size={18} />
        </button>

        <div className="flex flex-col md:flex-row">
        {/* media — left */}
        <div className="flex w-full shrink-0 items-center justify-center bg-black md:w-[60%]">
          {card.source === "youtube" ? (
            <div className="aspect-video w-full">
              <iframe
                className="h-full w-full"
                src={`https://www.youtube.com/embed/${card.external_id}`}
                title={title}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            </div>
          ) : card.thumbnail_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={card.thumbnail_url} alt="" className="max-h-[70vh] w-full object-contain" />
          ) : (
            <div className="flex aspect-[3/4] w-full max-h-[70vh] flex-col items-center justify-center gap-2 bg-gradient-to-br from-[var(--surface-2)] to-[#2b2b38] p-6 text-center">
              <FileMusic size={40} className="text-[var(--muted)]" />
              <p className="font-mono text-sm text-[var(--muted)]">
                {SOURCE_LABEL[card.source]} score{composer ? ` · ${composer}` : ""}
              </p>
            </div>
          )}
        </div>

        {/* info — right.
            Plain div, not an animated one: it used to fade in, but the modal's height now
            changes when "more like this" loads, which restarted the fade and left the
            panel stranded at ~9% opacity — effectively invisible. */}
        <div className="flex w-full flex-col md:w-[40%]">
          <div className="flex-1 p-5">
            {titleLinks ? (
              <a
                href={card.url}
                target="_blank"
                rel="noopener noreferrer"
                className="group inline-flex items-start gap-1.5 text-lg font-semibold leading-snug hover:text-[var(--accent)]"
              >
                <span>{title}</span>
                <ExternalLink size={15} className="mt-1.5 shrink-0 opacity-60 group-hover:opacity-100" />
              </a>
            ) : (
              <h2 className="text-lg font-semibold leading-snug">{title}</h2>
            )}
            {composer && <p className="mt-1 text-sm text-[var(--muted)]">{composer}</p>}
            {card.author && <p className="mt-0.5 text-sm text-[var(--muted)]">{card.author}</p>}

            <div className="mt-3 flex flex-wrap gap-1.5">
              <Badge>{SOURCE_LABEL[card.source]}</Badge>
              {card.kind && <Badge>{card.kind}</Badge>}
              {cleanInstrumentation(m.instrumentation, 60) && (
                <Badge>{cleanInstrumentation(m.instrumentation, 60)}</Badge>
              )}
              {m.piece_style && <Badge>{m.piece_style}</Badge>}
              {m.is_public_domain && <Badge>public domain</Badge>}
            </div>

            {sheetLink && (
              <a
                href={sheetLink}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-4 inline-flex items-center gap-2 rounded-xl bg-[var(--surface-2)] px-3.5 py-2 text-sm font-medium transition-colors hover:bg-white/10"
              >
                <FileMusic size={16} />
                {card.source === "youtube" ? "Sheet music link" : `View score on ${SOURCE_LABEL[card.source]}`}
              </a>
            )}

            {/* comments (placeholder) */}
            <div className="mt-6">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
                Comments
              </h3>
              <ul className="mt-3 space-y-3">
                {SAMPLE_COMMENTS.map((c) => (
                  <li key={c.user} className="flex gap-2.5">
                    <div className="mt-0.5 h-7 w-7 shrink-0 rounded-full bg-gradient-to-br from-[var(--accent)] to-[var(--accent-2)]" />
                    <div>
                      <p className="text-sm">
                        <span className="font-medium">{c.user}</span>{" "}
                        <span className="text-xs text-[var(--muted)]">· {c.when}</span>
                      </p>
                      <p className="text-sm text-[var(--foreground)]/90">{c.text}</p>
                    </div>
                  </li>
                ))}
              </ul>
              <input
                disabled
                placeholder="Add a comment… (coming soon)"
                className="mt-4 w-full cursor-not-allowed rounded-xl border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--muted)] placeholder:text-[var(--muted)]"
              />
            </div>
          </div>

          {/* actions */}
          <div className="flex items-center gap-2 border-t border-[var(--border)] p-4">
            {onPrev && (
              <button
                onClick={onPrev}
                aria-label="Previous card"
                className="rounded-xl bg-[var(--surface-2)] p-2.5 transition-colors hover:bg-white/10 sm:hidden"
              >
                <ChevronLeft size={17} />
              </button>
            )}
            <button
              onClick={toggleLike}
              className={`flex flex-1 items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-sm font-semibold transition-colors ${
                liked ? "bg-[var(--accent)] text-white" : "bg-[var(--surface-2)] hover:bg-white/10"
              }`}
            >
              <Heart size={17} fill={liked ? "currentColor" : "none"} />
              {liked ? "Liked" : "Like"}
            </button>
            <button
              onClick={toggleSave}
              className={`flex flex-1 items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-sm font-semibold transition-colors ${
                saved ? "bg-[var(--accent-2)] text-black" : "bg-[var(--surface-2)] hover:bg-white/10"
              }`}
            >
              <Bookmark size={17} fill={saved ? "currentColor" : "none"} />
              {saved ? "Saved" : "Save"}
            </button>
            {onNext && (
              <button
                onClick={onNext}
                aria-label="Next card"
                className="rounded-xl bg-[var(--surface-2)] p-2.5 transition-colors hover:bg-white/10 sm:hidden"
              >
                <ChevronRight size={17} />
              </button>
            )}
          </div>
        </div>
        </div>

        {/* cards like this one — ranked against this card, not against the viewer */}
        <SimilarStrip card={card} onSelect={onSelectSimilar ?? (() => {})} />
      </motion.div>
    </div>
  );
}
