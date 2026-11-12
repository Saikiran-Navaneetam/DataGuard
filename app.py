import os
from dotenv import load_dotenv
load_dotenv()
import csv
import io
import json
from collections import Counter
from application.replay.replay_engine import (
    correct_record,
    replay_record
)
import uuid
from pathlib import Path
from database.connection import get_connection
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file
)
from werkzeug.utils import secure_filename

from application.ingestion.ingest import ingest_file
from application.validation.validator import process_source_file
from application.monitoring.monitor import get_monitoring_report


# --------------------------------------------------
# Flask configuration
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "data" / "uploads"
ALLOWED_EXTENSIONS = {".csv", ".json", ".xlsx"}

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

app = Flask(
    __name__,
    template_folder="presentation/templates",
    static_folder="presentation/static"
)

app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")


# --------------------------------------------------
# Helper function
# --------------------------------------------------

def allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


# --------------------------------------------------
# Dashboard
# --------------------------------------------------

@app.route("/")
def index():

    report = get_monitoring_report()

    metrics = {
        "total_records": report["total_records"],
        "published_records": report["published"],
        "quarantined_records": report["quarantined"],
        "successful_replays": report["replay_success"]
    }

    return render_template(
        "dashboard.html",
        metrics=metrics,
        active_page="overview"
    )

@app.route("/ingestion")
def ingestion_page():

    connection = get_connection()

    try:
        files = connection.execute(
            """
            SELECT
                file_name,
                file_format,
                file_size_bytes,
                uploaded_at,
                run_id
            FROM source_files
            ORDER BY uploaded_at DESC
            """
        ).fetchall()

        return render_template(
            "ingestion.html",
            files=[dict(row) for row in files],
            active_page="ingestion"
        )

    finally:
        connection.close()


@app.route("/monitoring")
def monitoring_page():

    report = get_monitoring_report()

    return render_template(
        "monitoring.html",
        report=report,
        active_page="monitoring"
    )


@app.route("/quality")
def quality_page():

    connection = get_connection()

    try:
        # Overall validation counts
        counts = connection.execute(
            """
            SELECT
                COUNT(CASE WHEN status IN
                    ('PUBLISHED', 'QUARANTINED') THEN 1 END)
                    AS total_evaluated,

                COUNT(CASE WHEN status = 'PUBLISHED' THEN 1 END)
                    AS valid_records,

                COUNT(CASE WHEN status = 'QUARANTINED' THEN 1 END)
                    AS invalid_records

            FROM source_records
            """
        ).fetchone()

        total = counts["total_evaluated"] or 0
        valid = counts["valid_records"] or 0
        invalid = counts["invalid_records"] or 0

        pass_rate = round((valid / total) * 100, 2) if total else 0

        # Retrieve validation errors
        quarantine_rows = connection.execute(
            """
            SELECT
                q.error_codes,
                q.error_details
            FROM quarantine_records q
            """
        ).fetchall()

        error_counts = Counter()
        error_messages = {}

        for row in quarantine_rows:

            details = json.loads(row["error_details"] or "[]")

            for error in details:
                code = error["code"]

                error_counts[code] += 1
                error_messages[code] = error["message"]

        error_categories = [
            {
                "code": code,
                "message": error_messages[code],
                "count": count
            }
            for code, count in error_counts.most_common()
        ]

        # Retrieve record-level results
        records = connection.execute(
            """
            SELECT
                sr.source_record_id,
                sr.source_row_number,
                sr.record_key,
                sr.status,
                q.error_details

            FROM source_records sr

            LEFT JOIN quarantine_records q
                ON q.source_record_id = sr.source_record_id

            WHERE sr.status IN ('PUBLISHED', 'QUARANTINED')

            ORDER BY sr.created_at DESC,
                     sr.source_row_number DESC
            """
        ).fetchall()

        formatted_records = []

        for row in records:

            details = json.loads(row["error_details"] or "[]")

            error_summary = "; ".join(
                error["message"] for error in details
            )

            formatted_records.append({
                "source_record_id": row["source_record_id"],
                "source_row_number": row["source_row_number"],
                "record_key": row["record_key"],
                "status": row["status"],
                "error_summary": error_summary
            })

        quality = {
            "total_evaluated": total,
            "valid_records": valid,
            "invalid_records": invalid,
            "pass_rate": pass_rate,
            "error_categories": error_categories,
            "records": formatted_records
        }

        return render_template(
            "quality.html",
            quality=quality,
            active_page="quality"
        )

    finally:
        connection.close()


@app.route("/quarantine")
def quarantine_page():

    connection = get_connection()

    try:
        # Count quarantine records by status
        status_rows = connection.execute(
            """
            SELECT status, COUNT(*) AS total
            FROM quarantine_records
            GROUP BY status
            """
        ).fetchall()

        summary = {
            "open": 0,
            "corrected": 0,
            "resolved": 0
        }

        for row in status_rows:
            key = row["status"].lower()

            if key in summary:
                summary[key] = row["total"]

        # Retrieve records that need attention
        rows = connection.execute(
            """
            SELECT
                q.quarantine_id,
                q.status,
                q.error_details,
                q.corrected_payload,
                sr.raw_payload,
                sr.record_key,
                sr.source_row_number,
                sf.file_name

            FROM quarantine_records q

            JOIN source_records sr
                ON sr.source_record_id = q.source_record_id

            JOIN source_files sf
                ON sf.source_file_id = sr.source_file_id

            WHERE q.status IN ('OPEN', 'CORRECTED')

            ORDER BY q.rejected_at DESC
            """
        ).fetchall()

        records = []

        for row in rows:

            original = json.loads(row["raw_payload"] or "{}")

            corrected = (
                json.loads(row["corrected_payload"])
                if row["corrected_payload"]
                else original.copy()
            )

            errors = json.loads(row["error_details"] or "[]")

            records.append({
                "quarantine_id": row["quarantine_id"],
                "status": row["status"],
                "record_key": row["record_key"],
                "source_row_number": row["source_row_number"],
                "file_name": row["file_name"],
                "original": original,
                "corrected": corrected,
                "errors": errors
            })

        return render_template(
            "quarantine.html",
            records=records,
            summary=summary,
            active_page="quarantine"
        )

    finally:
        connection.close()


@app.route(
    "/quarantine/<quarantine_id>/correct",
    methods=["POST"]
)
def correct_quarantine_record(quarantine_id):

    try:
        corrected_payload = {
            "employee_id": request.form.get("employee_id", "").strip(),
            "employee_name": request.form.get("employee_name", "").strip(),
            "department_id": request.form.get("department_id", "").strip(),
            "salary": float(request.form.get("salary", "")),
            "age": int(request.form.get("age", "")),
            "joining_date": request.form.get("joining_date", "").strip()
        }

        result = correct_record(
            quarantine_id,
            corrected_payload
        )

        flash(result["message"], "success")

    except (ValueError, TypeError) as error:
        flash(f"Correction failed: {error}", "error")

    except Exception:
        app.logger.exception("Correction operation failed")
        flash("Unable to save the correction. Check the application logs.", "error")

    return redirect(url_for("quarantine_page"))


@app.route(
    "/quarantine/<quarantine_id>/replay",
    methods=["POST"]
)
def replay_quarantine_record(quarantine_id):

    try:
        result = replay_record(quarantine_id)

        if result["status"] == "SUCCESS":
            flash(result["message"], "success")
        else:
            flash(
                "Replay failed. Please review the corrected values and try again.",
                "error"
            )

    except (ValueError, TypeError) as error:
        flash(f"Replay could not be completed: {error}", "error")

    except Exception:
        app.logger.exception("Replay operation failed")
        flash("Replay failed. Check the application logs.", "error")

    return redirect(url_for("quarantine_page"))


@app.route("/replay")
def replay_page():

    connection = get_connection()

    try:
        # Replay summary
        counts = connection.execute(
            """
            SELECT
                COUNT(*) AS total,

                COUNT(CASE
                    WHEN replay_status = 'SUCCESS'
                    THEN 1 END) AS success,

                COUNT(CASE
                    WHEN replay_status = 'FAILED'
                    THEN 1 END) AS failed

            FROM replay_history
            """
        ).fetchone()

        summary = {
            "total": counts["total"] or 0,
            "success": counts["success"] or 0,
            "failed": counts["failed"] or 0
        }

        # Replay execution history
        rows = connection.execute(
            """
            SELECT
                rh.replay_id,
                rh.replay_status,
                rh.attempt_number,
                rh.attempted_at,
                rh.error_message,
                sr.raw_payload

            FROM replay_history rh

            JOIN source_records sr
                ON sr.source_record_id = rh.source_record_id

            ORDER BY rh.attempted_at DESC
            """
        ).fetchall()

        history = []

        for row in rows:

            original = json.loads(row["raw_payload"] or "{}")

            history.append({
                "replay_id": row["replay_id"],
                "status": row["replay_status"],
                "attempt_number": row["attempt_number"],
                "attempted_at": row["attempted_at"],
                "employee_id": original.get("employee_id", "Unknown"),
                "error_message": row["error_message"]
            })

        return render_template(
            "replay.html",
            summary=summary,
            history=history,
            active_page="replay"
        )

    finally:
        connection.close()


@app.route("/reports")
def reports_page():

    report = get_monitoring_report()

    return render_template(
        "reports.html",
        report=report,
        active_page="reports"
    )


@app.route("/reports/export/csv")
def export_report_csv():

    report = get_monitoring_report()

    output = io.StringIO()
    writer = csv.writer(output)

    # Report heading
    writer.writerow(["DATAGUARD - PIPELINE EXECUTION REPORT"])
    writer.writerow([])

    # Overall metrics
    writer.writerow(["Metric", "Value"])
    writer.writerow(["Total Pipeline Runs", report["total_runs"]])
    writer.writerow(["Total Input Records", report["total_records"]])
    writer.writerow(["Published Records", report["published"]])
    writer.writerow(["Quarantined Records", report["quarantined"]])
    writer.writerow(["Target Records", report["target_count"]])
    writer.writerow(["Reconciliation Gap", report["publication_gap"]])
    writer.writerow(["Successful Replays", report["replay_success"]])
    writer.writerow(["Failed Replays", report["replay_failed"]])
    writer.writerow(["Open Quarantine", report["open_quarantine"]])
    writer.writerow(["Resolved Quarantine", report["resolved_quarantine"]])

    writer.writerow([])
    writer.writerow(["PIPELINE EXECUTION HISTORY"])

    writer.writerow([
        "Run ID",
        "Status",
        "Started At",
        "Completed At",
        "Input Count",
        "Published Count",
        "Quarantined Count",
        "Replayed Count"
    ])

    for run in report["runs"]:
        writer.writerow([
            run["run_id"],
            run["status"],
            run["started_at"],
            run["completed_at"],
            run["input_count"],
            run["published_count"],
            run["quarantined_count"],
            run["replayed_count"]
        ])

    # Encode CSV as UTF-8 with BOM for Excel compatibility
    csv_bytes = io.BytesIO(
        output.getvalue().encode("utf-8-sig")
    )

    csv_bytes.seek(0)
    output.close()

    return send_file(
        csv_bytes,
        mimetype="text/csv",
        as_attachment=True,
        download_name="DataGuard_Pipeline_Report.csv"
    )

# --------------------------------------------------
# File Upload and Processing
# --------------------------------------------------

@app.route("/upload", methods=["POST"])
def upload_file():

    if "dataset" not in request.files:
        flash("No file was selected.", "error")
        return redirect(url_for("index"))

    uploaded_file = request.files["dataset"]

    if uploaded_file.filename == "":
        flash("Please select a file.", "error")
        return redirect(url_for("index"))

    if not allowed_file(uploaded_file.filename):
        flash("Unsupported format. Please upload CSV or JSON.", "error")
        return redirect(url_for("index"))

    original_name = secure_filename(uploaded_file.filename)

    # Give each physical upload a unique storage name.
    # The original filename is retained in the ingestion metadata.
    extension = Path(original_name).suffix.lower()
    stored_name = f"{uuid.uuid4().hex}{extension}"
    saved_path = UPLOAD_FOLDER / stored_name

    try:
        uploaded_file.save(saved_path)

        # Step 1: Ingest the uploaded file
        ingestion_result = ingest_file(saved_path)

        if ingestion_result["status"] == "DUPLICATE_FILE":
            flash(
                "This file has already been ingested. "
                "No duplicate processing was performed.",
                "warning"
            )
            return redirect(url_for("index"))

        # Step 2: Validate and publish/quarantine records
        validation_result = process_source_file(
            ingestion_result["source_file_id"]
        )

        flash(
            f"File processed successfully. "
            f"Pipeline status: {validation_result.get('status', 'COMPLETED')}. "
            f"Input records: {ingestion_result['input_count']}.",
            "success"
        )

    except Exception as error:
        app.logger.exception("File processing failed")
        flash(f"File processing failed: {str(error)}", "error")

    return redirect(url_for("index"))


# --------------------------------------------------
# Health Check
# --------------------------------------------------

@app.route("/health")
def health():
    return {
        "status": "healthy",
        "application": "DataGuard"
    }


# --------------------------------------------------
# File Size Error
# --------------------------------------------------

@app.errorhandler(413)
def file_too_large(error):
    flash("File is too large. Maximum upload size is 50 MB.", "error")
    return redirect(url_for("index"))


# --------------------------------------------------
# Run Application
# --------------------------------------------------

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )