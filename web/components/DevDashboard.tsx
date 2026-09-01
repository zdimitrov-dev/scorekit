"use client";
import { useCallback, useEffect, useState } from "react";
import { RefreshCw, FlaskConical, Database, Activity, Cpu, Eraser } from "lucide-react";
import { clearBrowserSignals, getFresh } from "@/lib/feedCache";

/**
 * Development dashboard. Not part of the product; remove before release.
 *
 * Exists because the two rankers are indistinguishable from the outside: the feed looks
 * the same whether the hand-tuned scoring or the trained model produced it, so "which one
 * am I actually looking at" is otherwise unanswerable without reading logs.
 */

type Stats = {
  model: {
    available: boolean;
    promoted: boolean;
    name?: string;
    auc?: number;
    heuristic_auc?: number;
    precision_at_10?: number;
    positives?: number;
    n_train?: number;
    n_test?: number;
    gate_reason?: string;
  };
  active_ranker: string;
  corpus: {
    pieces: number;
    cards: number;
    cards_by_source: Record<string, number>;
    tagged_pieces: number;
    distinct_tags: number;
  };
  interactions: {
    total: number;
    by_action: Record<string, number>;
    positives: number;
  };
  gate: { min_positives: number; min_auc_gain: number };
  error?: string;
};

function Panel({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl bg-[var(--surface)] p-4 ring-1 ring-[var(--border)]">
      <h2 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
        {icon}
        {title}
      </h2>
      {children}
    </section>
  );
}

function Row({ label, value, tone }: { label: string; value: React.ReactNode; tone?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-[var(--border)] py-1.5 last:border-0">
      <span className="text-xs text-[var(--muted)]">{label}</span>
      <span className={`font-mono text-sm ${tone ?? ""}`}>{value}</span>
    </div>
  );
}

/** A destructive control. Arming it changes the label to say exactly what is about to be
 *  deleted, so the second press is made knowing the consequence rather than confirming a
 *  generic "are you sure". */
function Danger({
  onClick,
  armed,
  busy,
  idle,
  confirm,
}: {
  onClick: () => void;
  armed: boolean;
  busy: boolean;
  idle: string;
  confirm: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={busy}
      className={`flex w-full items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-xs font-medium transition-colors disabled:opacity-40 ${
        armed
          ? "bg-red-500/15 text-red-400"
          : "bg-[var(--surface-2)] text-[var(--muted)] hover:text-[var(--foreground)]"
      }`}
    >
      <Eraser size={13} />
      {armed ? confirm : idle}
    </button>
  );
}

const num = (n?: number, digits = 3) =>
  typeof n === "number" && !Number.isNaN(n) ? n.toFixed(digits) : "n/a";

export default function DevDashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [local, setLocal] = useState({ likes: 0, saves: 0, cached: false, cachedBy: "" });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/dev", { cache: "no-store" });
      setStats((await res.json()) as Stats);
    } catch {
      setStats(null);
    } finally {
      setLoading(false);
    }
    const read = (k: string) => {
      try {
        const v: unknown = JSON.parse(localStorage.getItem(k) || "[]");
        return Array.isArray(v) ? v.length : 0;
      } catch {
        return 0;
      }
    };
    const fresh = getFresh("auto");
    setLocal({
      likes: read("scorekit:likes"),
      saves: read("scorekit:saves"),
      cached: Boolean(fresh),
      cachedBy: fresh?.ranker ?? "",
    });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Every destructive control takes two presses, because none of them has an undo.
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reset = useCallback(() => {
    if (confirming !== "signals") {
      setConfirming("signals");
      return;
    }
    clearBrowserSignals();
    window.location.reload();
  }, [confirming]);

  const clearLog = useCallback(
    async (action: string | null) => {
      const key = `log:${action ?? "all"}`;
      if (confirming !== key) {
        setConfirming(key);
        return;
      }
      setConfirming(null);
      setBusy(true);
      try {
        await fetch("/api/dev", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ action }),
        });
      } catch {
        /* the reload below will show what actually happened */
      }
      setBusy(false);
      await load();
    },
    [confirming, load],
  );

  const m = stats?.model;
  const served = stats?.active_ranker === "model";

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Dev dashboard</h1>
          <p className="text-xs text-[var(--muted)]">
            Development surface. Remove before release.
          </p>
        </div>
        <button
          onClick={() => void load()}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-full bg-[var(--surface-2)] px-3 py-1.5 text-xs font-medium transition-colors hover:text-[var(--foreground)] disabled:opacity-40"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          Reload
        </button>
      </header>

      {stats?.error || (!loading && !stats) ? (
        <p className="rounded-2xl bg-[var(--surface)] p-4 text-sm text-[var(--muted)]">
          Could not reach the API. Is it running on port 8000?
        </p>
      ) : null}

      {stats && !stats.error && (
        <div className="grid gap-4 md:grid-cols-2">
          <Panel title="Which ranker is live" icon={<Cpu size={13} />}>
            <div
              className={`mb-3 rounded-xl px-3 py-2 text-sm font-semibold ${
                served
                  ? "bg-[var(--accent)]/15 text-[var(--accent)]"
                  : "bg-[var(--surface-2)]"
              }`}
            >
              {served ? "Trained model" : "Content ranker (hand-tuned)"}
            </div>
            <Row label="Model on disk" value={m?.available ? "yes" : "none"} />
            <Row
              label="Passed its gate"
              value={m?.promoted ? "yes" : "no"}
              tone={m?.promoted ? "text-emerald-400" : "text-amber-400"}
            />
            {m?.gate_reason && (
              <p className="mt-2 text-xs leading-relaxed text-[var(--muted)]">
                {m.gate_reason}
              </p>
            )}
            <p className="mt-3 text-xs leading-relaxed text-[var(--muted)]">
              A model only serves the feed once it beats the hand-tuned scoring by{" "}
              {num(stats.gate.min_auc_gain, 2)} on held-out data, with at least{" "}
              {stats.gate.min_positives} likes or saves to measure against.
            </p>
          </Panel>

          <Panel title="Model scores" icon={<FlaskConical size={13} />}>
            {m?.available ? (
              <>
                <Row label="Algorithm" value={m.name ?? "?"} />
                <Row label="Model AUC" value={num(m.auc)} />
                <Row label="Heuristic AUC" value={num(m.heuristic_auc)} />
                <Row label="Precision@10" value={num(m.precision_at_10)} />
                <Row label="Trained on" value={`${m.n_train ?? 0} rows`} />
                <Row label="Tested on" value={`${m.n_test ?? 0} rows`} />
                <Row label="Positives in data" value={m.positives ?? 0} />
              </>
            ) : (
              <p className="text-sm text-[var(--muted)]">
                Nothing trained yet. Run{" "}
                <code className="font-mono text-xs">
                  python -m scorekit.jobs.train_model --force
                </code>
                .
              </p>
            )}
          </Panel>

          <Panel title="Corpus" icon={<Database size={13} />}>
            <Row label="Pieces" value={stats.corpus.pieces} />
            <Row label="Tagged pieces" value={stats.corpus.tagged_pieces} />
            <Row label="Distinct tags" value={stats.corpus.distinct_tags} />
            <Row label="Cards" value={stats.corpus.cards} />
            {Object.entries(stats.corpus.cards_by_source).map(([src, n]) => (
              <Row key={src} label={`  ${src}`} value={n} />
            ))}
          </Panel>

          <Panel title="Interactions" icon={<Activity size={13} />}>
            <Row label="Total events" value={stats.interactions.total} />
            {Object.entries(stats.interactions.by_action).map(([a, n]) => (
              <Row key={a} label={`  ${a}`} value={n} />
            ))}
            <Row
              label="Positives (like + save)"
              value={`${stats.interactions.positives} / ${stats.gate.min_positives} needed`}
              tone={
                stats.interactions.positives >= stats.gate.min_positives
                  ? "text-emerald-400"
                  : "text-amber-400"
              }
            />
            {/* The two stores drift apart: the feed ranks from what this browser
                remembers, the model trains from what reached the database. Events sent
                while the API was down are swallowed by design, so the browser can be
                ahead. Showing both makes that visible instead of puzzling. */}
            <div className="mt-3 border-t border-[var(--border)] pt-2">
              <Row label="This browser: likes" value={local.likes} />
              <Row label="This browser: saves" value={local.saves} />
              <Row
                label="Ranks from"
                value={`${local.likes + local.saves} browser signals`}
                tone={
                  local.likes + local.saves > stats.interactions.positives
                    ? "text-amber-400"
                    : undefined
                }
              />
              <Row
                label="Feed cache"
                value={local.cached ? `ready (${local.cachedBy})` : "empty"}
              />
            </div>
            <div className="mt-3 space-y-1.5">
              <Danger
                onClick={() => void clearLog("impression")}
                armed={confirming === "log:impression"}
                busy={busy}
                idle="Clear impressions from the database"
                confirm="Press again to delete every impression row"
              />
              <Danger
                onClick={() => void clearLog(null)}
                armed={confirming === "log:all"}
                busy={busy}
                idle="Clear the whole interactions table"
                confirm="Press again to delete every interaction, likes included"
              />
              <Danger
                onClick={reset}
                armed={confirming === "signals"}
                busy={busy}
                idle="Clear browser likes and saves"
                confirm="Press again to erase this browser's likes and saves"
              />
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}
