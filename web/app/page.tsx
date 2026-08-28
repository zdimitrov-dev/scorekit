import { getCards } from "@/lib/cards";
import Feed from "@/components/Feed";

export const dynamic = "force-dynamic"; // always read fresh cards from Supabase

export default async function Home() {
  const cards = await getCards();
  return (
    <div className="mx-auto max-w-6xl px-3 pt-6 sm:px-5">
      <header className="mb-5 px-1">
        <h1 className="text-2xl font-bold tracking-tight">scorekit</h1>
        <p className="mt-0.5 text-sm text-[var(--muted)]">
          Discover piano music — tutorials, scores &amp; performances in one board.
        </p>
      </header>
      <Feed cards={cards} />
    </div>
  );
}
