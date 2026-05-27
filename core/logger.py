"""Global logger. Every service, client, and repo logs through here. Each call
writes to stdout (so it shows in Streamlit Cloud logs) and inserts a row into
the debug_log table (surfaced in the in-app Debug tab). A failure to write to
the database degrades to stdout only and never raises into the caller."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

_SEVERITIES = {"info", "warning", "error"}
_SOURCES = {"garmin", "whoop", "claude", "db", "calc"}

_stdout = logging.getLogger("health")
if not _stdout.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _stdout.addHandler(_handler)
    _stdout.setLevel(logging.INFO)


def log(
    severity: str,
    source: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    severity = severity if severity in _SEVERITIES else "info"
    source = source if source in _SOURCES else "calc"

    line = f"[{source}] {message}"
    if details:
        try:
            line += f" | {json.dumps(details, default=str)}"
        except Exception:
            line += f" | {details!r}"
    _stdout.log(
        {"info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}[
            severity
        ],
        line,
    )

    try:
        from core.supabase_client import get_client

        get_client().table("debug_log").insert(
            {
                "severity": severity,
                "source": source,
                "message": message,
                "details": details,
            }
        ).execute()
    except Exception as exc:  # never let logging failures break the caller
        _stdout.error(f"[db] failed to write debug_log: {exc}")


def info(source: str, message: str, details: dict[str, Any] | None = None) -> None:
    log("info", source, message, details)


def warning(source: str, message: str, details: dict[str, Any] | None = None) -> None:
    log("warning", source, message, details)


def error(source: str, message: str, details: dict[str, Any] | None = None) -> None:
    log("error", source, message, details)
