"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { User, Settings, Bookmark, LogIn } from "lucide-react";

export default function TopBar() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  return (
    <header className="fixed inset-x-0 top-0 z-40 border-b border-[var(--border)] bg-[var(--background)]/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-2.5 sm:px-5">
        <Link href="/" className="text-lg font-bold tracking-tight">
          scorekit
        </Link>

        <div className="relative" ref={ref}>
          <button
            onClick={() => setOpen((o) => !o)}
            aria-label="Profile menu"
            aria-expanded={open}
            className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--surface-2)] text-[var(--foreground)] ring-1 ring-[var(--border)] transition-colors hover:ring-white/25"
          >
            <User size={18} />
          </button>

          {open && (
            <div className="absolute right-0 mt-2 w-56 overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] py-2 shadow-2xl shadow-black/50">
              <div className="flex items-center gap-3 px-4 py-2">
                <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-[var(--accent)] to-[var(--accent-2)]">
                  <User size={16} className="text-white" />
                </div>
                <div className="leading-tight">
                  <p className="text-sm font-medium">Guest</p>
                  <p className="text-xs text-[var(--muted)]">Not signed in</p>
                </div>
              </div>

              <button
                disabled
                className="mt-1 flex w-full cursor-not-allowed items-center gap-3 px-4 py-2.5 text-sm text-[var(--muted)]"
              >
                <LogIn size={16} />
                Sign in (coming soon)
              </button>

              <div className="my-1 border-t border-[var(--border)]" />

              <MenuLink href="/profile" onClick={() => setOpen(false)} icon={<User size={16} />}>
                Your profile
              </MenuLink>
              <MenuLink href="/favorites" onClick={() => setOpen(false)} icon={<Bookmark size={16} />}>
                Saved
              </MenuLink>
              <MenuLink href="/settings" onClick={() => setOpen(false)} icon={<Settings size={16} />}>
                Settings
              </MenuLink>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

function MenuLink({
  href,
  onClick,
  icon,
  children,
}: {
  href: string;
  onClick: () => void;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      onClick={onClick}
      className="flex items-center gap-3 px-4 py-2.5 text-sm transition-colors hover:bg-white/5"
    >
      {icon}
      {children}
    </Link>
  );
}
