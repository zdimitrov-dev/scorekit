import { getCards } from "@/lib/cards";
import SearchFeed from "@/components/SearchFeed";

export const dynamic = "force-dynamic";

export default async function SearchPage() {
  const cards = await getCards();
  return (
    <div className="mx-auto max-w-6xl px-3 pt-4 sm:px-5">
      <SearchFeed cards={cards} />
    </div>
  );
}
