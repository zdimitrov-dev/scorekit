"use client";
import { useCallback, useEffect, useState } from "react";
import { RefreshCw, FlaskConical, Database, Activity, Cpu } from "lucide-react";
import { currentSignals, getFresh } from "@/lib/feedCache";

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
            <div className="mt-3 border-t border-[var(--border)] pt-2">
              <Row label="This browser: likes" value={local.likes} />
              <Row label="This browser: saves" value={local.saves} />
              <Row
                label="Feed cache"
                value={local.cached ? `ready (${local.cachedBy})` : "empty"}
              />
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}
