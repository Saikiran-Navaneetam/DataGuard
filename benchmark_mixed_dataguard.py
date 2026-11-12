import csv
import json
import random
import sqlite3
import tempfile
import time
from pathlib import Path

from application.ingestion import ingest
from application.validation import validator
from database.connection import SCHEMA_PATH


TOTAL_RECORDS = 100_000
random.seed(42)


def generate_mixed_dataset(file_path):
    departments = ["101", "102", "103"]

    with open(file_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        writer.writerow([
            "employee_id",
            "employee_name",
            "department_id",
            "salary",
            "age",
            "joining_date"
        ])

        for number in range(1, TOTAL_RECORDS + 1):

            # First 90%: valid records
            if number <= 90_000:
                employee_id = f"EMP{number:06d}"
                department_id = random.choice(departments)
                salary = random.randint(25000, 120000)
                age = random.randint(18, 65)

            # Next 5%: invalid salary
            elif number <= 95_000:
                employee_id = f"EMP{number:06d}"
                department_id = random.choice(departments)
                salary = -5000
                age = random.randint(18, 65)

            # Next 3%: invalid department
            elif number <= 98_000:
                employee_id = f"EMP{number:06d}"
                department_id = "999"
                salary = random.randint(25000, 120000)
                age = random.randint(18, 65)

            # Next 1%: invalid age
            elif number <= 99_000:
                employee_id = f"EMP{number:06d}"
                department_id = random.choice(departments)
                salary = random.randint(25000, 120000)
                age = 15

            # Final 1%: duplicate employee IDs
            else:
                duplicate_number = number - 99_000
                employee_id = f"EMP{duplicate_number:06d}"
                department_id = random.choice(departments)
                salary = random.randint(25000, 120000)
                age = random.randint(18, 65)

            writer.writerow([
                employee_id,
                f"Employee {number}",
                department_id,
                salary,
                age,
                "2025-01-15"
            ])


def main():
    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)
        db_path = temp_dir / "mixed_benchmark.db"
        csv_path = temp_dir / "mixed_employees.csv"

        # Initialize isolated database
        connection = sqlite3.connect(db_path)
        connection.executescript(
            SCHEMA_PATH.read_text(encoding="utf-8")
        )
        connection.close()

        def temporary_connection():
            conn = sqlite3.connect(db_path, timeout=60)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 60000")
            return conn

        # Redirect application database connections
        ingest.get_connection = temporary_connection
        validator.get_connection = temporary_connection

        print("Generating 100,000 mixed-quality records...")
        start = time.perf_counter()

        generate_mixed_dataset(csv_path)

        generation_time = time.perf_counter() - start

        print(f"Generation completed in {generation_time:.2f}s")

        print("Starting ingestion...")
        start = time.perf_counter()

        ingestion_result = ingest.ingest_file(csv_path)

        ingestion_time = time.perf_counter() - start

        if ingestion_result["status"] != "SUCCESS":
            raise RuntimeError(ingestion_result)

        print("Starting validation and publication...")
        start = time.perf_counter()

        validation_result = validator.process_source_file(
            ingestion_result["source_file_id"]
        )

        validation_time = time.perf_counter() - start

        # Collect final database metrics
        connection = temporary_connection()

        source_count = connection.execute(
            "SELECT COUNT(*) FROM source_records"
        ).fetchone()[0]

        published = connection.execute(
            "SELECT COUNT(*) FROM target_records"
        ).fetchone()[0]

        quarantined = connection.execute(
            "SELECT COUNT(*) FROM quarantine_records"
        ).fetchone()[0]

        replay_ready = connection.execute(
            "SELECT COUNT(*) FROM quarantine_records WHERE status = 'OPEN'"
        ).fetchone()[0]

        connection.close()

        total_time = ingestion_time + validation_time

        reconciliation_passed = (
            source_count == published + quarantined
            and source_count == TOTAL_RECORDS
        )

        print("\n========== DATAGUARD MIXED BENCHMARK ==========")
        print(f"Input records       : {source_count:,}")
        print(f"Published records   : {published:,}")
        print(f"Quarantined records : {quarantined:,}")
        print(f"Open quarantine     : {replay_ready:,}")
        print(f"Generation time     : {generation_time:.2f}s")
        print(f"Ingestion time      : {ingestion_time:.2f}s")
        print(f"Validation time     : {validation_time:.2f}s")
        print(f"Processing time     : {total_time:.2f}s")

        if total_time > 0:
            print(
                f"Throughput          : "
                f"{source_count / total_time:,.0f} records/sec"
            )

        print(
            f"Reconciliation      : "
            f"{'PASSED' if reconciliation_passed else 'FAILED'}"
        )

        print("================================================")

        if not reconciliation_passed:
            raise AssertionError(
                "Record reconciliation failed."
            )


if __name__ == "__main__":
    main()