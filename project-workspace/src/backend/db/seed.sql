-- WSB Analysis Tool - Seed Data
-- Contains all 34 system_config entries and 4 portfolio records
-- Uses INSERT OR IGNORE for idempotent execution (safe to re-run)

-- =============================================================================
-- SYSTEM CONFIGURATION (34 entries)
-- =============================================================================

-- System state (2 entries)
INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('system_start_date', DATE('now'), DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('phase', 'paper_trading', DATETIME('now'));

-- Signal thresholds: Quality (2 entries)
INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('quality_min_users', '2', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('quality_min_confidence', '0.6', DATETIME('now'));

-- Signal thresholds: Consensus (3 entries)
INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('consensus_min_comments', '30', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('consensus_min_users', '8', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('consensus_min_alignment', '0.7', DATETIME('now'));

-- Confidence calculation weights (4 entries, must sum to 1.0)
INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('confidence_weight_volume', '0.25', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('confidence_weight_alignment', '0.25', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('confidence_weight_ai_confidence', '0.30', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('confidence_weight_author_trust', '0.20', DATETIME('now'));

-- Author trust calculation (6 entries, see Appendix F)
INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('trust_weight_quality', '0.40', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('trust_weight_accuracy', '0.50', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('trust_weight_tenure', '0.10', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('trust_default_accuracy', '0.50', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('trust_tenure_saturation_days', '30', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('accuracy_ema_weight', '0.30', DATETIME('now'));

-- Stock exit strategy thresholds (10 entries)
INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('stock_stop_loss_pct', '-0.10', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('stock_take_profit_pct', '0.15', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('stock_trailing_stop_pct', '0.07', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('stock_breakeven_trigger_pct', '0.05', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('stock_breakeven_min_days', '5', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('stock_time_stop_base_days', '5', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('stock_time_stop_base_min_gain', '0.05', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('stock_time_stop_extended_days', '7', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('stock_time_stop_max_days', '10', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('stock_take_profit_exit_pct', '0.50', DATETIME('now'));

-- Options exit strategy thresholds (6 entries)
INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('option_stop_loss_pct', '-0.50', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('option_take_profit_pct', '1.00', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('option_trailing_stop_pct', '0.30', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('option_time_stop_days', '10', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('option_expiration_protection_dte', '2', DATETIME('now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('option_take_profit_exit_pct', '0.50', DATETIME('now'));

-- Position management (1 entry)
INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
  ('signal_min_confidence', '0.50', DATETIME('now'));

-- =============================================================================
-- PORTFOLIO INITIALIZATION (4 records)
-- =============================================================================

-- Create unique index on portfolio name to enable idempotent INSERT OR IGNORE
CREATE UNIQUE INDEX IF NOT EXISTS idx_portfolios_name ON portfolios(name);

-- Seed four portfolios: stocks_quality, stocks_consensus, options_quality, options_consensus
-- Each starts with $100,000 in capital, fully available as cash
-- Re-running this file will not create duplicates (INSERT OR IGNORE)

INSERT OR IGNORE INTO portfolios (name, instrument_type, signal_type, starting_capital, current_value, cash_available, created_at)
VALUES
    ('stocks_quality', 'stock', 'quality', 100000.0, 100000.0, 100000.0, CURRENT_TIMESTAMP),
    ('stocks_consensus', 'stock', 'consensus', 100000.0, 100000.0, 100000.0, CURRENT_TIMESTAMP),
    ('options_quality', 'option', 'quality', 100000.0, 100000.0, 100000.0, CURRENT_TIMESTAMP),
    ('options_consensus', 'option', 'consensus', 100000.0, 100000.0, 100000.0, CURRENT_TIMESTAMP);

-- =============================================================================
-- VERIFICATION QUERIES (commented out - uncomment to verify)
-- =============================================================================
-- SELECT COUNT(*) as config_count FROM system_config;  -- Should return 34
-- SELECT COUNT(*) as portfolio_count FROM portfolios;  -- Should return 4
