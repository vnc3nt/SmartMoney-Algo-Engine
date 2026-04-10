"use client";

import type { Trade } from "@/types/trading";

interface Props {
  trades: Trade[];
}

export function TradesFeed({ trades }: Props) {
  if (!trades.length) {
    return (
      <p className="text-sm text-neutral-400 py-8 text-center">
        Noch keine Trades ausgeführt.
      </p>
    );
  }
  return (
    <ul className="space-y-2">
      {trades.map((t) => (
        <li
          key={t.id}
          className="flex items-center justify-between text-sm border-b border-neutral-800 pb-2"
        >
          <span className="font-medium">{t.ticker}</span>
          <span
            className={
              t.side === "BUY" ? "text-green-500" : "text-red-400"
            }
          >
            {t.side}
          </span>
          <span className="tabular-nums text-neutral-300">
            ${t.executed_price.toFixed(2)}
          </span>
          <span className="tabular-nums text-neutral-500 text-xs">
            {new Date(t.executed_at).toLocaleDateString("de-DE")}
          </span>
        </li>
      ))}
    </ul>
  );
}