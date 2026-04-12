"use client";

import { useStrategies } from "@/hooks/useStrategies";
import { StrategyChart } from "@/components/dashboard/StrategyChart";
import { PositionsTable } from "@/components/dashboard/PositionsTable";
import { TradesFeed } from "@/components/dashboard/TradesFeed";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import Link from "next/link";
import type { OpenPosition, Trade } from "@/types/trading";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const BACKTEST_SUPPORTED_KEYS = new Set([
  "strategy_a_legalinsider",
  "strategy_b_unusualvolume",
  "strategy_c_newssentiment",
  "strategy_ab_combined",
]);

export default function DashboardPage() {
  const supabase = createClient();
  const { strategies, selectedStrategyId, selectedStrategy, selectedPortfolio, setSelectedStrategyId, loading: strategiesLoading } =
    useStrategies();

  const [positions, setPositions] = useState<OpenPosition[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [metrics, setMetrics] = useState({
    roi: 0,
    win_rate: 0,
    max_drawdown: 0,
    sharpe_ratio: 0,
  });
  const [loading, setLoading] = useState(false);
  const [backtestEnabled, setBacktestEnabled] = useState(false);
  const [backtestStartDate, setBacktestStartDate] = useState("2025-01-01");
  const [backtestRunning, setBacktestRunning] = useState(false);
  const [backtestMessage, setBacktestMessage] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  // Fetch data when strategy changes
  useEffect(() => {
    if (!selectedPortfolio || !selectedStrategy) return;

    const fetchStrategyData = async () => {
      setLoading(true);
      try {
        // Fetch positions
        const { data: positionsData } = await supabase
          .schema("trades")
          .from("open_positions")
          .select("*")
          .eq("portfolio_id", selectedPortfolio.id);

        if (positionsData) {
          setPositions(positionsData);
        }

        // Fetch trades
        const { data: tradesData } = await supabase
          .schema("trades")
          .from("trade_history")
          .select("*")
          .eq("portfolio_id", selectedPortfolio.id)
          .order("executed_at", { ascending: false })
          .limit(50);

        if (tradesData) {
          setTrades(tradesData);
        }

        // Fetch metrics from backend
        const response = await fetch(
          `${API_BASE}/api/v1/portfolio/${selectedStrategy.id}/metrics`,
          { cache: "no-store" }
        );
        if (response.ok) {
          const metricsData = await response.json();
          setMetrics(metricsData);
        }
      } catch (error) {
        console.error("Failed to fetch strategy data:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchStrategyData();
  }, [selectedPortfolio, selectedStrategy, supabase, refreshTick]);

  const runBacktest = async () => {
    if (!selectedStrategy) return;
    setBacktestRunning(true);
    setBacktestMessage(null);
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/backtest/${selectedStrategy.strategy_key}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            start_date: backtestStartDate,
            reset_portfolio: true,
          }),
        }
      );

      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        const detail = payload?.detail ?? "Backtest fehlgeschlagen.";
        throw new Error(String(detail));
      }
      setBacktestMessage("Backtest erfolgreich gestartet/abgeschlossen.");
      setRefreshTick((v) => v + 1);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unbekannter Fehler";
      setBacktestMessage(message);
    } finally {
      setBacktestRunning(false);
    }
  };

  if (strategiesLoading || !selectedStrategy || !selectedPortfolio) {
    return <div className="p-6 text-neutral-400 min-h-screen bg-neutral-950">Loading strategies...</div>;
  }

  const equity = Number(selectedPortfolio.equity_value);
  const starting = Number(selectedPortfolio.starting_cash);
  const totalReturn = ((equity - starting) / starting) * 100;

  return (
    <main className="min-h-screen bg-neutral-950 text-neutral-100 p-6">
      <div className="mb-6 flex items-center justify-between flex-wrap gap-4">
        <h1 className="text-xl font-semibold">SmartMoney Algo-Engine</h1>
        <div className="flex items-center gap-2">
          <Link
            href="/analytics/leaderboard"
            className="rounded-lg border border-neutral-700 px-4 py-2 text-sm text-neutral-300 hover:bg-neutral-800 transition-colors"
          >
            📊 Leaderboard
          </Link>
          <button
            onClick={() => setBacktestEnabled((v) => !v)}
            className={`rounded-lg border px-4 py-2 text-sm transition-colors ${
              backtestEnabled
                ? "border-emerald-600 bg-emerald-700/30 text-emerald-200"
                : "border-neutral-700 text-neutral-300 hover:bg-neutral-800"
            }`}
          >
            {backtestEnabled ? "Backtest: AN" : "Backtest: AUS"}
          </button>
        </div>
      </div>

      {backtestEnabled && (
        <div className="mb-6 rounded-lg border border-neutral-800 bg-neutral-900 p-4">
          <h2 className="text-sm font-medium mb-3">Backtest-Steuerung (Testmodus)</h2>
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="block text-xs text-neutral-400 mb-1">Startdatum</label>
              <input
                type="date"
                value={backtestStartDate}
                onChange={(e) => setBacktestStartDate(e.target.value)}
                className="rounded border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm"
              />
            </div>
            <button
              onClick={runBacktest}
              disabled={backtestRunning || !BACKTEST_SUPPORTED_KEYS.has(selectedStrategy.strategy_key)}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {backtestRunning ? "Backtest läuft..." : "Backtest jetzt starten"}
            </button>
            <p className="text-xs text-neutral-400">
              Unterstützt: <code>strategy_a_legalinsider</code>,{" "}
              <code>strategy_b_unusualvolume</code>,{" "}
              <code>strategy_c_newssentiment</code>,{" "}
              <code>strategy_ab_combined</code>
            </p>
          </div>
          {backtestMessage && <p className="mt-3 text-sm text-neutral-300">{backtestMessage}</p>}
        </div>
      )}

      {/* Strategy Selector */}
      <div className="flex gap-2 flex-wrap mb-6">
        {strategies.map((strategy) => (
          <button
            key={strategy.id}
            onClick={() => setSelectedStrategyId(strategy.id)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              selectedStrategyId === strategy.id
                ? "bg-blue-600 text-white"
                : "bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
            }`}
          >
            {strategy.name}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="p-8 text-center text-neutral-400">Loading data...</div>
      ) : (
        <>
          {/* KPI-Reihe mit echten Metriken */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <KpiCard
              label="Equity"
              value={`$${equity.toLocaleString("en-US", { maximumFractionDigits: 0 })}`}
              positive={equity >= starting}
            />
            <KpiCard
              label="ROI"
              value={`${metrics.roi.toFixed(2)}%`}
              positive={metrics.roi >= 0}
            />
            <KpiCard
              label="Win Rate"
              value={`${metrics.win_rate.toFixed(2)}%`}
            />
            <KpiCard
              label="Max Drawdown"
              value={`${metrics.max_drawdown.toFixed(2)}%`}
              positive={false}
            />
          </div>

          {/* Zusätzliche Metriken Zeile */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <KpiCard
              label="Total Return"
              value={`${totalReturn.toFixed(2)}%`}
              positive={totalReturn >= 0}
            />
            <KpiCard
              label="Sharpe Ratio"
              value={metrics.sharpe_ratio.toFixed(2)}
            />
            <KpiCard
              label="Cash Balance"
              value={`$${Number(selectedPortfolio.cash_balance).toLocaleString("en-US", {
                maximumFractionDigits: 0,
              })}`}
            />
            <KpiCard
              label="Offene Positionen"
              value={String(positions.length)}
            />
          </div>

          {/* Strategy Chart with trade markers and KPI cards */}
          <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4 mb-8">
            <h2 className="text-sm font-medium mb-4">{selectedStrategy.name} — Equity Curve & Trades</h2>
            <StrategyChart
              strategyId={selectedStrategy.id}
              strategyKey={selectedStrategy.strategy_key}
            />
          </div>

          {/* Positionen und Trades */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
              <h2 className="text-sm font-medium mb-4">Offene Positionen</h2>
              <PositionsTable positions={positions} />
            </div>

            <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
              <h2 className="text-sm font-medium mb-4">Letzte Trades</h2>
              <TradesFeed trades={trades} />
            </div>
          </div>
        </>
      )}
    </main>
  );
}
