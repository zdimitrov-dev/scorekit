"use client";
import { motion } from "framer-motion";
import { FileMusic } from "lucide-react";
import type { FeedCard, Source } from "@/lib/types";

const SOURCE_STYLES: Record<Source, { label: string; cls: string }> = {
  youtube: { label: "YouTube", cls: "bg-red-500/90" },
  imslp: { label: "IMSLP", cls: "bg-emerald-500/90" },
  musescore: { label: "MuseScore", cls: "bg-sky-500/90" },
};

const PH_HEIGHTS = [180, 210, 240, 270, 200];
function phHeight(id: string) {
  let s = 0;
  for (let i = 0; i < id.length; i++) s += id.charCodeAt(i);
  return PH_HEIGHTS[s % PH_HEIGHTS.length];
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
  onSelect,
}: {
  card: FeedCard;
  index: number;
  onSelect: (c: FeedCard) => void;
}) {
  const src = SOURCE_STYLES[card.source];
  const title = card.title ?? card.piece?.title ?? "Untitled";
  const duration = fmtDuration(card.metadata?.duration_seconds);
  const chips = [
    card.metadata?.instrumentation,
    card.metadata?.piece_style,
    card.metadata?.year,
    card.metadata?.is_public_domain ? "Public domain" : null,
  ].filter(Boolean) as string[];

  return (
    <motion.div
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
      {card.thumbnail_url ? (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={card.thumbnail_url} alt="" loading="lazy" className="w-full object-cover" />
          {/* hover: darken + title */}
          <div className="pointer-events-none absolute inset-0 flex flex-col justify-end bg-gradient-to-t from-black/85 via-black/15 to-transparent p-3 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
            <p className="line-clamp-3 text-sm font-semibold text-white">{title}</p>
            {card.author && <p className="mt-1 text-xs text-white/70">{card.author}</p>}
          </div>
        </>
      ) : (
        // themed score tile for cards without a first-page thumbnail
        <div
          style={{ minHeight: phHeight(card.id) }}
          className="flex w-full flex-col justify-between gap-3 bg-gradient-to-br from-[#20202b] to-[#2c2c3b] p-4"
        >
          <div className="flex items-center gap-1.5 text-[var(--muted)]">
            <FileMusic size={15} />
            <span className="font-mono text-[10px] uppercase tracking-widest">Score</span>
          </div>
          <div>
            <p className="line-clamp-2 text-sm font-semibold">
              {card.author ?? card.piece?.composer ?? "Unknown composer"}
            </p>
            <p className="mt-0.5 line-clamp-2 text-xs text-[var(--muted)]">{title}</p>
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
