"use client";

interface Props {
  label: string;
  value: string;
  sub?: string;
  positive?: boolean;
}

export function KpiCard({ label, value, sub, positive }: Props) {
  return (
    <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4">
      <p className="text-xs text-neutral-500 uppercase tracking-wide">{label}</p>
      <p className={`text-xl font-semibold tabular-nums mt-1 ${positive ? "text-green-600" : "text-red-500"}`}>
        {value}
      </p>
      {sub && <p className="text-xs text-neutral-400 mt-0.5">{sub}</p>}
    </div>
  );
}