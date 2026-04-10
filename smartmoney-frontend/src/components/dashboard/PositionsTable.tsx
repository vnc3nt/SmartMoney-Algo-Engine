"use client";

import type { OpenPosition } from "@/types/trading";

interface Props {
  positions: OpenPosition[];   // NUR positions, kein strategies
}

export function PositionsTable({ positions }: Props) {
  if (!positions.length) {
    return (
      <p className="text-sm text-neutral-400 py-8 text-center">
        Keine offenen Positionen.
      </p>
    );
  }
  return (
    <table className="w-full text-sm tabular-nums">
      <thead>
        <tr className="text-left text-xs text-neutral-500 border-b border-neutral-800">
          <th className="pb-2 pr-4">Ticker</th>
          <th className="pb-2 pr-4">Menge</th>
          <th className="pb-2 pr-4">Ø Einstieg</th>
          <th className="pb-2">Marktwert</th>
        </tr>
      </thead>
      <tbody>
        {positions.map((p) => (
          <tr key={p.id} className="border-b border-neutral-800/50">
            <td className="py-2 pr-4 font-medium">{p.ticker}</td>
            <td className="py-2 pr-4">{Number(p.quantity).toFixed(4)}</td>
            <td className="py-2 pr-4">
              ${Number(p.average_entry_price).toFixed(2)}
            </td>
            <td className="py-2">${Number(p.market_value ?? 0).toFixed(2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}