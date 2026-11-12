
PRAGMA foreign_keys = ON;

-- 1. Pipeline execution tracking
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'RUNNING'
        CHECK (status IN ('RUNNING', 'SUCCESS', 'PARTIAL_SUCCESS', 'FAILED')),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    input_count INTEGER DEFAULT 0,
    valid_count INTEGER DEFAULT 0,
    rejected_count INTEGER DEFAULT 0,
    duplicate_count INTEGER DEFAULT 0,
    error_message TEXT,
    execution_time_ms REAL
);

-- 2. Uploaded source files
CREATE TABLE IF NOT EXISTS source_files (
    source_file_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_format TEXT NOT NULL,
    file_path TEXT,
    file_hash TEXT,
    file_size_bytes INTEGER,
    uploaded_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
);

-- 3. Original ingested records
CREATE TABLE IF NOT EXISTS source_records (
    source_record_id TEXT PRIMARY KEY,
    source_file_id TEXT NOT NULL,
    source_row_number INTEGER NOT NULL,
    record_key TEXT,
    raw_payload TEXT NOT NULL,
    content_hash TEXT,
    status TEXT NOT NULL DEFAULT 'RECEIVED'
        CHECK (status IN (
            'RECEIVED', 'VALIDATING', 'VALIDATED',
            'PUBLISHED', 'QUARANTINED', 'CORRECTED'
        )),
    created_at TEXT NOT NULL,
    UNIQUE (source_file_id, source_row_number),
    FOREIGN KEY (source_file_id)
        REFERENCES source_files(source_file_id)
);

-- 4. Successfully published records
CREATE TABLE IF NOT EXISTS target_records (
    target_record_id TEXT PRIMARY KEY,
    source_record_id TEXT NOT NULL UNIQUE,
    record_key TEXT NOT NULL UNIQUE,
    transformed_payload TEXT NOT NULL,
    published_at TEXT NOT NULL,
    FOREIGN KEY (source_record_id)
        REFERENCES source_records(source_record_id)
);

-- 5. Quarantined records
CREATE TABLE IF NOT EXISTS quarantine_records (
    quarantine_id TEXT PRIMARY KEY,
    source_record_id TEXT NOT NULL UNIQUE,
    error_codes TEXT NOT NULL,
    error_details TEXT NOT NULL,
    corrected_payload TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN'
        CHECK (status IN (
            'OPEN', 'CORRECTED', 'REPLAY_PENDING',
            'RESOLVED', 'REJECTED'
        )),
    rejected_at TEXT NOT NULL,
    corrected_at TEXT,
    FOREIGN KEY (source_record_id)
        REFERENCES source_records(source_record_id)
);

-- 6. Replay attempts and results
CREATE TABLE IF NOT EXISTS replay_history (
    replay_id TEXT PRIMARY KEY,
    quarantine_id TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    replay_status TEXT NOT NULL
        CHECK (replay_status IN ('SUCCESS', 'FAILED')),
    attempt_number INTEGER NOT NULL,
    attempted_at TEXT NOT NULL,
    error_message TEXT,
    FOREIGN KEY (quarantine_id)
        REFERENCES quarantine_records(quarantine_id),
    FOREIGN KEY (source_record_id)
        REFERENCES source_records(source_record_id)
);

-- 7. Record-level audit history
CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id TEXT PRIMARY KEY,
    run_id TEXT,
    source_record_id TEXT,
    action TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id),
    FOREIGN KEY (source_record_id)
        REFERENCES source_records(source_record_id)
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_source_record_status
    ON source_records(status);

CREATE INDEX IF NOT EXISTS idx_source_record_key
    ON source_records(record_key);

CREATE INDEX IF NOT EXISTS idx_quarantine_status
    ON quarantine_records(status);

CREATE INDEX IF NOT EXISTS idx_replay_source
    ON replay_history(source_record_id);

CREATE INDEX IF NOT EXISTS idx_pipeline_status
    ON pipeline_runs(status);

CREATE INDEX IF NOT EXISTS idx_source_file_hash
    ON source_files(file_hash);
