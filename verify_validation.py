from database.connection import get_connection

connection = get_connection()

print("\n========== TARGET RECORDS ==========")

for row in connection.execute(
    "SELECT record_key, transformed_payload FROM target_records"
):
    print(row["record_key"], row["transformed_payload"])

print("\n========== QUARANTINE RECORDS ==========")

for row in connection.execute(
    "SELECT source_record_id, error_codes, error_details, status "
    "FROM quarantine_records"
):
    print("Record:", row["source_record_id"])
    print("Errors:", row["error_codes"])
    print("Details:", row["error_details"])
    print("Status:", row["status"])
    print("-" * 35)

connection.close()