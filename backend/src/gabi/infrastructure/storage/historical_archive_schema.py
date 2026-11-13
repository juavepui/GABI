"""Historical archive schema; initialization belongs to explicit writes."""
SCHEMA = """
CREATE TABLE IF NOT EXISTS historical_sources (
 source_id TEXT PRIMARY KEY, metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS historical_membership (
 source_id TEXT NOT NULL, date TEXT NOT NULL, tickers TEXT NOT NULL,
 PRIMARY KEY(source_id,date)
);
CREATE TABLE IF NOT EXISTS historical_issuer_candidates (
 source_id TEXT NOT NULL, symbol TEXT NOT NULL, cik TEXT NOT NULL,
 name TEXT, date_added TEXT, date_removed TEXT, observed_from TEXT,
 PRIMARY KEY(source_id,symbol,cik,date_added,observed_from)
);
CREATE TABLE IF NOT EXISTS historical_prices (
 source_id TEXT NOT NULL, symbol TEXT NOT NULL, date TEXT NOT NULL,
 open REAL, high REAL, low REAL, close REAL, adj_close REAL, volume REAL,
 close_basis TEXT NOT NULL,
 PRIMARY KEY(source_id,symbol,date)
);
CREATE TABLE IF NOT EXISTS historical_facts (
 source_id TEXT NOT NULL, candidate_symbol TEXT NOT NULL, cik TEXT NOT NULL,
 record_key TEXT NOT NULL, filed_date TEXT NOT NULL, payload_json TEXT NOT NULL,
 PRIMARY KEY(source_id,candidate_symbol,cik,record_key)
);
CREATE TABLE IF NOT EXISTS historical_identity_intervals (
 source_id TEXT NOT NULL, symbol TEXT NOT NULL, cik TEXT NOT NULL,
 valid_from TEXT NOT NULL, valid_to TEXT NOT NULL,
 status TEXT NOT NULL, evidence_count INTEGER NOT NULL,
 first_filed TEXT, last_filed TEXT, source_refs_json TEXT NOT NULL,
 PRIMARY KEY(source_id,symbol,cik,valid_from,valid_to)
);
CREATE INDEX IF NOT EXISTS idx_historical_identity_interval_symbol
 ON historical_identity_intervals(symbol,valid_from,valid_to);
"""
