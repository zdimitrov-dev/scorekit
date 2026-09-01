"use client";
import { readTimes } from "./useCollection";

/**
 * Interaction logging — the recommender's training signal (Phase 5).
 *
 * Every card that is actually *seen* is logged, so this fires far more often than any
 * other request in the app. Three consequences shape the design:
 *
 * - **Batched.** Events queue and flush on a timer, never one request per card.
 * - **Flushed on the way out.** A queue lost when the tab closes is training data lost, so
 *   the final flush uses `sendBeacon`, which the browser delivers after the page is gone.
 *   `fetch` is cancelled at unload and would silently drop the tail of every session.
 * - **Never in the user's way.** Failures are swallowed. This is telemetry; losing an
 *   event costs a little data, and must never cost someone their like.
 */

export type Action = "seen" | "like" | "save" | "click" | "skip";

export interface TrackEvent {
  action: Action;
  card_id?: string;
  piece_id?: string;
  dwell_ms?: number;
  feed_position?: number;
  /** When the thing happened, ISO 8601. Stamped here rather than left to the database,
   *  which would otherwise record when the row was written: up to a batch interval later
   *  for a normal event, and arbitrarily later for one flushed at page exit or recovered
   *  by a reconciliation. Training reads created_at as chronology, so the difference
   *  matters. Filled in automatically by track and trackNow. */
  occurred_at?: string;
}

const VIEWER_KEY = "scorekit:viewer";
const ENDPOINT = "/api/interactions";
const FLUSH_MS = 4000;
const MAX_BATCH = 60;

/** A UUID, because `interactions.user_id` is a uuid column — any other shape is rejected
 *  by Postgres and the whole batch is lost. */
function newId(): string {
  if (typeof crypto?.randomUUID === "function") return crypto.randomUUID();
  // randomUUID needs a secure context; keep a valid v4 shape either way
  return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) =>
    (+c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (+c / 4)))).toString(16),
  );
}

// Used when storage is unavailable, so a private-mode session still logs — grouped for
// this page load only, rather than being dropped entirely.
let ephemeralId: string | null = null;

/** Anonymous, per-browser. No account and no personal data — just enough to group one
 *  person's history for training, and swappable for a real user id when auth lands. */
export function viewerId(): string {
  try {
    let id = localStorage.getItem(VIEWER_KEY);
    if (!id) {
      id = newId();
      localStorage.setItem(VIEWER_KEY, id);
    }
    return id;
  } catch {
    return (ephemeralId ??= newId());
  }
}

let queue: TrackEvent[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;

function send(events: TrackEvent[], beacon = false) {
  if (events.length === 0) return;
  const body = JSON.stringify({ user_id: viewerId(), events });
  try {
    if (beacon && typeof navigator.sendBeacon === "function") {
      navigator.sendBeacon(ENDPOINT, new Blob([body], { type: "application/json" }));
      return;
    }
    void fetch(ENDPOINT, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body,
      keepalive: true,
    }).catch(() => {});
  } catch {
    /* telemetry must never surface to the user */
  }
}

export function flush(beacon = false) {
  const events = queue;
  queue = [];
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
  send(events, beacon);
}

export function track(event: TrackEvent) {
  queue.push({ occurred_at: new Date().toISOString(), ...event });
  if (queue.length >= MAX_BATCH) {
    flush();
    return;
  }
  timer ??= setTimeout(() => flush(), FLUSH_MS);
}

/**
 * Send one event now, retrying briefly, and report whether it landed.
 *
 * Likes and saves are user actions, not telemetry. The batch queue above is right for
 * impressions — losing one costs a little training data — but wrong for these: a like
 * lives in localStorage the instant it is pressed and reaches the database only if this
 * succeeds, so a swallowed failure leaves the two permanently disagreeing.
 */
export async function trackNow(event: TrackEvent, attempts = 3): Promise<boolean> {
  const stamped = { occurred_at: new Date().toISOString(), ...event };
  const body = JSON.stringify({ user_id: viewerId(), events: [stamped] });
  for (let attempt = 0; attempt < attempts; attempt++) {
    try {
      const res = await fetch(ENDPOINT, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body,
        keepalive: true,
      });
      if (res.ok) return true;
    } catch {
      /* offline, or the API is restarting: worth another try */
    }
    await new Promise((r) => setTimeout(r, 300 * 2 ** attempt));
  }
  return false;
}

/**
 * Reconcile this browser's likes and saves against the database.
 *
 * Retrying at the moment of the press is not enough on its own: a like made while the API
 * was down is still missing afterwards, and nothing would ever notice. This runs at
 * startup and backfills whatever the server does not already have, which makes the two
 * stores converge instead of drifting further apart with every outage.
 */
export async function syncSignals(): Promise<number> {
  const read = (key: string): string[] => {
    try {
      const parsed: unknown = JSON.parse(localStorage.getItem(key) || "[]");
      return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === "string") : [];
    } catch {
      return [];
    }
  };
  const likes = read("scorekit:likes");
  const saves = read("scorekit:saves");
  if (likes.length === 0 && saves.length === 0) return 0;
  try {
    const res = await fetch("/api/interactions/sync", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        user_id: viewerId(),
        likes,
        saves,
        // Where the time is known the row is written with it and counts as ordinary
        // history. Only ids from before times were recorded arrive without one, and
        // those are the ones the server has to flag.
        like_times: readTimes("scorekit:likes"),
        save_times: readTimes("scorekit:saves"),
      }),
    });
    if (!res.ok) return 0;
    const data = (await res.json()) as { inserted?: number };
    return data.inserted ?? 0;
  } catch {
    return 0;
  }
}

let listening = false;

/** Flush on the way out. `visibilitychange` is the reliable signal — mobile browsers
 *  often kill a backgrounded tab without ever firing `beforeunload`. */
export function startTracking() {
  if (listening || typeof document === "undefined") return;
  listening = true;
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flush(true);
  });
  window.addEventListener("pagehide", () => flush(true));
}
