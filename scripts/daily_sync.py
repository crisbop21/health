"""Headless daily sync entrypoint, run by the scheduled GitHub Action (and
manually via `python -m scripts.daily_sync`). Pulls recent device data and
rebuilds derived metrics, with no Streamlit involved — config comes from
environment variables via core.config's os.environ fallback.

A device that is simply not set up yet (Whoop not connected, Garmin creds
missing) is treated as skipped, not failed, so the job doesn't alert every day
before you've finished connecting things. Real failures trigger a webhook alert
(if ALERT_WEBHOOK_URL is set) and a non-zero exit so the CI run goes red."""

from __future__ import annotations

import sys

from clients import notify_client
from core import logger
from services import metrics_service, sync_service

# Default lookback for the routine sync. A week of overlap is cheap and heals
# any days missed while the schedule was down.
DEFAULT_DAYS = 7


def _is_skip(error: str | None) -> bool:
    """A device that isn't set up yet is skipped, not a failure."""
    e = (error or "").lower()
    return "not connected" in e or "not configured" in e


def run(days: int = DEFAULT_DAYS) -> dict:
    logger.info("sync", "daily_sync starting", {"days": days})
    sync = sync_service.sync_all_devices(days)
    recompute = metrics_service.recompute_daily_metrics()

    problems: list[str] = []
    for name in ("garmin", "whoop"):
        d = sync.get(name, {})
        if not d.get("ok") and not _is_skip(d.get("error")):
            problems.append(f"{name}: {d.get('error')}")
    if not recompute.get("ok"):
        problems.append(f"recompute: {recompute.get('error')}")

    ok = not problems
    logger.info(
        "sync",
        "daily_sync complete" if ok else "daily_sync finished with problems",
        {
            "ok": ok,
            "garmin_ok": sync.get("garmin", {}).get("ok"),
            "whoop_ok": sync.get("whoop", {}).get("ok"),
            "recompute_ok": recompute.get("ok"),
            "problems": problems,
        },
    )

    if problems:
        notify_client.send("⚠️ Daily health sync had problems:\n- " + "\n- ".join(problems))

    return {"ok": ok, "problems": problems, "sync": sync, "recompute": recompute}


def main() -> int:
    days = DEFAULT_DAYS
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except ValueError:
            print(f"Ignoring non-integer days argument: {sys.argv[1]!r}")
    result = run(days)
    if not result["ok"]:
        print("daily_sync failed:", result["problems"])
        return 1
    print("daily_sync ok:", {"sync": result["sync"], "recompute": result["recompute"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
