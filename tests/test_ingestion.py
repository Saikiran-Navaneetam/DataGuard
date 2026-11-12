import sqlite3

from application.ingestion import ingest
from pathlib import Path

import pytest

from application.ingestion.ingest import read_source_file


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"


def test_sample_csv_is_read_successfully():
    file_format, records = read_source_file(
        SAMPLE_DIR / "sample_employees.csv"
    )

    assert file_format == "CSV"
    assert isinstance(records, list)
    assert len(records) == 5
    assert records[0]["employee_id"] == "EMP001"


def test_json_file_is_read_successfully(tmp_path):
    json_file = tmp_path / "employees.json"
    json_file.write_text(
        '[{"employee_id": "EMP101", "employee_name": "Test User"}]',
        encoding="utf-8"
    )

    file_format, records = read_source_file(json_file)

    assert file_format == "JSON"
    assert len(records) == 1
    assert records[0]["employee_id"] == "EMP101"


def test_excel_file_is_read_successfully(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")

    excel_file = tmp_path / "employees.xlsx"

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["employee_id", "employee_name"])
    sheet.append(["EMP102", "Excel User"])
    workbook.save(excel_file)

    file_format, records = read_source_file(excel_file)

    assert file_format == "XLSX"
    assert len(records) == 1
    assert records[0]["employee_id"] == "EMP102"


def test_missing_file_raises_error():
    missing_file = SAMPLE_DIR / "does_not_exist.csv"

    with pytest.raises((FileNotFoundError, Exception)):
        read_source_file(missing_file)

def test_duplicate_file_is_not_ingested_twice(tmp_path, monkeypatch):
    # Create an isolated temporary database
    db_path = tmp_path / "test_dataguard.db"

    schema_path = PROJECT_ROOT / "database" / "schema.sql"

    connection = sqlite3.connect(db_path)
    connection.executescript(
        schema_path.read_text(encoding="utf-8")
    )
    connection.close()

    # Make every ingestion connection use the temporary database
    def temporary_connection():
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr(
        ingest,
        "get_connection",
        temporary_connection
    )

    # Create a test CSV file
    test_file = tmp_path / "duplicate_test.csv"

    test_file.write_text(
        "employee_id,employee_name,department_id,salary,age,joining_date\n"
        "EMP900,Test Employee,101,50000,25,2025-01-15\n",
        encoding="utf-8"
    )

    # First ingestion
    first_result = ingest.ingest_file(test_file)

    assert first_result["status"] == "SUCCESS"
    assert first_result["input_count"] == 1

    # Second ingestion of the exact same file
    second_result = ingest.ingest_file(test_file)

    assert second_result["status"] == "DUPLICATE_FILE"

    # Verify database counts
    connection = sqlite3.connect(db_path)

    run_count = connection.execute(
        "SELECT COUNT(*) FROM pipeline_runs"
    ).fetchone()[0]

    file_count = connection.execute(
        "SELECT COUNT(*) FROM source_files"
    ).fetchone()[0]

    record_count = connection.execute(
        "SELECT COUNT(*) FROM source_records"
    ).fetchone()[0]

    connection.close()

    assert run_count == 1
    assert file_count == 1
    assert record_count == 1


def test_failed_ingestion_can_be_retried(tmp_path, monkeypatch):
    # Create an isolated temporary database
    db_path = tmp_path / "retry_test.db"
    schema_path = PROJECT_ROOT / "database" / "schema.sql"

    connection = sqlite3.connect(db_path)
    connection.executescript(
        schema_path.read_text(encoding="utf-8")
    )
    connection.close()

    def temporary_connection():
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr(
        ingest,
        "get_connection",
        temporary_connection
    )

    # Create a malformed JSON file
    test_file = tmp_path / "retry_test.json"
    test_file.write_text("{ invalid json", encoding="utf-8")

    # First attempt should fail
    with pytest.raises(Exception):
        ingest.ingest_file(test_file)

    connection = sqlite3.connect(db_path)

    failed_runs = connection.execute(
        "SELECT COUNT(*) FROM pipeline_runs WHERE status = 'FAILED'"
    ).fetchone()[0]

    source_files = connection.execute(
        "SELECT COUNT(*) FROM source_files"
    ).fetchone()[0]

    connection.close()

    assert failed_runs == 1
    assert source_files == 0

    # Correct the same file and retry
    test_file.write_text(
        '[{"employee_id":"EMP901","employee_name":"Retry User"}]',
        encoding="utf-8"
    )

    retry_result = ingest.ingest_file(test_file)

    assert retry_result["status"] == "SUCCESS"
    assert retry_result["input_count"] == 1

    connection = sqlite3.connect(db_path)

    total_runs = connection.execute(
        "SELECT COUNT(*) FROM pipeline_runs"
    ).fetchone()[0]

    total_files = connection.execute(
        "SELECT COUNT(*) FROM source_files"
    ).fetchone()[0]

    connection.close()

    assert total_runs == 2
    assert total_files == 1
