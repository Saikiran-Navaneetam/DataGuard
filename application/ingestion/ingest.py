import csv
import json
import hashlib
import uuid

from pathlib import Path
from datetime import datetime, date, timezone

from database.connection import get_connection

from openpyxl import load_workbook

# Supported file formats
SUPPORTED_FORMATS = {".csv", ".json", ".xlsx"}

# Stable namespace for deterministic record IDs
RECORD_NAMESPACE = uuid.UUID("a1d65f60-96d2-4c19-8a42-cc7b3c5e8f10")


def get_timestamp():
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def calculate_file_hash(file_path):
    """Calculate SHA-256 fingerprint of the source file."""

    sha256 = hashlib.sha256()

    with open(file_path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def calculate_content_hash(record):
    """Calculate a deterministic hash for an individual record."""

    content = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        default=str
    )

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def extract_record_key(record, content_hash):
    """Extract a business key when available."""

    possible_keys = (
        "record_id",
        "employee_id",
        "event_id",
        "transaction_id",
        "id"
    )

    for key in possible_keys:
        value = record.get(key)

        if value is not None and str(value).strip():
            return str(value).strip()

    # Fallback for datasets without a known business key
    return content_hash


def read_csv_file(file_path):
    """Read CSV records as dictionaries."""

    with open(file_path, "r", encoding="utf-8-sig", newline="") as file:

        reader = csv.DictReader(file)

        if not reader.fieldnames:
            raise ValueError("CSV file has no header row.")

        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("CSV contains duplicate column names.")

        records = []

        for row in reader:
            if None in row:
                raise ValueError("CSV row contains extra values.")

            records.append(dict(row))

        return records


def read_json_file(file_path):
    """Read a JSON array, object, or JSON Lines file."""

    text = Path(file_path).read_text(encoding="utf-8-sig").strip()

    if not text:
        return []

    try:
        data = json.loads(text)

        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list):
            raise ValueError(
                "JSON must contain an array of objects or a single object."
            )

    except json.JSONDecodeError:
        # Support JSON Lines: one JSON object per line
        data = []

        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue

            try:
                data.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Malformed JSON on line {line_number}: {error.msg}"
                ) from error

    if not all(isinstance(item, dict) for item in data):
        raise ValueError("Every JSON record must be an object.")

    return data


def read_excel_file(file_path):
    """
    Read the first worksheet of an XLSX workbook.
    The first row contains column headers.
    """

    workbook = load_workbook(
        filename=file_path,
        read_only=True,
        data_only=True
    )

    try:
        worksheet = workbook.active

        rows = worksheet.iter_rows(values_only=True)

        headers = next(rows, None)

        if not headers:
            return []

        headers = [
            str(header).strip() if header is not None else ""
            for header in headers
        ]

        if any(not header for header in headers):
            raise ValueError(
                "Excel file contains an empty column header."
            )

        if len(headers) != len(set(headers)):
            raise ValueError(
                "Excel file contains duplicate column names."
            )

        records = []

        for row_number, row in enumerate(rows, start=2):

            # Ignore completely empty rows
            if all(value is None for value in row):
                continue

            if len(row) > len(headers):
                raise ValueError(
                    f"Excel row {row_number} contains extra values."
                )

            record = {}

            for index, header in enumerate(headers):

                value = row[index] if index < len(row) else None

                if isinstance(value, (datetime, date)):
                    value = value.isoformat()

                elif isinstance(value, float) and value.is_integer():
                    value = int(value)

                record[header] = value

            records.append(record)

        return records

    finally:
        workbook.close()

def read_source_file(file_path):
    """Detect file format and load records."""

    extension = Path(file_path).suffix.lower()

    if extension == ".csv":
        return "CSV", read_csv_file(file_path)

    if extension == ".json":
        return "JSON", read_json_file(file_path)

    if extension == ".xlsx":
        return "XLSX", read_excel_file(file_path)

    raise ValueError(
        f"Unsupported file format: {extension or 'unknown'}. "
        "Supported formats: CSV, JSON and XLSX."
    )


def ingest_file(file_path):
    """
    Ingest a local source file into DataGuard.

    Returns run information and ingestion statistics.
    """

    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"Source file not found: {path}")

    file_format = path.suffix.lower().replace(".", "").upper()

    if f".{file_format.lower()}" not in SUPPORTED_FORMATS:
        raise ValueError("Only CSV and JSON files are currently supported.")

    # Identify the source file
    file_hash = calculate_file_hash(path)

    connection = get_connection()

    try:
        # Prevent re-ingestion of an identical file
        existing = connection.execute(
            """
            SELECT source_file_id, run_id
            FROM source_files
            WHERE file_hash = ?
            LIMIT 1
            """,
            (file_hash,)
        ).fetchone()

        if existing:
            return {
                "status": "DUPLICATE_FILE",
                "message": "This file has already been ingested.",
                "existing_run_id": existing["run_id"],
                "source_file_id": existing["source_file_id"]
            }

        # Generate identifiers
        run_id = str(uuid.uuid4())
        source_file_id = str(uuid.uuid4())

        started_at = get_timestamp()

        # Create execution record
        connection.execute(
            """
            INSERT INTO pipeline_runs (
                run_id, status, started_at
            )
            VALUES (?, 'RUNNING', ?)
            """,
            (run_id, started_at)
        )

        # Track uploaded file
        connection.execute(
            """
            INSERT INTO source_files (
                source_file_id, run_id, file_name,
                file_format, file_path, file_hash,
                file_size_bytes, uploaded_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_file_id,
                run_id,
                path.name,
                file_format,
                str(path.resolve()),
                file_hash,
                path.stat().st_size,
                started_at
            )
        )

        connection.commit()

        try:
            # Parse source data
            detected_format, records = read_source_file(path)

            # Insert original records
            for row_number, record in enumerate(records, start=1):

                content_hash = calculate_content_hash(record)

                record_id = str(
                    uuid.uuid5(
                        RECORD_NAMESPACE,
                        f"{file_hash}:{row_number}"
                    )
                )

                record_key = extract_record_key(
                    record,
                    content_hash
                )

                connection.execute(
                    """
                    INSERT INTO source_records (
                        source_record_id,
                        source_file_id,
                        source_row_number,
                        record_key,
                        raw_payload,
                        content_hash,
                        status,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 'RECEIVED', ?)
                    """,
                    (
                        record_id,
                        source_file_id,
                        row_number,
                        record_key,
                        json.dumps(record, default=str),
                        content_hash,
                        get_timestamp()
                    )
                )

            completed_at = get_timestamp()

            connection.execute(
                """
                UPDATE pipeline_runs
                SET status = 'SUCCESS',
                    input_count = ?,
                    completed_at = ?,
                    execution_time_ms =
                        (julianday(?) - julianday(started_at)) * 86400000
                WHERE run_id = ?
                """,
                (
                    len(records),
                    completed_at,
                    completed_at,
                    run_id
                )
            )

            connection.commit()

            return {
                "status": "SUCCESS",
                "run_id": run_id,
                "source_file_id": source_file_id,
                "file_name": path.name,
                "file_format": detected_format,
                "input_count": len(records),
                "file_hash": file_hash
            }

        
        except Exception as error:
            connection.rollback()

            # Remove failed source-file registration.
            # This allows the same file to be uploaded again.
            connection.execute(
                """
                DELETE FROM source_files
                WHERE source_file_id = ?
                """,
                (source_file_id,)
            )

            completed_at = get_timestamp()

            connection.execute(
                """
                UPDATE pipeline_runs
                SET status = 'FAILED',
                    completed_at = ?,
                    error_message = ?
                WHERE run_id = ?
                """,
                (completed_at, str(error), run_id)
            )

            connection.commit()
            raise

    finally:
        connection.close()
