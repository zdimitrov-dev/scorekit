"use client";
import { useCallback, useEffect, useState } from "react";

/**
 * A per-browser set of ids persisted in localStorage — a stand-in for the
 * likes / saved-catalog features until auth + the interactions table are wired.
 *
 * Alongside the set, the time each id was added is kept under `<key>:at`. Without it a
 * reconciliation can only tell the server *that* something was liked, not when, and the
 * row lands with the sync time — which training reads as chronology. The set itself keeps
 * its original shape so nothing else that reads these keys has to change.
 */
export function timesKey(key: string): string {
  return `${key}:at`;
}

/** `{card_id: ISO timestamp}` for a collection, as far as it is known. Ids added before
 *  this was recorded simply have no entry. */
export function readTimes(key: string): Record<string, string> {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(timesKey(key)) || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed as Record<string, unknown>).filter(
        ([, v]) => typeof v === "string",
      ) as [string, string][],
    );
  } catch {
    return {};
  }
}

export function useCollection(key: string) {
  const [ids, setIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw) setIds(new Set(JSON.parse(raw) as string[]));
    } catch {
      /* private mode / blocked storage — start empty */
    }
  }, [key]);

  const toggle = useCallback(
    (id: string) => {
      setIds((prev) => {
        const next = new Set(prev);
        const adding = !next.has(id);
        if (adding) next.add(id);
        else next.delete(id);
        try {
          localStorage.setItem(key, JSON.stringify([...next]));
          const times = readTimes(key);
          if (adding) times[id] = new Date().toISOString();
          else delete times[id];
          localStorage.setItem(timesKey(key), JSON.stringify(times));
        } catch {
          /* ignore */
        }
        return next;
      });
    },
    [key],
  );

  return { ids, has: (id: string) => ids.has(id), toggle };
}
