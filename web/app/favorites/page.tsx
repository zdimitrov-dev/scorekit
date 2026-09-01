import FavoritesFeed from "@/components/FavoritesFeed";

// Saved ids live in the browser, so there is nothing useful to render on the server —
// the component fetches exactly the saved cards by id once it can read localStorage.
export default function FavoritesPage() {
  return (
    <div className="mx-auto max-w-6xl px-3 pt-4 sm:px-5">
      <FavoritesFeed />
    </div>
  );
}
