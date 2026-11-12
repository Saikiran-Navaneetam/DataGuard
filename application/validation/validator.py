import json
import uuid

from datetime import datetime, timezone
from database.connection import get_connection


ALLOWED_DEPARTMENTS = {"101", "102", "103"}

RECORD_NAMESPACE = uuid.UUID(
    "a1d65f60-96d2-4c19-8a42-cc7b3c5e8f10"
)


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def validate_employee(record, seen_ids, existing_ids):
    """Validate one employee record and return its errors."""

    errors = []

    employee_id = str(record.get("employee_id") or "").strip()
    employee_name = str(record.get("employee_name") or "").strip()
    department_id = str(record.get("department_id") or "").strip()

    # Required fields
    if not employee_id:
        errors.append(("MISSING_EMPLOYEE_ID", "Employee ID is required."))

    if not employee_name:
        errors.append(("MISSING_EMPLOYEE_NAME", "Employee name is required."))

    if not department_id:
        errors.append(("MISSING_DEPARTMENT_ID", "Department ID is required."))

    # Duplicate employee ID
    if employee_id:
        if employee_id in seen_ids or employee_id in existing_ids:
            errors.append(("DUPLICATE_EMPLOYEE_ID", "Employee ID already exists."))

        seen_ids.add(employee_id)

    # Department validation
    if department_id and department_id not in ALLOWED_DEPARTMENTS:
        errors.append(("INVALID_DEPARTMENT", "Department ID is not recognized."))

    # Salary validation
    try:
        salary = float(record.get("salary"))
        if salary <= 0:
            errors.append(("INVALID_SALARY", "Salary must be greater than zero."))
    except (ValueError, TypeError):
        errors.append(("INVALID_SALARY", "Salary must be numeric."))

    # Age validation
    try:
        age = int(record.get("age"))
        if not 18 <= age <= 65:
            errors.append(("INVALID_AGE", "Age must be between 18 and 65."))
    except (ValueError, TypeError):
        errors.append(("INVALID_AGE", "Age must be a valid integer."))

    # Joining date validation
    try:
        datetime.strptime(str(record.get("joining_date")), "%Y-%m-%d")
    except (ValueError, TypeError):
        errors.append(("INVALID_JOINING_DATE", "Joining date must use YYYY-MM-DD."))

    return errors


def process_source_file(source_file_id):
    """Validate, quarantine and publish records from an ingested file."""

    connection = get_connection()

    try:
        source = connection.execute(
            """
            SELECT run_id, file_name
            FROM source_files
            WHERE source_file_id = ?
            """,
            (source_file_id,)
        ).fetchone()

        if source is None:
            raise ValueError("Source file not found.")

        run_id = source["run_id"]

        records = connection.execute(
            """
            SELECT *
            FROM source_records
            WHERE source_file_id = ?
              AND status = 'RECEIVED'
            ORDER BY source_row_number
            """,
            (source_file_id,)
        ).fetchall()

        if not records:
            return {
                "status": "ALREADY_PROCESSED",
                "message": "No unprocessed records found."
            }

        existing_ids = {
            row["record_key"]
            for row in connection.execute(
                "SELECT record_key FROM target_records"
            ).fetchall()
        }

        seen_ids = set()

        valid_count = 0
        rejected_count = 0

        for row in records:

            record = json.loads(row["raw_payload"])

            errors = validate_employee(
                record,
                seen_ids,
                existing_ids
            )

            record_id = row["source_record_id"]
            now = timestamp()

            if errors:
                error_codes = [error[0] for error in errors]
                error_details = [
                    {"code": code, "message": message}
                    for code, message in errors
                ]

                quarantine_id = str(uuid.uuid4())

                connection.execute(
                    """
                    INSERT INTO quarantine_records (
                        quarantine_id,
                        source_record_id,
                        error_codes,
                        error_details,
                        status,
                        rejected_at
                    )
                    VALUES (?, ?, ?, ?, 'OPEN', ?)
                    """,
                    (
                        quarantine_id,
                        record_id,
                        json.dumps(error_codes),
                        json.dumps(error_details),
                        now
                    )
                )

                connection.execute(
                    """
                    UPDATE source_records
                    SET status = 'QUARANTINED'
                    WHERE source_record_id = ?
                    """,
                    (record_id,)
                )

                connection.execute(
                    """
                    INSERT INTO audit_logs (
                        audit_id, run_id, source_record_id,
                        action, details, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        run_id,
                        record_id,
                        "QUARANTINED",
                        json.dumps(error_details),
                        now
                    )
                )

                rejected_count += 1

            else:
                transformed = {
                    "employee_id": str(record["employee_id"]).strip(),
                    "employee_name": str(record["employee_name"]).strip(),
                    "department_id": int(record["department_id"]),
                    "salary": float(record["salary"]),
                    "age": int(record["age"]),
                    "joining_date": str(record["joining_date"]).strip()
                }

                target_id = str(
                    uuid.uuid5(RECORD_NAMESPACE, record_id)
                )

                connection.execute(
                    """
                    INSERT INTO target_records (
                        target_record_id,
                        source_record_id,
                        record_key,
                        transformed_payload,
                        published_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        target_id,
                        record_id,
                        row["record_key"],
                        json.dumps(transformed),
                        now
                    )
                )

                connection.execute(
                    """
                    UPDATE source_records
                    SET status = 'PUBLISHED'
                    WHERE source_record_id = ?
                    """,
                    (record_id,)
                )

                existing_ids.add(row["record_key"])

                connection.execute(
                    """
                    INSERT INTO audit_logs (
                        audit_id, run_id, source_record_id,
                        action, details, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        run_id,
                        record_id,
                        "PUBLISHED",
                        "Record successfully validated and published.",
                        now
                    )
                )

                valid_count += 1

        completed_at = timestamp()

        final_status = (
            "PARTIAL_SUCCESS" if rejected_count else "SUCCESS"
        )

        connection.execute(
            """
            UPDATE pipeline_runs
            SET status = ?,
                valid_count = ?,
                rejected_count = ?,
                completed_at = ?
            WHERE run_id = ?
            """,
            (
                final_status,
                valid_count,
                rejected_count,
                completed_at,
                run_id
            )
        )

        connection.commit()

        return {
            "status": final_status,
            "file_name": source["file_name"],
            "input_count": len(records),
            "valid_count": valid_count,
            "rejected_count": rejected_count
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()