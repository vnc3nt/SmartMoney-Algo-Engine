"use client";

import { useStrategies } from "@/hooks/useStrategies";
import { StrategyChart } from "@/components/dashboard/StrategyChart";
import { PositionsTable } from "@/components/dashboard/PositionsTable";
import { TradesFeed } from "@/components/dashboard/TradesFeed";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import Link from "next/link";
import type { OpenPosition, Trade, Strategy, Portfolio } from "@/types/trading";

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
          `http://localhost:8000/api/v1/portfolio/${selectedStrategy.id}/metrics`,
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
  }, [selectedPortfolio, selectedStrategy, supabase]);

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
        <Link
          href="/analytics/leaderboard"
          className="rounded-lg border border-neutral-700 px-4 py-2 text-sm text-neutral-300 hover:bg-neutral-800 transition-colors"
        >
          📊 Leaderboard
        </Link>
      </div>

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