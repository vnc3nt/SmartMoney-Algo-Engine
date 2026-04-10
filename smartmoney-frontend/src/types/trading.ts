export type ExecutionFrequency = "1m" | "1h" | "1d";
export type SignalSide = "BUY" | "SELL" | "HOLD";
export type TradeSide = "BUY" | "SELL";

export interface Strategy {
  id: string;
  strategy_key: string;
  name: string;
  execution_frequency: ExecutionFrequency;
  is_active: boolean;
}

export interface Portfolio {
  id: string;
  strategy_id: string;
  starting_cash: number;
  cash_balance: number;
  equity_value: number;
}

export interface PerformanceSnapshot {
  id: string;
  portfolio_id: string;
  strategy_id: string;
  snapshot_date: string;
  cash_balance: number;
  market_value: number;
  equity_value: number;
  open_positions_count: number;
  daily_pnl: number;
  total_return_pct: number;
}

export interface OpenPosition {
  id: string;
  portfolio_id: string;
  strategy_id: string;
  ticker: string;
  quantity: number;
  average_entry_price: number;
  last_mark_price?: number;
  market_value?: number;
  opened_at: string;
}

// ← NEU — war bisher nicht definiert
export interface Trade {
  id: string;
  portfolio_id: string;
  strategy_id: string;
  ticker: string;
  side: TradeSide;
  quantity: number;
  signal_price: number;
  executed_price: number;
  gross_notional: number;
  slippage_amount: number;
  realized_pnl?: number;
  reason?: string;
  executed_at: string;
}