"use client";

/**
 * Strategy Leaderboard Page
 *
 * Fetches and renders all active strategies ranked by performance metrics.
 */

import { useEffect, useState } from "react";
import type { StrategyLeaderboardEntry } from "@/types/trading";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const SORT_OPTIONS: { label: string; value: string }[] = [
  { label: "All-Time Return", value: "return_all" },
  { label: "1-Year Return", value: "return_1y" },
  { label: "1-Month Return", value: "return_1m" },
  { label: "1-Week Return", value: "return_1w" },
  { label: "Win Rate", value: "win_rate" },
];

function ReturnBadge({ value }: { value: number }) {
  const positive = value >= 0;
  return (
    <span
      className={`inline-block tabular-nums font-semibold ${
        positive ? "text-green-500" : "text-red-400"
      }`}
    >
      {positive ? "+" : ""}
      {value.toFixed(2)}%
    </span>
  );
}

function DrawdownBadge({ value }: { value: number }) {
  const severe = value > 20;
  return (
    <span
      className={`inline-block tabular-nums ${
        severe ? "text-red-500 font-semibold" : "text-neutral-300"
      }`}
    >
      -{value.toFixed(2)}%
    </span>
  );
}

export default function LeaderboardPage() {
  const [entries, setEntries] = useState<StrategyLeaderboardEntry[]>([]);
  const [sortBy, setSortBy] = useState("return_all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchLeaderboard = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(
          `${API_BASE}/analytics/leaderboard?sort_by=${sortBy}`,
          { cache: "no-store" }
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: StrategyLeaderboardEntry[] = await res.json();
        setEntries(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unbekannter Fehler");
      } finally {
        setLoading(false);
      }
    };
    fetchLeaderboard();
  }, [sortBy]);

  return (
    <main className="min-h-screen bg-neutral-950 text-neutral-100 p-6">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-xl font-semibold">Strategy Leaderboard</h1>
          <p className="text-sm text-neutral-400 mt-0.5">
            Alle aktiven Strategien sortiert nach Performance
          </p>
        </div>
        <Link
          href="/dashboard"
          className="rounded-lg border border-neutral-700 px-4 py-2 text-sm text-neutral-300 hover:bg-neutral-800 transition-colors"
        >
          ← Dashboard
        </Link>
      </div>

      {/* Sort selector */}
      <div className="mb-6 flex gap-2 flex-wrap">
        {SORT_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setSortBy(opt.value)}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              sortBy === opt.value
                ? "bg-blue-600 text-white"
                : "bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex h-40 items-center justify-center text-neutral-400">
          Lade Leaderboard…
        </div>
      ) : error ? (
        <div className="rounded-lg border border-red-800 bg-red-950/30 p-4 text-red-400">
          Fehler beim Laden: {error}
        </div>
      ) : entries.length === 0 ? (
        <div className="flex h-40 items-center justify-center text-neutral-400">
          Keine aktiven Strategien gefunden.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-neutral-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-neutral-800 text-left text-xs text-neutral-500 uppercase tracking-wide">
                <th className="px-4 py-3">#</th>
                <th className="px-4 py-3">Strategie</th>
                <th className="px-4 py-3 text-right">Equity</th>
                <th className="px-4 py-3 text-right">1D</th>
                <th className="px-4 py-3 text-right">1W</th>
                <th className="px-4 py-3 text-right">1M</th>
                <th className="px-4 py-3 text-right">1Y</th>
                <th className="px-4 py-3 text-right">All-Time</th>
                <th className="px-4 py-3 text-right">Win Rate</th>
                <th className="px-4 py-3 text-right">Max DD</th>
                <th className="px-4 py-3 text-right">Trades</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e, idx) => (
                <tr
                  key={e.strategy_key}
                  className={`border-b border-neutral-800/60 transition-colors hover:bg-neutral-900 ${
                    idx === 0 ? "bg-neutral-900/50" : ""
                  }`}
                >
                  <td className="px-4 py-3 text-neutral-500 font-semibold">
                    {idx + 1}
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-medium text-neutral-100">{e.name}</div>
                    <div className="text-xs text-neutral-500">{e.strategy_key}</div>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    $
                    {e.equity_value.toLocaleString("en-US", {
                      maximumFractionDigits: 0,
                    })}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <ReturnBadge value={e.return_1d} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <ReturnBadge value={e.return_1w} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <ReturnBadge value={e.return_1m} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <ReturnBadge value={e.return_1y} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <ReturnBadge value={e.return_all} />
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {e.win_rate.toFixed(1)}%
                  </td>
                  <td className="px-4 py-3 text-right">
                    <DrawdownBadge value={e.max_drawdown} />
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-neutral-400">
                    {e.total_trades}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
