import json

from database.connection import get_connection

from application.replay.replay_engine import (
    correct_record,
    replay_record
)


def main():

    connection = get_connection()

    # Find the quarantined negative-salary record.
    quarantine = connection.execute(
        """
        SELECT
            q.quarantine_id,
            q.status,
            q.corrected_payload,
            sr.raw_payload,
            sr.source_record_id
        FROM quarantine_records q
        JOIN source_records sr
            ON sr.source_record_id = q.source_record_id
        WHERE q.error_codes LIKE '%INVALID_SALARY%'
          AND q.status IN ('OPEN', 'CORRECTED')
        ORDER BY sr.source_row_number
        LIMIT 1
        """
    ).fetchone()

    if quarantine is None:
        connection.close()
        print("No pending invalid-salary record found.")
        return

    before_count = connection.execute(
        "SELECT COUNT(*) AS total FROM target_records"
    ).fetchone()["total"]

    connection.close()

    # Retrieve existing correction or original record.
    if quarantine["status"] == "CORRECTED":
        corrected = json.loads(quarantine["corrected_payload"])
    else:
        corrected = json.loads(quarantine["raw_payload"])

        print("\nOriginal salary:", corrected["salary"])

        # Operator correction.
        corrected["salary"] = "50000"

        correction_result = correct_record(
            quarantine["quarantine_id"],
            corrected
        )

        print("\nCORRECTION RESULT:")
        print(correction_result)

    # Replay only the selected record.
    replay_result = replay_record(
        quarantine["quarantine_id"]
    )

    connection = get_connection()

    after_count = connection.execute(
        "SELECT COUNT(*) AS total FROM target_records"
    ).fetchone()["total"]

    connection.close()

    print("\n========== REPLAY REPORT ==========")

    for key, value in replay_result.items():
        print(f"{key}: {value}")

    print("\nTarget records before replay:", before_count)
    print("Target records after replay:", after_count)
    print("Newly published records:", after_count - before_count)

    print("===================================")


if __name__ == "__main__":
    main()