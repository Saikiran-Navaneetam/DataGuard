import json
import sqlite3
import uuid

import pytest

from application.replay import replay_engine


@pytest.fixture
def replay_environment(tmp_path, monkeypatch):
    """Create an isolated database with one quarantined employee."""

    db_path = tmp_path / "test_replay.db"

    # Initialize the database schema.
    from database.connection import SCHEMA_PATH

    connection = sqlite3.connect(db_path)
    connection.executescript(
        SCHEMA_PATH.read_text(encoding="utf-8")
    )

    run_id = str(uuid.uuid4())
    source_file_id = str(uuid.uuid4())
    source_record_id = str(uuid.uuid4())
    quarantine_id = str(uuid.uuid4())

    original_payload = {
        "employee_id": "EMP900",
        "employee_name": "Test Employee",
        "department_id": "101",
        "salary": "-5000",
        "age": "25",
        "joining_date": "2025-01-15"
    }

    connection.execute(
        """
        INSERT INTO pipeline_runs (run_id, status, started_at)
        VALUES (?, 'PARTIAL_SUCCESS', '2026-01-01')
        """,
        (run_id,)
    )

    connection.execute(
        """
        INSERT INTO source_files (
            source_file_id, run_id, file_name, file_format,
            file_path, file_hash, file_size_bytes, uploaded_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_file_id, run_id, "test.csv", "CSV",
            "test.csv", "test_hash", 100, "2026-01-01"
        )
    )

    connection.execute(
        """
        INSERT INTO source_records (
            source_record_id, source_file_id, source_row_number,
            record_key, raw_payload, content_hash, status, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'QUARANTINED', ?)
        """,
        (
            source_record_id, source_file_id, 1, "EMP900",
            json.dumps(original_payload), "content_hash", "2026-01-01"
        )
    )

    connection.execute(
        """
        INSERT INTO quarantine_records (
            quarantine_id, source_record_id, error_codes,
            error_details, status, rejected_at
        )
        VALUES (?, ?, ?, ?, 'OPEN', ?)
        """,
        (
            quarantine_id, source_record_id,
            '["INVALID_SALARY"]',
            '[{"code":"INVALID_SALARY","message":"Salary must be greater than zero."}]',
            "2026-01-01"
        )
    )

    connection.commit()
    connection.close()

    # Redirect replay engine database connections.
    def temporary_connection():
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr(
        replay_engine,
        "get_connection",
        temporary_connection
    )

    return {
        "db_path": db_path,
        "quarantine_id": quarantine_id,
        "source_record_id": source_record_id,
        "original_payload": original_payload
    }


def test_correct_record_saves_correction(replay_environment):
    result = replay_engine.correct_record(
        replay_environment["quarantine_id"],
        {
            **replay_environment["original_payload"],
            "salary": "50000"
        }
    )

    assert result["status"] == "CORRECTED"

    connection = sqlite3.connect(replay_environment["db_path"])

    status = connection.execute(
        "SELECT status FROM quarantine_records WHERE quarantine_id = ?",
        (replay_environment["quarantine_id"],)
    ).fetchone()[0]

    connection.close()

    assert status == "CORRECTED"


def test_successful_replay_publishes_record(replay_environment):
    corrected = {
        **replay_environment["original_payload"],
        "salary": "50000"
    }

    replay_engine.correct_record(
        replay_environment["quarantine_id"],
        corrected
    )

    result = replay_engine.replay_record(
        replay_environment["quarantine_id"]
    )

    assert result["status"] == "SUCCESS"
    assert result["employee_id"] == "EMP900"

    connection = sqlite3.connect(replay_environment["db_path"])

    target_count = connection.execute(
        "SELECT COUNT(*) FROM target_records"
    ).fetchone()[0]

    quarantine_status = connection.execute(
        "SELECT status FROM quarantine_records WHERE quarantine_id = ?",
        (replay_environment["quarantine_id"],)
    ).fetchone()[0]

    source_status = connection.execute(
        "SELECT status FROM source_records WHERE source_record_id = ?",
        (replay_environment["source_record_id"],)
    ).fetchone()[0]

    connection.close()

    assert target_count == 1
    assert quarantine_status == "RESOLVED"
    assert source_status == "PUBLISHED"


def test_unfixed_record_cannot_be_replayed(replay_environment):
    with pytest.raises(ValueError, match="Only corrected records"):
        replay_engine.replay_record(
            replay_environment["quarantine_id"]
        )


def test_original_payload_remains_unchanged(replay_environment):
    corrected = {
        **replay_environment["original_payload"],
        "salary": "50000"
    }

    replay_engine.correct_record(
        replay_environment["quarantine_id"],
        corrected
    )

    connection = sqlite3.connect(replay_environment["db_path"])

    original = connection.execute(
        "SELECT raw_payload FROM source_records WHERE source_record_id = ?",
        (replay_environment["source_record_id"],)
    ).fetchone()[0]

    connection.close()

    original = json.loads(original)

    assert original["salary"] == "-5000"


def test_invalid_correction_fails_replay(replay_environment):
    corrected = {
        **replay_environment["original_payload"],
        "salary": "-1000"
    }

    replay_engine.correct_record(
        replay_environment["quarantine_id"],
        corrected
    )

    result = replay_engine.replay_record(
        replay_environment["quarantine_id"]
    )

    assert result["status"] == "FAILED"

    connection = sqlite3.connect(replay_environment["db_path"])

    target_count = connection.execute(
        "SELECT COUNT(*) FROM target_records"
    ).fetchone()[0]

    quarantine_status = connection.execute(
        "SELECT status FROM quarantine_records WHERE quarantine_id = ?",
        (replay_environment["quarantine_id"],)
    ).fetchone()[0]

    connection.close()

    assert target_count == 0
    assert quarantine_status == "CORRECTED"


def test_successful_record_cannot_be_replayed_twice(replay_environment):
    corrected = {
        **replay_environment["original_payload"],
        "salary": "50000"
    }

    replay_engine.correct_record(
        replay_environment["quarantine_id"],
        corrected
    )

    first_result = replay_engine.replay_record(
        replay_environment["quarantine_id"]
    )

    assert first_result["status"] == "SUCCESS"

    with pytest.raises(ValueError, match="Only corrected records"):
        replay_engine.replay_record(
            replay_environment["quarantine_id"]
        )

    connection = sqlite3.connect(replay_environment["db_path"])

    target_count = connection.execute(
        "SELECT COUNT(*) FROM target_records"
    ).fetchone()[0]

    connection.close()

    assert target_count == 1