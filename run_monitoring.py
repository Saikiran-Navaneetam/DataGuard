from application.monitoring.monitor import get_monitoring_report


def main():

    report = get_monitoring_report()

    print("\n========== DATAGUARD MONITORING ==========")

    print("\nPIPELINE OVERVIEW")
    print("-" * 40)

    metrics = [
        ("Total pipeline runs", "total_runs"),
        ("Total source files", "total_files"),
        ("Total input records", "total_records"),
        ("Published source records", "published"),
        ("Target records", "target_count"),
        ("Currently quarantined", "quarantined"),
        ("Open quarantine cases", "open_quarantine"),
        ("Resolved quarantine cases", "resolved_quarantine"),
        ("Not yet processed", "received"),
        ("Other source statuses", "other_status"),
        ("Successful replays", "replay_success"),
        ("Failed replay attempts", "replay_failed")
    ]

    for label, key in metrics:
        print(f"{label:<32}: {report[key]}")

    print("\nRECONCILIATION")
    print("-" * 40)

    gap = report["publication_gap"]

    print(f"Published records : {report['published']}")
    print(f"Target records    : {report['target_count']}")
    print(f"Publication gap   : {gap}")

    if gap == 0:
        print("Result            : RECONCILED")
    else:
        print("Result            : INVESTIGATION REQUIRED")

    print("\nPIPELINE RUN HISTORY")
    print("-" * 40)

    for run in report["runs"]:
        print(f"\nRun ID: {run['run_id']}")
        print(f"Status: {run['status']}")
        print(f"Input count: {run['input_count']}")
        print(f"Published: {run['published_count']}")
        print(f"Currently quarantined: {run['quarantined_count']}")
        print(f"Successful replays: {run['replayed_count']}")

    print("\nRECENT REPLAY HISTORY")
    print("-" * 40)

    for replay in report["replay_history"]:
        print(
            f"Attempt {replay['attempt_number']} | "
            f"{replay['replay_status']} | "
            f"{replay['attempted_at']}"
        )

    print("\n===========================================")


if __name__ == "__main__":
    main()