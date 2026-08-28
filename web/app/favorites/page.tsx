import { getCards } from "@/lib/cards";
import FavoritesFeed from "@/components/FavoritesFeed";

export const dynamic = "force-dynamic";

export default async function FavoritesPage() {
  const cards = await getCards();
  return (
    <div className="mx-auto max-w-6xl px-3 pt-4 sm:px-5">
      <FavoritesFeed cards={cards} />
    </div>
  );
}
