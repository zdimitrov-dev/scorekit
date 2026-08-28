import { getCards } from "@/lib/cards";
import Feed from "@/components/Feed";

export const dynamic = "force-dynamic"; // always read fresh cards from Supabase

export default async function Home() {
  const cards = await getCards();
  return (
    <div className="mx-auto max-w-6xl px-3 pt-4 sm:px-5">
      <Feed cards={cards} />
    </div>
  );
}
