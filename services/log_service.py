"""Read access to the operational log for the UI (Today's error strip and the
Debug tab). Pure Python — no Streamlit."""

from __future__ import annotations

from repositories import debug_log_repo


def recent_logs(
    limit: int = 200,
    severity: str | None = None,
    source: str | None = None,
    since: str | None = None,
) -> dict:
    """Recent debug_log rows, newest first. Never raises into the UI."""
    try:
        rows = debug_log_repo.recent(limit=limit, severity=severity, source=source, since=since)
        return {"ok": True, "rows": rows}
    except Exception as exc:
        # Not logged via core.logger: if the log table is unreachable, logging
        # the failure would fail too.
        return {"ok": False, "error": str(exc), "rows": []}
