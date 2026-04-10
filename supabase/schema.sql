-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create the trades schema
CREATE SCHEMA IF NOT EXISTS trades;

-- Strategies table
CREATE TABLE IF NOT EXISTS trades.strategies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_key VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(150) NOT NULL,
    description TEXT,
    execution_frequency VARCHAR(10) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_strategies_key ON trades.strategies(strategy_key);

-- Portfolios table
CREATE TABLE IF NOT EXISTS trades.portfolios (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID NOT NULL UNIQUE REFERENCES trades.strategies(id) ON DELETE CASCADE,
    base_currency VARCHAR(10) NOT NULL DEFAULT 'USD',
    starting_cash NUMERIC(18, 4) NOT NULL DEFAULT 100000.0000,
    cash_balance NUMERIC(18, 4) NOT NULL DEFAULT 100000.0000,
    equity_value NUMERIC(18, 4) NOT NULL DEFAULT 100000.0000,
    slippage_bps INTEGER NOT NULL DEFAULT 10,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_portfolios_strategy ON trades.portfolios(strategy_id);

-- Open Positions table
CREATE TABLE IF NOT EXISTS trades.open_positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    portfolio_id UUID NOT NULL REFERENCES trades.portfolios(id) ON DELETE CASCADE,
    strategy_id UUID NOT NULL REFERENCES trades.strategies(id) ON DELETE CASCADE,
    ticker VARCHAR(32) NOT NULL,
    quantity NUMERIC(18, 8) NOT NULL,
    average_entry_price NUMERIC(18, 8) NOT NULL,
    last_mark_price NUMERIC(18, 8),
    market_value NUMERIC(18, 4),
    opened_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(portfolio_id, ticker)
);

CREATE INDEX idx_open_positions_portfolio ON trades.open_positions(portfolio_id);
CREATE INDEX idx_open_positions_strategy ON trades.open_positions(strategy_id);
CREATE INDEX idx_open_positions_ticker ON trades.open_positions(ticker);

-- Trade History table
CREATE TABLE IF NOT EXISTS trades.trade_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    portfolio_id UUID NOT NULL REFERENCES trades.portfolios(id) ON DELETE CASCADE,
    strategy_id UUID NOT NULL REFERENCES trades.strategies(id) ON DELETE CASCADE,
    ticker VARCHAR(32) NOT NULL,
    side VARCHAR(8) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    quantity NUMERIC(18, 8) NOT NULL,
    signal_price NUMERIC(18, 8) NOT NULL,
    executed_price NUMERIC(18, 8) NOT NULL,
    gross_notional NUMERIC(18, 4) NOT NULL,
    slippage_amount NUMERIC(18, 4) NOT NULL DEFAULT 0,
    fees NUMERIC(18, 4) NOT NULL DEFAULT 0,
    realized_pnl NUMERIC(18, 4),
    reason TEXT,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_trade_history_portfolio ON trades.trade_history(portfolio_id);
CREATE INDEX idx_trade_history_strategy ON trades.trade_history(strategy_id);
CREATE INDEX idx_trade_history_ticker ON trades.trade_history(ticker);
CREATE INDEX idx_trade_history_executed_at ON trades.trade_history(executed_at DESC);

-- Performance Snapshots table
CREATE TABLE IF NOT EXISTS trades.performance_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    portfolio_id UUID NOT NULL REFERENCES trades.portfolios(id) ON DELETE CASCADE,
    strategy_id UUID NOT NULL REFERENCES trades.strategies(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    cash_balance NUMERIC(18, 4) NOT NULL,
    market_value NUMERIC(18, 4) NOT NULL,
    equity_value NUMERIC(18, 4) NOT NULL,
    open_positions_count INTEGER NOT NULL DEFAULT 0,
    daily_pnl NUMERIC(18, 4) NOT NULL DEFAULT 0,
    total_return_pct NUMERIC(12, 6) NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(portfolio_id, snapshot_date)
);

CREATE INDEX idx_performance_snapshots_portfolio ON trades.performance_snapshots(portfolio_id);
CREATE INDEX idx_performance_snapshots_strategy ON trades.performance_snapshots(strategy_id);
CREATE INDEX idx_performance_snapshots_date ON trades.performance_snapshots(snapshot_date DESC);

-- Enable RLS (Row Level Security) for Supabase
ALTER TABLE trades.strategies ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades.portfolios ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades.open_positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades.trade_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades.performance_snapshots ENABLE ROW LEVEL SECURITY;
