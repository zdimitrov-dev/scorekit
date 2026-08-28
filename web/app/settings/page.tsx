import { Settings } from "lucide-react";

export default function SettingsPage() {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-3 px-6 pt-28 text-center">
      <Settings size={40} className="text-[var(--muted)]" />
      <h1 className="text-xl font-semibold">Settings</h1>
      <p className="text-sm text-[var(--muted)]">
        Coming soon — your saved catalog, feed preferences, and account.
      </p>
    </div>
  );
}
