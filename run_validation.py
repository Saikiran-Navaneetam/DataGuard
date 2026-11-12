from pathlib import Path

from application.ingestion.ingest import ingest_file
from application.validation.validator import process_source_file


BASE_DIR = Path(__file__).resolve().parent

sample_file = (
    BASE_DIR / "data" / "sample" / "sample_employees_mixed.csv"
)


if __name__ == "__main__":

    print("\n========== DATAGUARD VALIDATION ==========")

    ingestion_result = ingest_file(sample_file)

    print("\nINGESTION RESULT:")
    print(ingestion_result)

    if ingestion_result["status"] not in ("SUCCESS", "DUPLICATE_FILE"):
        raise RuntimeError("Source ingestion failed.")

    source_file_id = ingestion_result["source_file_id"]

    validation_result = process_source_file(source_file_id)

    print("\nVALIDATION RESULT:")

    for key, value in validation_result.items():
        print(f"{key}: {value}")

    print("==========================================")