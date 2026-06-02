"""Headless daily sync entrypoint, run by the scheduled GitHub Action (and
manually via `python -m scripts.daily_sync`). Pulls recent device data and
rebuilds derived metrics, with no Streamlit involved — config comes from
environment variables via core.config's os.environ fallback.

Exit code is 0 when both the sync and recompute succeed, 1 otherwise, so the
CI run goes red on failure and you get notified."""

from __future__ import annotations

import sys

from core import logger
from services import metrics_service, sync_service

# Default lookback for the routine sync. A week of overlap is cheap and heals
# any days missed while the schedule was down.
DEFAULT_DAYS = 7


def run(days: int = DEFAULT_DAYS) -> dict:
    logger.info("sync", "daily_sync starting", {"days": days})
    sync = sync_service.sync_all_devices(days)
    recompute = metrics_service.recompute_daily_metrics()
    ok = bool(sync.get("ok")) and bool(recompute.get("ok"))
    logger.info(
        "sync",
        "daily_sync complete" if ok else "daily_sync finished with errors",
        {
            "ok": ok,
            "garmin_ok": sync.get("garmin", {}).get("ok"),
            "whoop_ok": sync.get("whoop", {}).get("ok"),
            "recompute_ok": recompute.get("ok"),
        },
    )
    return {"ok": ok, "sync": sync, "recompute": recompute}


def main() -> int:
    days = DEFAULT_DAYS
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except ValueError:
            print(f"Ignoring non-integer days argument: {sys.argv[1]!r}")
    result = run(days)
    if not result["ok"]:
        print("daily_sync failed:", result)
        return 1
    print("daily_sync ok:", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
