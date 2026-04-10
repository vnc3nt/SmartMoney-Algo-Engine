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
    equity: s.equity_value,
    pnl: s.daily_pnl,
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={chartData}>
        <XAxis dataKey="date" tick={{ fontSize: 12 }} />
        <YAxis
          tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
          tick={{ fontSize: 12 }}
        />
        <Tooltip
          formatter={(value: number) => [
            new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value),
            "Equity"
          ]}
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