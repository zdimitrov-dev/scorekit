"use client";
import { useCallback, useEffect, useState } from "react";

/**
 * A per-browser set of ids persisted in localStorage — a stand-in for the
 * likes / saved-catalog features until auth + the interactions table are wired.
 */
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
        if (next.has(id)) next.delete(id);
        else next.add(id);
        try {
          localStorage.setItem(key, JSON.stringify([...next]));
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
