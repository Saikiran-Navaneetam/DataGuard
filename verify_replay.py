from database.connection import get_connection

connection = get_connection()

print("\n========== REPLAY HISTORY ==========")

history = connection.execute("""
    SELECT
        replay_id,
        source_record_id,
        replay_status,
        attempt_number,
        attempted_at,
        error_message
    FROM replay_history
    ORDER BY attempted_at DESC
""").fetchall()

for row in history:
    print(dict(row))

print("\n========== QUARANTINE STATUS ==========")

records = connection.execute("""
    SELECT
        q.quarantine_id,
        q.status,
        sr.record_key
    FROM quarantine_records q
    JOIN source_records sr
        ON sr.source_record_id = q.source_record_id
""").fetchall()

for row in records:
    print(dict(row))

print("\n========== TARGET COUNT ==========")

count = connection.execute(
    "SELECT COUNT(*) AS total FROM target_records"
).fetchone()

print("Published records:", count["total"])

connection.close()