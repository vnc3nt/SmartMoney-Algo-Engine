"use client";                                     // ← muss ganz oben stehen

import { useRealtimeSnapshots } from "@/hooks/useRealtimePortfolio";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

interface Props {
  strategyId: string;                             // ← kein snapshots-Prop mehr
}

export function EquityChart({ strategyId }: Props) {
  const snapshots = useRealtimeSnapshots(strategyId); // ← Live-Daten

  const chartData = snapshots.map((s) => ({
    date: s.snapshot_date,
    equity: Number(s.equity_value),
    pnl: Number(s.daily_pnl),
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
            formatter={(value) => [
                new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(value)),
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