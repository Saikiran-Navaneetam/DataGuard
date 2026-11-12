from database.connection import get_connection


def get_monitoring_report():
    """Collect live operational metrics from the DataGuard database."""

    connection = get_connection()

    try:
        # Overall pipeline metrics
        total_runs = connection.execute(
            "SELECT COUNT(*) AS total FROM pipeline_runs"
        ).fetchone()["total"]

        total_files = connection.execute(
            "SELECT COUNT(*) AS total FROM source_files"
        ).fetchone()["total"]

        total_records = connection.execute(
            "SELECT COUNT(*) AS total FROM source_records"
        ).fetchone()["total"]

        published = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM source_records
            WHERE status = 'PUBLISHED'
            """
        ).fetchone()["total"]

        quarantined = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM source_records
            WHERE status = 'QUARANTINED'
            """
        ).fetchone()["total"]

        received = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM source_records
            WHERE status = 'RECEIVED'
            """
        ).fetchone()["total"]

        other = total_records - published - quarantined - received

        # Target verification
        target_count = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM target_records
            """
        ).fetchone()["total"]

        publication_gap = published - target_count

        # Quarantine metrics
        open_quarantine = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM quarantine_records
            WHERE status IN ('OPEN', 'CORRECTED', 'REPLAY_PENDING')
            """
        ).fetchone()["total"]

        resolved_quarantine = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM quarantine_records
            WHERE status = 'RESOLVED'
            """
        ).fetchone()["total"]

        # Replay metrics
        replay_success = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM replay_history
            WHERE replay_status = 'SUCCESS'
            """
        ).fetchone()["total"]

        replay_failed = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM replay_history
            WHERE replay_status = 'FAILED'
            """
        ).fetchone()["total"]

        # Pipeline execution details
        runs = connection.execute(
            """
            SELECT
                p.run_id,
                p.status,
                p.started_at,
                p.completed_at,
                p.input_count,

                (
                    SELECT COUNT(*)
                    FROM source_files sf
                    JOIN source_records sr
                        ON sr.source_file_id = sf.source_file_id
                    WHERE sf.run_id = p.run_id
                      AND sr.status = 'PUBLISHED'
                ) AS published_count,

                (
                    SELECT COUNT(*)
                    FROM source_files sf
                    JOIN source_records sr
                        ON sr.source_file_id = sf.source_file_id
                    WHERE sf.run_id = p.run_id
                      AND sr.status = 'QUARANTINED'
                ) AS quarantined_count,

                (
                    SELECT COUNT(*)
                    FROM replay_history rh
                    JOIN source_records sr
                        ON sr.source_record_id = rh.source_record_id
                    JOIN source_files sf
                        ON sf.source_file_id = sr.source_file_id
                    WHERE sf.run_id = p.run_id
                      AND rh.replay_status = 'SUCCESS'
                ) AS replayed_count

            FROM pipeline_runs p
            ORDER BY p.started_at DESC
            """
        ).fetchall()

        # Recent replay attempts
        replay_history = connection.execute(
            """
            SELECT
                replay_id,
                replay_status,
                attempt_number,
                attempted_at,
                error_message
            FROM replay_history
            ORDER BY attempted_at DESC
            LIMIT 10
            """
        ).fetchall()

        return {
            "total_runs": total_runs,
            "total_files": total_files,
            "total_records": total_records,
            "published": published,
            "target_count": target_count,
            "quarantined": quarantined,
            "open_quarantine": open_quarantine,
            "resolved_quarantine": resolved_quarantine,
            "received": received,
            "other_status": other,
            "publication_gap": publication_gap,
            "replay_success": replay_success,
            "replay_failed": replay_failed,
            "runs": [dict(row) for row in runs],
            "replay_history": [
                dict(row) for row in replay_history
            ]
        }

    finally:
        connection.close()