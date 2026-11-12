import json
from database.connection import get_connection

connection = get_connection()

record = connection.execute("""
    SELECT
        tr.record_key,
        tr.transformed_payload,
        tr.published_at,
        sr.raw_payload
    FROM target_records tr
    JOIN source_records sr
        ON sr.source_record_id = tr.source_record_id
    WHERE tr.record_key = 'EMP010'
""").fetchone()

if record:
    print("\n===== ORIGINAL RECORD =====")
    print(json.dumps(json.loads(record["raw_payload"]), indent=4))

    print("\n===== CORRECTED PUBLISHED RECORD =====")
    print(json.dumps(json.loads(record["transformed_payload"]), indent=4))
else:
    print("EMP010 not found in target records.")

connection.close()