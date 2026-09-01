"use client";
import type { FeedCard } from "./types";

/**
 * Keeps the ranked home feed ready *before* the Home tab is opened.
 *
 * Home used to paint a server-rendered board and then replace it once the ranking came
 * back, so every visit showed a few seconds of the wrong order before it jumped. Ranking
 * needs the browser's like/save history, which the server cannot see, so it can never be
 * server-rendered correctly — the fix is to have the answer already in hand.
 *
 * The cache is keyed by a signature of the signals it was built from, so it is used only
 * while it still reflects what the person has actually liked. Liking something invalidates
 * it and immediately starts building the replacement, which is normally finished long
 * before they navigate back to Home.
 */

const KEY = "scorekit:feed-cache";
const LIMIT = 80;
// Rebuilt on this cadence even when nothing changed, so the feed still moves as the
// corpus grows rather than showing the same board all session.
const MAX_AGE_MS = 5 * 60 * 1000;

type Signal = { card_id: string; action: string };
export type Ranker = "auto" | "model" | "content";
type Cached = {
  signature: string;
  cards: FeedCard[];
  at: number;
  personalized: boolean;
  ranker: string;          // which ranker actually produced it
  modelAvailable: boolean;
};

function ids(key: string): string[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(key) || "[]");
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === "string") : [];
  } catch {
    return [];
  }
}

export function currentSignals(): Signal[] {
  return [
    ...ids("scorekit:likes").map((card_id) => ({ card_id, action: "like" })),
    ...ids("scorekit:saves").map((card_id) => ({ card_id, action: "save" })),
  ];
}

/** Identifies a set of signals by content, so a cache built from different likes is not
 *  mistaken for a current one. Sorted, because order of liking is irrelevant here. */
/** Includes the requested ranker, so switching rankers never reads the other one's
 *  cached board. */
export function signatureOf(signals: Signal[], ranker: Ranker = "auto"): string {
  return ranker + "::" + signals.map((s) => `${s.action}:${s.card_id}`).sort().join("|");
}

let memory: Cached | null = null;

function readStore(): Cached | null {
  if (memory) return memory;
  try {
    const raw = sessionStorage.getItem(KEY);
    memory = raw ? (JSON.parse(raw) as Cached) : null;
  } catch {
    memory = null;
  }
  return memory;
}

function writeStore(entry: Cached) {
  memory = entry;
  try {
    sessionStorage.setItem(KEY, JSON.stringify(entry));
  } catch {
    /* quota or private mode — the in-memory copy still serves this session */
  }
}

/** The cached feed if it still matches the current signals and hasn't gone stale. */
export function getFresh(ranker: Ranker = "auto"): Cached | null {
  const entry = readStore();
  if (!entry) return null;
  if (entry.signature !== signatureOf(currentSignals(), ranker)) return null;
  if (Date.now() - entry.at > MAX_AGE_MS) return null;
  return entry;
}

/** Forget the cached board and the browser's like/save history.
 *
 *  A development affordance, for testing a ranker against a taste built from scratch. The
 *  signals live only in this browser, so this is the only place they exist. */
export function clearBrowserSignals(): void {
  memory = null;
  for (const key of [KEY, "scorekit:likes", "scorekit:saves"]) {
    try {
      localStorage.removeItem(key);
      sessionStorage.removeItem(key);
    } catch {
      /* private mode: nothing to clear */
    }
  }
}

let inFlight: Promise<Cached | null> | null = null;

/** Fetch and cache a fresh ranking. Concurrent callers share one request. */
export function refreshFeed(ranker: Ranker = "auto"): Promise<Cached | null> {
  if (inFlight) return inFlight;
  const signals = currentSignals();
  const signature = signatureOf(signals, ranker);

  inFlight = (async () => {
    try {
      const res = await fetch("/api/recommend", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ signals, limit: LIMIT, ranker }),
      });
      const data = (await res.json()) as {
        cards?: FeedCard[];
        personalized?: boolean;
        ranker?: string;
        model?: { available?: boolean };
      };
      if (!res.ok || !Array.isArray(data.cards)) return null;
      const entry: Cached = {
        signature,
        cards: data.cards,
        at: Date.now(),
        personalized: Boolean(data.personalized),
        ranker: data.ranker ?? "content",
        modelAvailable: Boolean(data.model?.available),
      };
      writeStore(entry);
      return entry;
    } catch {
      return null;
    } finally {
      inFlight = null;
    }
  })();
  return inFlight;
}

/** Rebuild in the background — called after a like or save, so the next visit to Home is
 *  already correct. Fire and forget: nothing waits on it. */
export function warmFeed() {
  if (getFresh()) return;
  void refreshFeed();
}
