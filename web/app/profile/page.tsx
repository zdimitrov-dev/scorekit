import Link from "next/link";
import { User, Settings, Bookmark, LogIn } from "lucide-react";

export default function ProfilePage() {
  return (
    <div className="mx-auto max-w-md px-6 pt-10">
      <div className="flex flex-col items-center gap-3 text-center">
        <div className="flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-br from-[var(--accent)] to-[var(--accent-2)]">
          <User size={34} className="text-white" />
        </div>
        <h1 className="text-xl font-semibold">Guest</h1>
        <p className="text-sm text-[var(--muted)]">Sign in to sync your saves across devices.</p>
        <button
          disabled
          className="mt-1 flex cursor-not-allowed items-center gap-2 rounded-full bg-[var(--surface-2)] px-5 py-2.5 text-sm font-semibold text-[var(--muted)]"
        >
          <LogIn size={16} /> Sign in (coming soon)
        </button>
      </div>

      <div className="mt-8 divide-y divide-[var(--border)] overflow-hidden rounded-2xl border border-[var(--border)]">
        <Link href="/favorites" className="flex items-center gap-3 px-4 py-3.5 text-sm transition-colors hover:bg-white/5">
          <Bookmark size={17} /> Saved
        </Link>
        <Link href="/settings" className="flex items-center gap-3 px-4 py-3.5 text-sm transition-colors hover:bg-white/5">
          <Settings size={17} /> Settings
        </Link>
      </div>
    </div>
  );
}
