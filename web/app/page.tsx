import HomeFeed from "@/components/HomeFeed";

// No server-side card fetch. Ranking depends on the browser's like/save history, so
// anything rendered here would be in the wrong order and would visibly re-sort a moment
// later — HomeFeed reads a ranking prepared in advance instead.
export default function Home() {
  return (
    <div className="mx-auto max-w-6xl px-3 pt-4 sm:px-5">
      <HomeFeed />
    </div>
  );
}
