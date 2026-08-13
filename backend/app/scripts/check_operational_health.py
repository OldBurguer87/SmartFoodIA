from app.database.session import SessionLocal
from app.services.operational_monitor import OperationalMonitorService


def main() -> None:
    with SessionLocal() as db:
        result = OperationalMonitorService().run(db)
    print(
        "MONITOR_OK "
        f"stores={result['stores_checked']} "
        f"opened={result['tickets_opened']} "
        f"resolved={result['tickets_resolved']}"
    )


if __name__ == "__main__":
    main()
