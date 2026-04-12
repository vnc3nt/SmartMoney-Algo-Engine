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
    stop_loss_price NUMERIC(18, 8),
    take_profit_price NUMERIC(18, 8),
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

-- Strategy Allocations table (dynamic allocator state)
CREATE TABLE IF NOT EXISTS trades.strategy_allocations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID NOT NULL UNIQUE REFERENCES trades.strategies(id) ON DELETE CASCADE,
    allocation_fraction NUMERIC(12, 6) NOT NULL DEFAULT 0.100000 CHECK (allocation_fraction >= 0 AND allocation_fraction <= 1),
    is_auto_managed BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_strategy_allocations_strategy ON trades.strategy_allocations(strategy_id);

-- Allocation adjustment audit trail
CREATE TABLE IF NOT EXISTS trades.allocation_adjustments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID NOT NULL REFERENCES trades.strategies(id) ON DELETE CASCADE,
    previous_fraction NUMERIC(12, 6) NOT NULL,
    new_fraction NUMERIC(12, 6) NOT NULL,
    adjustment_reason TEXT NOT NULL,
    metric_return_30d NUMERIC(12, 6),
    metric_max_drawdown NUMERIC(12, 6),
    metric_sharpe NUMERIC(12, 6),
    metric_win_rate NUMERIC(12, 6),
    adjusted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_allocation_adjustments_strategy ON trades.allocation_adjustments(strategy_id);
CREATE INDEX idx_allocation_adjustments_adjusted_at ON trades.allocation_adjustments(adjusted_at DESC);

-- iOS APNs device tokens
CREATE TABLE IF NOT EXISTS trades.device_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(128) NOT NULL,
    platform VARCHAR(20) NOT NULL DEFAULT 'ios',
    device_token VARCHAR(512) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_device_tokens_user_id ON trades.device_tokens(user_id);
CREATE INDEX idx_device_tokens_platform ON trades.device_tokens(platform);

-- Notification queue (for downstream APNs/FCM worker)
CREATE TABLE IF NOT EXISTS trades.notifications_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(128),
    strategy_id UUID REFERENCES trades.strategies(id) ON DELETE SET NULL,
    strategy_key VARCHAR(100) NOT NULL,
    event_type VARCHAR(50) NOT NULL DEFAULT 'trade_executed',
    payload JSONB NOT NULL,
    delivery_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (delivery_status IN ('pending', 'sent', 'failed')),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    delivered_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_notifications_queue_status ON trades.notifications_queue(delivery_status, created_at DESC);
CREATE INDEX idx_notifications_queue_strategy_key ON trades.notifications_queue(strategy_key);
CREATE INDEX idx_notifications_queue_user_id ON trades.notifications_queue(user_id);

-- Persistent strategy signal store
CREATE TABLE IF NOT EXISTS trades.strategy_signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_key VARCHAR(100) NOT NULL,
    ticker VARCHAR(32) NOT NULL,
    side VARCHAR(8) NOT NULL CHECK (side IN ('BUY', 'SELL', 'HOLD')),
    signal_price NUMERIC(18, 8) NOT NULL,
    confidence NUMERIC(12, 6) NOT NULL DEFAULT 0.500000,
    allocation_fraction NUMERIC(12, 6) NOT NULL DEFAULT 0.100000,
    reason TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_strategy_signals_strategy_key_created_at
    ON trades.strategy_signals(strategy_key, created_at DESC);
CREATE INDEX idx_strategy_signals_ticker ON trades.strategy_signals(ticker);

-- Enable RLS (Row Level Security) on the actual tables in trades schema
ALTER TABLE trades.strategies ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades.portfolios ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades.open_positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades.trade_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades.performance_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades.strategy_allocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades.allocation_adjustments ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades.device_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades.notifications_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades.strategy_signals ENABLE ROW LEVEL SECURITY;

-- Role-based policies (production-friendly defaults)
-- Read access for authenticated users
CREATE POLICY "authenticated_read_strategies" ON trades.strategies
    FOR SELECT TO authenticated USING (true);
CREATE POLICY "authenticated_read_portfolios" ON trades.portfolios
    FOR SELECT TO authenticated USING (true);
CREATE POLICY "authenticated_read_open_positions" ON trades.open_positions
    FOR SELECT TO authenticated USING (true);
CREATE POLICY "authenticated_read_trade_history" ON trades.trade_history
    FOR SELECT TO authenticated USING (true);
CREATE POLICY "authenticated_read_performance_snapshots" ON trades.performance_snapshots
    FOR SELECT TO authenticated USING (true);
CREATE POLICY "authenticated_read_strategy_allocations" ON trades.strategy_allocations
    FOR SELECT TO authenticated USING (true);
CREATE POLICY "authenticated_read_allocation_adjustments" ON trades.allocation_adjustments
    FOR SELECT TO authenticated USING (true);
CREATE POLICY "authenticated_read_strategy_signals" ON trades.strategy_signals
    FOR SELECT TO authenticated USING (true);

-- Service role full access for backend jobs
CREATE POLICY "service_all_strategies" ON trades.strategies
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_all_portfolios" ON trades.portfolios
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_all_open_positions" ON trades.open_positions
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_all_trade_history" ON trades.trade_history
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_all_performance_snapshots" ON trades.performance_snapshots
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_all_strategy_allocations" ON trades.strategy_allocations
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_all_allocation_adjustments" ON trades.allocation_adjustments
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_all_device_tokens" ON trades.device_tokens
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_all_notifications_queue" ON trades.notifications_queue
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_all_strategy_signals" ON trades.strategy_signals
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Device tokens: authenticated users can manage their own entries
CREATE POLICY "authenticated_insert_device_tokens" ON trades.device_tokens
    FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "authenticated_update_device_tokens" ON trades.device_tokens
    FOR UPDATE TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_select_device_tokens" ON trades.device_tokens
    FOR SELECT TO authenticated USING (true);
