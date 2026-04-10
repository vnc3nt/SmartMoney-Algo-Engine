"use client";

import { useRealtimeSnapshots } from "@/hooks/useRealtimePortfolio";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

interface Props {
  strategyId: string;
}

export function EquityChart({ strategyId }: Props) {
  const snapshots = useRealtimeSnapshots(strategyId);

  const chartData = snapshots.map((s) => ({
    date: new Date(s.snapshot_date).toLocaleDateString("de-DE"),
    equity: typeof s.equity_value === "number" ? s.equity_value : parseFloat(String(s.equity_value)),
    pnl: typeof s.daily_pnl === "number" ? s.daily_pnl : parseFloat(String(s.daily_pnl)),
  }));

  const formatCurrency = (value: unknown) => {
    if (typeof value === "number") {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
      }).format(value);
    }
    return String(value);
  };

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={chartData}>
        <XAxis dataKey="date" tick={{ fontSize: 12 }} />
        <YAxis
          tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
          tick={{ fontSize: 12 }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "rgba(0, 0, 0, 0.8)",
            border: "1px solid #333",
            borderRadius: "4px",
          }}
          labelFormatter={(label: unknown) => `Date: ${label}`}
          formatter={formatCurrency}
        />
        <Line
          type="monotone"
          dataKey="equity"
          stroke="var(--color-primary)"
          strokeWidth={2}
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}