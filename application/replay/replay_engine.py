import json
import uuid
import sqlite3

from datetime import datetime, timezone

from database.connection import get_connection
from application.validation.validator import validate_employee


RECORD_NAMESPACE = uuid.UUID(
    "a1d65f60-96d2-4c19-8a42-cc7b3c5e8f10"
)


def get_timestamp():
    return datetime.now(timezone.utc).isoformat()


def correct_record(quarantine_id, corrected_payload):
    """
    Save an operator's correction without changing
    the original source payload.
    """

    if not isinstance(corrected_payload, dict):
        raise ValueError("Corrected payload must be a dictionary.")

    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT q.status, s.run_id
            FROM quarantine_records q
            JOIN source_records sr
                ON sr.source_record_id = q.source_record_id
            JOIN source_files s
                ON s.source_file_id = sr.source_file_id
            WHERE q.quarantine_id = ?
            """,
            (quarantine_id,)
        ).fetchone()

        if row is None:
            raise ValueError("Quarantine record not found.")

        if row["status"] not in ("OPEN", "CORRECTED"):
            raise ValueError(
                f"Cannot correct a record with status {row['status']}."
            )

        now = get_timestamp()

        connection.execute(
            """
            UPDATE quarantine_records
            SET corrected_payload = ?,
                status = 'CORRECTED',
                corrected_at = ?
            WHERE quarantine_id = ?
            """,
            (
                json.dumps(corrected_payload, default=str),
                now,
                quarantine_id
            )
        )

        connection.execute(
            """
            INSERT INTO audit_logs (
                audit_id, run_id, source_record_id,
                action, details, created_at
            )
            SELECT ?, ?, source_record_id, ?, ?, ?
            FROM quarantine_records
            WHERE quarantine_id = ?
            """,
            (
                str(uuid.uuid4()),
                row["run_id"],
                "RECORD_CORRECTED",
                "Operator supplied corrected record values.",
                now,
                quarantine_id
            )
        )

        connection.commit()

        return {
            "status": "CORRECTED",
            "quarantine_id": quarantine_id,
            "message": "Correction saved successfully."
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def replay_record(quarantine_id):
    """
    Revalidate and replay only the selected quarantined record.
    """

    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT
                q.*,
                sr.source_record_id,
                sr.record_key,
                sr.source_file_id,
                sf.run_id
            FROM quarantine_records q
            JOIN source_records sr
                ON sr.source_record_id = q.source_record_id
            JOIN source_files sf
                ON sf.source_file_id = sr.source_file_id
            WHERE q.quarantine_id = ?
            """,
            (quarantine_id,)
        ).fetchone()

        if row is None:
            raise ValueError("Quarantine record not found.")

        if row["status"] != "CORRECTED":
            raise ValueError(
                "Only corrected records can be replayed."
            )

        corrected_payload = json.loads(row["corrected_payload"])

        previous_attempts = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM replay_history
            WHERE quarantine_id = ?
            """,
            (quarantine_id,)
        ).fetchone()["total"]

        attempt_number = previous_attempts + 1

        seen_ids = set()

        existing_ids = {
            item["record_key"]
            for item in connection.execute(
                "SELECT record_key FROM target_records"
            ).fetchall()
        }

        errors = validate_employee(
            corrected_payload,
            seen_ids,
            existing_ids
        )

        now = get_timestamp()
        replay_id = str(uuid.uuid4())
        source_record_id = row["source_record_id"]

        # Revalidation failed: keep record quarantined.
        if errors:

            error_message = json.dumps([
                {"code": code, "message": message}
                for code, message in errors
            ])

            connection.execute(
                """
                INSERT INTO replay_history (
                    replay_id, quarantine_id, source_record_id,
                    replay_status, attempt_number,
                    attempted_at, error_message
                )
                VALUES (?, ?, ?, 'FAILED', ?, ?, ?)
                """,
                (
                    replay_id,
                    quarantine_id,
                    source_record_id,
                    attempt_number,
                    now,
                    error_message
                )
            )

            connection.commit()

            return {
                "status": "FAILED",
                "attempt_number": attempt_number,
                "errors": error_message
            }

        # Prepare corrected target record.
        transformed = {
            "employee_id": str(
                corrected_payload["employee_id"]
            ).strip(),
            "employee_name": str(
                corrected_payload["employee_name"]
            ).strip(),
            "department_id": int(
                corrected_payload["department_id"]
            ),
            "salary": float(corrected_payload["salary"]),
            "age": int(corrected_payload["age"]),
            "joining_date": str(
                corrected_payload["joining_date"]
            ).strip()
        }

        target_id = str(
            uuid.uuid5(RECORD_NAMESPACE, source_record_id)
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
                source_record_id,
                transformed["employee_id"],
                json.dumps(transformed),
                now
            )
        )

        # Mark source record as published.
        connection.execute(
            """
            UPDATE source_records
            SET status = 'PUBLISHED'
            WHERE source_record_id = ?
            """,
            (source_record_id,)
        )

        # Resolve quarantine record.
        connection.execute(
            """
            UPDATE quarantine_records
            SET status = 'RESOLVED'
            WHERE quarantine_id = ?
            """,
            (quarantine_id,)
        )

        # Record successful replay.
        connection.execute(
            """
            INSERT INTO replay_history (
                replay_id, quarantine_id, source_record_id,
                replay_status, attempt_number, attempted_at
            )
            VALUES (?, ?, ?, 'SUCCESS', ?, ?)
            """,
            (
                replay_id,
                quarantine_id,
                source_record_id,
                attempt_number,
                now
            )
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
                row["run_id"],
                source_record_id,
                "RECORD_REPLAYED",
                "Corrected record successfully published.",
                now
            )
        )

        connection.commit()

        return {
            "status": "SUCCESS",
            "replay_id": replay_id,
            "attempt_number": attempt_number,
            "employee_id": transformed["employee_id"],
            "message": "Corrected record successfully published."
        }

    except sqlite3.IntegrityError as error:
        connection.rollback()
        raise ValueError(
            f"Replay could not be published: {error}"
        ) from error

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()