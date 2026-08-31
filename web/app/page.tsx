import { getCards } from "@/lib/cards";
import HomeFeed from "@/components/HomeFeed";

export const dynamic = "force-dynamic"; // always read fresh cards from Supabase

export default async function Home() {
  // Server-rendered board so the page paints immediately; HomeFeed then replaces it with
  // the ranked feed, which needs the browser's localStorage signals to personalize.
  const cards = await getCards();
  return (
    <div className="mx-auto max-w-6xl px-3 pt-4 sm:px-5">
      <HomeFeed fallback={cards} />
    </div>
  );
}
