"use client";

/**
 * StrategyChart
 *
 * Renders an equity-curve line chart (from performance_snapshots) with
 * overlaid buy/sell trade markers (from trade_history), plus a row of
 * KPI cards showing key performance metrics.
 */

import { useEffect, useState, useMemo } from "react";
import { createClient } from "@/lib/supabase/client";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceDot,
  CartesianGrid,
  Legend,
} from "recharts";
import type { PerformanceSnapshot, Trade, StrategyMetrics } from "@/types/trading";
import { KpiCard } from "@/components/dashboard/KpiCard";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface Props {
  strategyId: string;
  strategyKey: string;
  /** Maximum number of snapshots to display (default: 365) */
  maxSnapshots?: number;
}

// ---------------------------------------------------------------------------
// Internal types
// ---------------------------------------------------------------------------

interface ChartDataPoint {
  date: string;       // YYYY-MM-DD — used as xAxis key & for ReferenceDot matching
  equity: number;
  dailyPnl: number;
}

interface TradeMarker {
  date: string;       // YYYY-MM-DD
  equity: number;     // equity on that day (y-position on chart)
  side: "BUY" | "SELL";
  ticker: string;
  price: number;
  realizedPnl?: number;
}

// ---------------------------------------------------------------------------
// Custom tooltip
// ---------------------------------------------------------------------------

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number; name: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 font-semibold text-neutral-300">{label}</p>
      {payload.map((p) => (
        <p key={p.name} className="tabular-nums text-neutral-400">
          {p.name === "equity" ? "Equity" : "Daily PnL"}:{" "}
          <span className="text-neutral-100">
            {new Intl.NumberFormat("en-US", {
              style: "currency",
              currency: "USD",
              maximumFractionDigits: 0,
            }).format(p.value)}
          </span>
        </p>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function StrategyChart({
  strategyId,
  strategyKey,
  maxSnapshots = 365,
}: Props) {
  const supabase = createClient();

  const [snapshots, setSnapshots] = useState<PerformanceSnapshot[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [metrics, setMetrics] = useState<StrategyMetrics | null>(null);
  const [loading, setLoading] = useState(true);

  // ------------------------------------------------------------------
  // Fetch data
  // ------------------------------------------------------------------
  useEffect(() => {
    if (!strategyId || !strategyKey) return;

    const fetchAll = async () => {
      setLoading(true);
      try {
        // Snapshots (equity curve)
        const { data: snapshotData } = await supabase
          .schema("trades")
          .from("performance_snapshots")
          .select("*")
          .eq("strategy_id", strategyId)
          .order("snapshot_date", { ascending: true })
          .limit(maxSnapshots);

        if (snapshotData) setSnapshots(snapshotData);

        // Trade history for markers
        const { data: tradesData } = await supabase
          .schema("trades")
          .from("trade_history")
          .select("*")
          .eq("strategy_id", strategyId)
          .order("executed_at", { ascending: true });

        if (tradesData) setTrades(tradesData);

        // Analytics metrics from backend
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/analytics/strategy/${strategyKey}/metrics`,
          { cache: "no-store" }
        );
        if (response.ok) {
          const metricsData = await response.json();
          setMetrics(metricsData);
        }
      } catch (err) {
        console.error("StrategyChart: failed to fetch data", err);
      } finally {
        setLoading(false);
      }
    };

    fetchAll();
  }, [strategyId, strategyKey, maxSnapshots, supabase]);

  // ------------------------------------------------------------------
  // Derived data
  // ------------------------------------------------------------------

  const chartData: ChartDataPoint[] = useMemo(
    () =>
      snapshots.map((s) => ({
        date: s.snapshot_date,
        equity:
          typeof s.equity_value === "number"
            ? s.equity_value
            : parseFloat(String(s.equity_value)),
        dailyPnl:
          typeof s.daily_pnl === "number"
            ? s.daily_pnl
            : parseFloat(String(s.daily_pnl)),
      })),
    [snapshots]
  );

  // Build a map date → equity for ReferenceDot y-positions
  const equityByDate = useMemo(() => {
    const map = new Map<string, number>();
    chartData.forEach((d) => map.set(d.date, d.equity));
    return map;
  }, [chartData]);

  const tradeMarkers = useMemo<TradeMarker[]>(() => {
    const results: TradeMarker[] = [];
    for (const t of trades) {
      const tradeDate = t.executed_at.slice(0, 10); // YYYY-MM-DD
      const equity = equityByDate.get(tradeDate);
      if (equity !== undefined) {
        results.push({
          date: tradeDate,
          equity,
          side: t.side,
          ticker: t.ticker,
          price: t.executed_price,
          realizedPnl: t.realized_pnl,
        });
      }
    }
    return results;
  }, [trades, equityByDate]);

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------

  const startingCash = snapshots.length
    ? parseFloat(String(snapshots[0].equity_value))
    : 100_000;

  const latestEquity = chartData.at(-1)?.equity ?? startingCash;

  const fmt = (v: number) =>
    new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    }).format(v);

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-neutral-400 text-sm">
        Loading chart…
      </div>
    );
  }

  if (chartData.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-neutral-400 text-sm">
        Keine Snapshot-Daten vorhanden. Starte einen Backtest oder warte auf den nächsten Trade.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* KPI Cards */}
      {metrics && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <KpiCard
            label="Return letzte Woche"
            value={`${metrics.return_1w >= 0 ? "+" : ""}${metrics.return_1w.toFixed(2)}%`}
            positive={metrics.return_1w >= 0}
          />
          <KpiCard
            label="Return letzter Monat"
            value={`${metrics.return_1m >= 0 ? "+" : ""}${metrics.return_1m.toFixed(2)}%`}
            positive={metrics.return_1m >= 0}
          />
          <KpiCard
            label="Win Rate"
            value={`${metrics.win_rate.toFixed(1)}%`}
            sub={`${metrics.total_trades} Trades`}
          />
          <KpiCard
            label="Max Drawdown"
            value={`-${metrics.max_drawdown.toFixed(2)}%`}
            positive={false}
          />
        </div>
      )}

      {/* Chart legend */}
      <div className="flex items-center gap-4 text-xs text-neutral-400">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-green-500" />
          Buy
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-red-400" />
          Sell
        </span>
        <span className="ml-auto tabular-nums">
          Aktuell: <span className="text-neutral-100">{fmt(latestEquity)}</span>
        </span>
      </div>

      {/* Equity + trade-markers chart */}
      <ResponsiveContainer width="100%" height={340}>
        <LineChart
          data={chartData}
          margin={{ top: 6, right: 16, bottom: 0, left: 8 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 11, fill: "#737373" }}
            tickFormatter={(d: string) => {
              const dt = new Date(d + "T00:00:00");
              return dt.toLocaleDateString("de-DE", {
                day: "2-digit",
                month: "2-digit",
              });
            }}
            minTickGap={40}
          />
          <YAxis
            tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
            tick={{ fontSize: 11, fill: "#737373" }}
            width={52}
          />
          <Tooltip content={<CustomTooltip />} />
          <Line
            type="monotone"
            dataKey="equity"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: "#3b82f6" }}
          />

          {/* Buy markers */}
          {tradeMarkers
            .filter((m) => m.side === "BUY")
            .map((m, i) => (
              <ReferenceDot
                key={`buy-${i}`}
                x={m.date}
                y={m.equity}
                r={6}
                fill="#22c55e"
                stroke="#ffffff"
                strokeWidth={1.5}
                label={{
                  value: "▲",
                  position: "top",
                  fontSize: 10,
                  fill: "#22c55e",
                }}
              />
            ))}

          {/* Sell markers */}
          {tradeMarkers
            .filter((m) => m.side === "SELL")
            .map((m, i) => (
              <ReferenceDot
                key={`sell-${i}`}
                x={m.date}
                y={m.equity}
                r={6}
                fill="#ef4444"
                stroke="#ffffff"
                strokeWidth={1.5}
                label={{
                  value: "▼",
                  position: "bottom",
                  fontSize: 10,
                  fill: "#ef4444",
                }}
              />
            ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
