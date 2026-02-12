-- WSB Analysis Tool - Database Schema
-- SQLite database schema with foreign key support and WAL mode

-- Enable foreign keys and set journal mode
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- =============================================================================
-- System Configuration Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS system_config (
    key VARCHAR(50) PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP
);

-- =============================================================================
-- Authors Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS authors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    first_seen TIMESTAMP,
    total_comments INT,
    high_quality_comments INT,
    avg_conviction_score FLOAT,
    avg_sentiment_accuracy FLOAT,
    total_upvotes INT,
    flagged_comments INT,
    last_active TIMESTAMP,
    trust_score REAL DEFAULT 0.5
);

-- =============================================================================
-- Reddit Posts Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS reddit_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reddit_id VARCHAR(20) UNIQUE NOT NULL,
    title TEXT,
    selftext TEXT,
    upvotes INT,
    total_comments INT,
    image_urls TEXT,
    image_analysis TEXT,
    fetched_at TIMESTAMP
);

-- =============================================================================
-- Signals Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_date DATE NOT NULL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    ticker VARCHAR(10) NOT NULL,
    signal_type VARCHAR(20) NOT NULL,
    sentiment_score FLOAT,
    prediction VARCHAR(10),
    confidence FLOAT,
    comment_count INT,
    has_reasoning BOOLEAN,
    is_emergence BOOLEAN,
    prior_7d_mentions INT,
    distinct_users INT,
    position_opened BOOLEAN,
    UNIQUE(ticker, signal_type, signal_date)
);

-- =============================================================================
-- Portfolios Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS portfolios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(50),
    instrument_type VARCHAR(10),
    signal_type VARCHAR(20),
    starting_capital FLOAT,
    current_value FLOAT,
    cash_available FLOAT,
    created_at TIMESTAMP
);

-- =============================================================================
-- Positions Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INT NOT NULL,
    signal_id INT NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    instrument_type VARCHAR(10) NOT NULL,
    signal_type VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    confidence FLOAT,
    position_size FLOAT,
    entry_date DATE,
    entry_price FLOAT,
    status VARCHAR(20),
    -- Stock-specific fields (nullable for options)
    shares INT,
    shares_remaining INT,
    -- Monitoring state fields
    stop_loss_price FLOAT,
    take_profit_price FLOAT,
    peak_price FLOAT,
    trailing_stop_active BOOLEAN,
    time_extension VARCHAR(10),
    -- Option-specific fields (nullable for stocks)
    option_type VARCHAR(10),
    strike_price FLOAT,
    expiration_date DATE,
    contracts INT,
    contracts_remaining INT,
    premium_paid FLOAT,
    peak_premium FLOAT,
    underlying_price_at_entry FLOAT,
    -- Closure fields
    exit_date DATE,
    exit_reason VARCHAR(20),
    hold_days INT,
    realized_return_pct FLOAT,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(id),
    FOREIGN KEY (signal_id) REFERENCES signals(id)
);

-- =============================================================================
-- Price History Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open FLOAT,
    high FLOAT,
    low FLOAT,
    close FLOAT,
    fetched_at TIMESTAMP,
    UNIQUE(ticker, date)
);

-- =============================================================================
-- Evaluation Periods Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS evaluation_periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INT NOT NULL,
    period_start DATE,
    period_end DATE,
    instrument_type VARCHAR(10),
    signal_type VARCHAR(20),
    status VARCHAR(20) DEFAULT 'active',
    portfolio_return_pct FLOAT,
    sp500_return_pct FLOAT,
    relative_performance FLOAT,
    beat_benchmark BOOLEAN,
    total_positions_closed INT,
    winning_positions INT,
    losing_positions INT,
    avg_return_pct FLOAT,
    signal_accuracy_pct FLOAT,
    value_at_period_start FLOAT,
    created_at TIMESTAMP,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
);

-- =============================================================================
-- Comments Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_run_id INT NOT NULL,
    post_id INT NOT NULL,
    reddit_id VARCHAR(20) UNIQUE NOT NULL,
    author VARCHAR(50),
    body TEXT,
    created_utc TIMESTAMP,
    score INT,
    parent_comment_id INT,
    depth INT,
    prioritization_score FLOAT,
    sentiment VARCHAR(10),
    sarcasm_detected BOOLEAN,
    has_reasoning BOOLEAN,
    reasoning_summary TEXT,
    ai_confidence FLOAT,
    author_trust_score FLOAT,
    analyzed_at TIMESTAMP,
    parent_chain TEXT,
    FOREIGN KEY (analysis_run_id) REFERENCES analysis_runs(id),
    FOREIGN KEY (post_id) REFERENCES reddit_posts(id) ON DELETE RESTRICT,
    FOREIGN KEY (parent_comment_id) REFERENCES comments(id)
);

-- =============================================================================
-- Analysis Runs Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS analysis_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status VARCHAR(20),
    current_phase INT,
    current_phase_label VARCHAR(50),
    progress_current INT,
    progress_total INT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    signals_created INT,
    positions_opened INT,
    exits_triggered INT,
    warnings TEXT
);

-- =============================================================================
-- Signal Comments Junction Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS signal_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INT NOT NULL,
    comment_id INT NOT NULL,
    created_at TIMESTAMP,
    UNIQUE(signal_id, comment_id),
    FOREIGN KEY (signal_id) REFERENCES signals(id),
    FOREIGN KEY (comment_id) REFERENCES comments(id)
);

-- =============================================================================
-- Comment Tickers Junction Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS comment_tickers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    comment_id INT NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    sentiment VARCHAR(10),
    created_at TIMESTAMP,
    UNIQUE(comment_id, ticker),
    FOREIGN KEY (comment_id) REFERENCES comments(id)
);

-- =============================================================================
-- Position Exits Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS position_exits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INT NOT NULL,
    exit_date DATE,
    exit_price FLOAT,
    exit_reason VARCHAR(20),
    quantity_pct FLOAT,
    shares_exited INT,
    contracts_exited INT,
    realized_pnl FLOAT,
    created_at TIMESTAMP,
    FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE
);

-- =============================================================================
-- Predictions Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    comment_id INT NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    sentiment VARCHAR(10),
    option_type VARCHAR(4),
    analysis_run_id INT NOT NULL,
    strike_price FLOAT,
    expiration_date DATE,
    contract_symbol VARCHAR(50),
    entry_premium FLOAT,
    entry_date DATE,
    contracts INT,
    contracts_remaining INT,
    current_premium FLOAT,
    peak_premium FLOAT,
    trailing_stop_active BOOLEAN DEFAULT FALSE,
    status VARCHAR(20) NOT NULL DEFAULT 'tracking',
    simulated_return_pct FLOAT,
    is_correct BOOLEAN,
    resolved_at TIMESTAMP,
    hitl_override VARCHAR(10),
    hitl_override_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL,
    UNIQUE(comment_id, ticker),
    FOREIGN KEY (comment_id) REFERENCES comments(id),
    FOREIGN KEY (analysis_run_id) REFERENCES analysis_runs(id)
);

-- =============================================================================
-- Prediction Outcomes Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS prediction_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id INT NOT NULL,
    day_offset INT NOT NULL,
    premium FLOAT,
    underlying_price FLOAT,
    recorded_at TIMESTAMP,
    UNIQUE(prediction_id, day_offset),
    FOREIGN KEY (prediction_id) REFERENCES predictions(id)
);

-- =============================================================================
-- Prediction Exits Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS prediction_exits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id INT NOT NULL,
    exit_date DATE,
    exit_premium FLOAT,
    exit_reason VARCHAR(30),
    quantity_pct FLOAT,
    contracts_exited INT,
    simulated_pnl FLOAT,
    created_at TIMESTAMP,
    FOREIGN KEY (prediction_id) REFERENCES predictions(id)
);
