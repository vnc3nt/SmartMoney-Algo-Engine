import { createClient } from "@/lib/supabase/server";
import { EquityChart } from "@/components/dashboard/EquityChart";
import { PositionsTable } from "@/components/dashboard/PositionsTable";
import { TradesFeed } from "@/components/dashboard/TradesFeed";
import { KpiCard } from "@/components/dashboard/KpiCard";

export default async function DashboardPage() {
  const supabase = await createClient();

  // Strategien laden
  const { data: strategies } = await supabase
    .schema("trades")
    .from("strategies")
    .select("*")
    .eq("is_active", true);

  // Portfolios laden
  const { data: portfolios } = await supabase
    .schema("trades")
    .from("portfolios")
    .select("*");

  // Letzte Snapshots pro Strategie
  const { data: latestSnapshots } = await supabase
    .schema("trades")
    .from("performance_snapshots")
    .select("*")
    .order("snapshot_date", { ascending: false })
    .limit(10);

  // Offene Positionen
  const { data: positions } = await supabase
    .schema("trades")
    .from("open_positions")
    .select("*");

  // Trade History
  const { data: trades } = await supabase
    .schema("trades")
    .from("trade_history")
    .select("*")
    .order("executed_at", { ascending: false })
    .limit(50);

  const strategyList = strategies ?? [];
  const portfolioList = portfolios ?? [];
  const positionList = positions ?? [];
  const tradeList = trades ?? [];

  // Ersten Portfolio-Eintrag für KPIs nehmen
  const firstPortfolio = portfolioList[0];
  const equity = firstPortfolio ? Number(firstPortfolio.equity_value) : 100000;
  const starting = firstPortfolio ? Number(firstPortfolio.starting_cash) : 100000;
  const totalReturn = ((equity - starting) / starting) * 100;

  return (
    <main className="min-h-screen bg-neutral-950 text-neutral-100 p-6">
      <h1 className="text-xl font-semibold mb-6">SmartMoney Algo-Engine</h1>

      {/* KPI-Reihe */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <KpiCard
          label="Equity"
          value={`$${equity.toLocaleString("en-US", { maximumFractionDigits: 0 })}`}
          positive={equity >= starting}
        />
        <KpiCard
          label="Total Return"
          value={`${totalReturn.toFixed(2)}%`}
          positive={totalReturn >= 0}
        />
        <KpiCard
          label="Strategien aktiv"
          value={String(strategyList.length)}
        />
        <KpiCard
          label="Offene Positionen"
          value={String(positionList.length)}
        />
      </div>

      {/* Charts pro Strategie */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        {strategyList.map((strategy) => {
          const portfolio = portfolioList.find(
            (p) => p.strategy_id === strategy.id
          );
          return (
            <div
              key={strategy.id}
              className="rounded-lg border border-neutral-800 bg-neutral-900 p-4"
            >
              <h2 className="text-sm font-medium mb-1">{strategy.name}</h2>
              <p className="text-xs text-neutral-500 mb-4">
                Frequenz: {strategy.execution_frequency}
              </p>
              {/* EquityChart bekommt nur strategyId — lädt Daten selbst via Realtime-Hook */}
              <EquityChart strategyId={strategy.id} />
              {portfolio && (
                <p className="text-xs text-neutral-400 mt-2 tabular-nums">
                  Cash:{" "}
                  {Number(portfolio.cash_balance).toLocaleString("en-US", {
                    style: "currency",
                    currency: "USD",
                  })}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {/* Positionen und Trades */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
          <h2 className="text-sm font-medium mb-4">Offene Positionen</h2>
          {/* PositionsTable bekommt nur positions — kein strategies-Prop */}
          <PositionsTable positions={positionList} />
        </div>

        <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
          <h2 className="text-sm font-medium mb-4">Letzte Trades</h2>
          {/* TradesFeed bekommt nur trades — kein strategies-Prop */}
          <TradesFeed trades={tradeList} />
        </div>
      </div>
    </main>
  );
}