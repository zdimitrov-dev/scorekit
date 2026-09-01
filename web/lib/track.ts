"use client";

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
  queue.push(event);
  if (queue.length >= MAX_BATCH) {
    flush();
    return;
  }
  timer ??= setTimeout(() => flush(), FLUSH_MS);
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
