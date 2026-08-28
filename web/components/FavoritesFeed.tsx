"use client";
import { useEffect, useState } from "react";
import type { FeedCard } from "@/lib/types";
import Feed from "./Feed";

export default function FavoritesFeed({ cards }: { cards: FeedCard[] }) {
  const [ids, setIds] = useState<Set<string> | null>(null);

  useEffect(() => {
    const read = (k: string) => {
      try {
        return JSON.parse(localStorage.getItem(k) || "[]") as string[];
      } catch {
        return [];
      }
    };
    setIds(new Set([...read("scorekit:likes"), ...read("scorekit:saves")]));
  }, []);

  if (ids === null) return null; // wait for localStorage to avoid a hydration flash

  const favs = cards.filter((c) => ids.has(c.id));
  return (
    <div>
      <h1 className="mb-4 px-1 text-xl font-bold tracking-tight">Saved</h1>
      <Feed cards={favs} emptyLabel="Nothing saved yet — like or save cards to find them here." />
    </div>
  );
}
