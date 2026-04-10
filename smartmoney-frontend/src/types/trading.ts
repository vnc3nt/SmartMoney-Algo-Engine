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

export interface StrategyMetrics {
  return_1d: number;
  return_1w: number;
  return_1m: number;
  return_1y: number;
  return_all: number;
  win_rate: number;
  max_drawdown: number;
  total_trades: number;
}

export interface StrategyLeaderboardEntry extends StrategyMetrics {
  strategy_key: string;
  name: string;
  execution_frequency: ExecutionFrequency;
  portfolio_id: string;
  starting_cash: number;
  equity_value: number;
  cash_balance: number;
  snapshot_count: number;
}

export interface BacktestRequest {
  start_date: string;
  end_date?: string;
  tickers?: string[];
  reset_portfolio?: boolean;
}

export interface BacktestSnapshotEntry {
  date: string;
  equity: number;
  cash: number;
  market_value: number;
  daily_pnl: number;
  total_return_pct: number;
}

export interface BacktestResult {
  strategy_key: string;
  start_date: string;
  end_date: string;
  tickers: string[];
  total_trading_days: number;
  total_signals: number;
  total_trades: number;
  starting_cash: number;
  final_equity: number;
  total_return_pct: number;
  max_drawdown_pct: number;
  win_rate_pct: number;
  daily_snapshots: BacktestSnapshotEntry[];
}
