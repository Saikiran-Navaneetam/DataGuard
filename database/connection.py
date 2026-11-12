
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = BASE_DIR / "database" / "dataguard.db"
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"


def get_connection():
    """Create a SQLite database connection."""

    connection = sqlite3.connect(DB_PATH, timeout=30)

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")

    return connection


def init_db():
    """Initialize the DataGuard database."""

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = get_connection()

    try:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        connection.executescript(schema)

        print("DataGuard database initialized successfully!")

    except Exception:
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    init_db()
