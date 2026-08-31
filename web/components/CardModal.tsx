"use client";
import { useEffect } from "react";
import { motion } from "framer-motion";
import { X, Heart, Bookmark, ExternalLink, FileMusic } from "lucide-react";
import type { FeedCard, Source } from "@/lib/types";
import { useCollection } from "@/lib/useCollection";
import { cleanInstrumentation } from "@/lib/format";

const SOURCE_LABEL: Record<Source, string> = {
  youtube: "YouTube",
  imslp: "IMSLP",
  musescore: "MuseScore",
};

const SAMPLE_COMMENTS = [
  { user: "pianoDreamer", text: "This arrangement is gorgeous 😍", when: "2d" },
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

export default function CardModal({ card, onClose }: { card: FeedCard; onClose: () => void }) {
  const likes = useCollection("scorekit:likes");
  const saves = useCollection("scorekit:saves");
  const liked = likes.has(card.id);
  const saved = saves.has(card.id);

  const title = card.title ?? card.piece?.title ?? "Untitled";
  const composer = card.piece?.composer ?? card.metadata?.composer;
  const m = card.metadata ?? {};
  const sheetLink =
    (m.sheet_music_links && m.sheet_music_links[0]) ||
    (card.source !== "youtube" ? card.url : undefined);
  // Only link the title when the "view score" button doesn't already open the same
  // URL — otherwise it's a redundant duplicate link (IMSLP/MuseScore case).
  const titleLinks = card.url !== sheetLink;

  // lock background scroll while open + close on Escape
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6">
      <motion.div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      />

      <motion.div
        layoutId={`card-${card.id}`}
        className="relative z-10 flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-3xl bg-[var(--surface)] ring-1 ring-[var(--border)] md:flex-row"
      >
        <button
          onClick={onClose}
          aria-label="Close"
          className="absolute right-3 top-3 z-20 rounded-full bg-black/55 p-2 text-white transition-colors hover:bg-black/80"
        >
          <X size={18} />
        </button>

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
            <img src={card.thumbnail_url} alt="" className="max-h-[86vh] w-full object-contain md:max-h-[90vh]" />
          ) : (
            <div className="flex aspect-[3/4] w-full max-h-[86vh] flex-col items-center justify-center gap-2 bg-gradient-to-br from-[var(--surface-2)] to-[#2b2b38] p-6 text-center">
              <FileMusic size={40} className="text-[var(--muted)]" />
              <p className="font-mono text-sm text-[var(--muted)]">
                {SOURCE_LABEL[card.source]} score{composer ? ` · ${composer}` : ""}
              </p>
            </div>
          )}
        </div>

        {/* info — right */}
        <motion.div
          className="flex w-full flex-col md:w-[40%]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.12 }}
        >
          <div className="flex-1 overflow-y-auto p-5">
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
            <button
              onClick={() => likes.toggle(card.id)}
              className={`flex flex-1 items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-sm font-semibold transition-colors ${
                liked ? "bg-[var(--accent)] text-white" : "bg-[var(--surface-2)] hover:bg-white/10"
              }`}
            >
              <Heart size={17} fill={liked ? "currentColor" : "none"} />
              {liked ? "Liked" : "Like"}
            </button>
            <button
              onClick={() => saves.toggle(card.id)}
              className={`flex flex-1 items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-sm font-semibold transition-colors ${
                saved ? "bg-[var(--accent-2)] text-black" : "bg-[var(--surface-2)] hover:bg-white/10"
              }`}
            >
              <Bookmark size={17} fill={saved ? "currentColor" : "none"} />
              {saved ? "Saved" : "Save"}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}
