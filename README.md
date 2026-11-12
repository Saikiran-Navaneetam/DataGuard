# DataGuard — Intelligent Data Quality, Quarantine & Recovery Platform

**A Python-based data pipeline platform designed to ingest, validate, transform, monitor, quarantine, and recover data with reliability and traceability.**

![Python](https://img.shields.io/badge/Python-3.13-blue)
![Flask](https://img.shields.io/badge/Framework-Flask-black)
![Database](https://img.shields.io/badge/Database-SQLite-blue)
![Testing](https://img.shields.io/badge/Tests-24%20Passing-brightgreen)
![Status](https://img.shields.io/badge/Project-Completed-success)

---

## 1. Overview

DataGuard is an intelligent data quality and recovery platform developed to address common challenges in data engineering workflows.

Traditional data pipelines can fail when they encounter malformed records, missing values, duplicate entries, invalid business data, or inconsistent references. These issues can lead to inaccurate reporting, incomplete datasets, and repeated processing.

DataGuard provides a structured pipeline that identifies data quality issues, separates invalid records from valid records, and allows operators to correct and replay rejected records without reprocessing successfully published data.

The platform provides a web-based interface for ingestion, monitoring, data quality analysis, quarantine management, replay operations, and reporting.

## 2. Key Features

### Data Ingestion
- Upload CSV, JSON, and Excel (.xlsx) files.
- Parse and register incoming datasets.
- Generate unique pipeline execution IDs.
- Calculate SHA-256 file hashes.
- Detect identical files and prevent duplicate ingestion.
- Preserve original source records.

### Data Validation
- Check required employee fields.
- Detect duplicate employee IDs.
- Validate department IDs.
- Validate salary values.
- Enforce employee age limits.
- Validate joining-date formats.

### Data Transformation and Publication
- Transform validated employee records into structured target records.
- Publish valid records to the target database.
- Maintain source-to-target traceability.

### Quarantine Management
- Automatically isolate invalid records.
- Store validation error codes and descriptions.
- Preserve original source data.
- Allow operators to correct rejected records.

### Controlled Replay and Recovery
- Revalidate corrected records before publication.
- Replay individual corrected records.
- Prevent replay of records that are not corrected.
- Maintain replay attempt history.
- Preserve original source payloads.
- Resolve quarantine records after successful publication.

### Monitoring and Reporting
- Monitor pipeline execution history.
- Track total input, published, and quarantined records.
- Monitor replay success and failure.
- View data quality metrics.
- Export reports as CSV.
- Print or save reports as PDF through the browser.

## 3. Technology Stack

| Component | Technology |
|---|---|
| Programming language | Python |
| Web framework | Flask |
| Frontend | HTML, CSS, JavaScript, Bootstrap |
| Database | SQLite |
| Excel processing | OpenPyXL |
| Data formats | CSV, JSON, XLSX |
| Testing framework | Pytest |
| Version control | Git |

## 4. System Architecture

DataGuard follows a three-tier logical architecture.

### Presentation Layer
Provides the web interface through Flask, HTML, CSS, JavaScript, and Bootstrap.

### Application Layer
Contains the modular Python components responsible for ingestion, validation, transformation, quarantine, replay, and monitoring.

### Data Layer
Uses SQLite to maintain source records, target records, pipeline execution details, quarantine records, replay history, and audit logs.

### Architecture Flow

```text
              USER
                |
                v
       FLASK WEB INTERFACE
                |
                v
        APPLICATION LAYER
                |
       +--------+---------+
       |                  |
       v                  v
  INGESTION            VALIDATION
       |                  |
       v                  v
 SOURCE RECORDS      VALID RECORDS
       |                  |
       |                  v
       |             TRANSFORMATION
       |                  |
       |                  v
       |             TARGET RECORDS
       |
       v
   QUARANTINE
       |
       v
  DATA CORRECTION
       |
       v
  REVALIDATION
       |
       v
  CONTROLLED REPLAY
       |
       v
   TARGET RECORDS

       DATABASE
          |
          v
  MONITORING & REPORTS
```

## 5. Database Design

DataGuard uses SQLite with seven core relational tables.

| Table | Purpose |
|---|---|
| pipeline_runs | Tracks pipeline executions and their statuses |
| source_files | Stores uploaded file metadata and hashes |
| source_records | Preserves original ingested records |
| target_records | Stores successfully published records |
| quarantine_records | Stores rejected records and correction details |
| replay_history | Tracks replay attempts and outcomes |
| audit_logs | Maintains record-level operational history |

Foreign keys and database indexes support referential integrity and frequently used queries.

## 6. Project Structure

```text
DataGuard/
│
├── app.py
├── benchmark_dataguard.py
├── benchmark_mixed_dataguard.py
├── requirements.txt
├── README.md
├── .env.example
├── .gitignore
│
├── application/
│   ├── ingestion/
│   ├── validation/
│   ├── transformation/
│   ├── quarantine/
│   ├── replay/
│   └── monitoring/
│
├── database/
│   ├── connection.py
│   ├── schema.sql
│   └── dataguard.db
│
├── presentation/
│   ├── templates/
│   └── static/
│
├── data/
│   ├── sample/
│   ├── uploads/
│   └── outputs/
│
├── tests/
│   ├── test_ingestion.py
│   ├── test_validation.py
│   └── test_replay.py
│
├── config/
└── docs/
```

## 7. Installation and Setup

### Prerequisites

- Python 3.10 or later.
- Visual Studio Code or another Python IDE.
- Git (optional).

### Step 1: Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd DataGuard
```

### Step 2: Create a virtual environment

```bash
python -m venv venv
```

### Step 3: Activate the virtual environment

Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

### Step 4: Install dependencies

```bash
python -m pip install -r requirements.txt
```

### Step 5: Initialize the database

```bash
python -m database.connection
```

### Step 6: Start the application

```bash
python app.py
```

Open the local application in your browser:

```text
http://127.0.0.1:5000
```

## 8. Running Automated Tests

DataGuard includes automated tests using Pytest.

Run the complete test suite:

```bash
python -m pytest -v
```

For a concise summary:

```bash
python -m pytest -q
```

### Current Test Coverage

| Test Module | Test Cases |
|---|---:|
| Ingestion | 6 |
| Validation | 12 |
| Replay and Recovery | 6 |
| **Total** | **24** |

The tests cover:
- CSV, JSON, and XLSX parsing.
- Missing-file handling.
- Duplicate file detection.
- Failed ingestion and retry.
- Employee validation rules.
- Record correction and replay.
- Failed replay handling.
- Original payload preservation.
- Duplicate replay prevention.

**Latest test result: 24 tests passed.**

## 9. Performance Benchmark

DataGuard was evaluated using two reproducible synthetic datasets containing 100,000 employee records each.

### Benchmark A — Clean Dataset

| Metric | Result |
|---|---:|
| Input records | 100,000 |
| Published records | 100,000 |
| Quarantined records | 0 |
| Ingestion time | 4.20 seconds |
| Validation time | 13.36 seconds |
| Total processing time | 17.56 seconds |
| Throughput | 5,695 records/second |
| Reconciliation | PASSED |

### Benchmark B — Mixed-Quality Dataset

| Metric | Result |
|---|---:|
| Input records | 100,000 |
| Published records | 90,000 |
| Quarantined records | 10,000 |
| Ingestion time | 4.31 seconds |
| Validation time | 8.91 seconds |
| Total processing time | 13.21 seconds |
| Throughput | 7,567 records/second |
| Reconciliation | PASSED |

### Mixed Dataset Distribution

- 90,000 valid records.
- 5,000 invalid salary records.
- 3,000 invalid department records.
- 1,000 invalid age records.
- 1,000 duplicate employee IDs.

Both benchmarks achieved successful record reconciliation.

*Benchmark results reflect measurements from the development machine and are not universal performance guarantees.*

## 10. Reliability and Data Recovery

DataGuard incorporates several mechanisms to improve pipeline reliability:

- File-hash-based duplicate ingestion detection.
- Deterministic source and target record identifiers.
- Preservation of original source payloads.
- Transaction rollback during failed processing.
- Failed execution history.
- Record-level quarantine and correction.
- Controlled replay of corrected records.
- Replay history and audit logging.
- Source-to-target reconciliation.

## 11. Supported Input Formats and Scope

Currently supported input formats:

- CSV
- JSON
- Excel (.xlsx)

The Excel reader currently processes the first worksheet.

The platform is currently designed around an employee dataset with configurable validation rules for employee IDs, departments, salary, age, and joining dates.

Additional data formats and configurable domain schemas can be considered as future enhancements.

## 12. Future Enhancements

Potential future improvements include:

- PostgreSQL integration for multi-user and larger-scale deployments.
- Configurable validation rules and schema management.
- Advanced schema-drift detection.
- Incremental and scheduled ingestion.
- Concurrent processing and parallel validation.
- Role-based access control.
- Cloud storage integration.
- Pipeline scheduling and orchestration.
- Advanced operational analytics and alerting.
- Additional formats such as Parquet and JSONL.

## 13. Author and Project Information

**Project:** DataGuard — Intelligent Data Quality, Quarantine & Recovery Platform

**Category:** Data Engineering / Data Quality / Pipeline Reliability

**Primary Technologies:** Python, Flask, SQLite, HTML, CSS, JavaScript, Pytest

**Purpose:** To demonstrate an end-to-end data ingestion, validation, quarantine, recovery, and monitoring workflow.

---

**DataGuard — Making Data Pipelines More Reliable, Transparent, and Recoverable.**