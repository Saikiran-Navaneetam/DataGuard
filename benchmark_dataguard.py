import csv
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

BASE_DIR = Path(__file__).resolve().parent


def generate_dataset(file_path):
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
            writer.writerow([
                f"EMP{number:06d}",
                f"Employee {number}",
                random.choice(departments),
                random.randint(25000, 120000),
                random.randint(18, 65),
                "2025-01-15"
            ])


def main():
    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)

        # Create an isolated benchmark database.
        db_path = temp_dir / "benchmark.db"

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

        ingest.get_connection = temporary_connection
        validator.get_connection = temporary_connection

        csv_path = temp_dir / "benchmark_employees.csv"

        print(f"Generating {TOTAL_RECORDS:,} records...")
        start = time.perf_counter()

        generate_dataset(csv_path)

        generation_time = time.perf_counter() - start

        print(f"Generation completed in {generation_time:.2f}s")

        print("Starting ingestion...")
        start = time.perf_counter()

        result = ingest.ingest_file(csv_path)

        ingestion_time = time.perf_counter() - start

        if result["status"] != "SUCCESS":
            raise RuntimeError(result)

        print("Starting validation and publication...")
        start = time.perf_counter()

        validation_result = validator.process_source_file(
            result["source_file_id"]
        )

        validation_time = time.perf_counter() - start

        connection = temporary_connection()

        published = connection.execute(
            "SELECT COUNT(*) FROM target_records"
        ).fetchone()[0]

        quarantined = connection.execute(
            "SELECT COUNT(*) FROM quarantine_records"
        ).fetchone()[0]

        source_count = connection.execute(
            "SELECT COUNT(*) FROM source_records"
        ).fetchone()[0]

        connection.close()

        total_time = ingestion_time + validation_time

        print("\n========== DATAGUARD BENCHMARK ==========")
        print(f"Input records       : {source_count:,}")
        print(f"Published records   : {published:,}")
        print(f"Quarantined records : {quarantined:,}")
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
            f"{'PASSED' if source_count == published + quarantined else 'FAILED'}"
        )

        print("=========================================")


if __name__ == "__main__":
    main()
