
from pathlib import Path
from application.ingestion.ingest import ingest_file

BASE_DIR = Path(__file__).resolve().parent

sample_file = BASE_DIR / "data" / "sample" / "sample_employees.csv"

if __name__ == "__main__":
    result = ingest_file(sample_file)

    print("\n========== DATAGUARD INGESTION ==========")

    for key, value in result.items():
        print(f"{key}: {value}")

    print("=========================================")