"""Daily schedule trigger — determines whether a daily run is due.

The check is intentionally simple: the pipeline fires at most once per
calendar day (UTC).  The caller is responsible for persisting the last-run
date across restarts.
"""

from __future__ import annotations

from datetime import date, datetime


def is_daily_trigger_due(last_run_date: date | None, now: datetime) -> bool:
    """Return True if the daily trigger has not yet fired today.

    "Today" is determined from *now* via :meth:`~datetime.datetime.date`, so
    the caller controls the timezone interpretation by passing an aware or
    naive *now* consistently.

    Args:
        last_run_date: Date of the most recent successful daily run, or
            ``None`` if the pipeline has never run.
        now: Current datetime used to determine today's date.

    Returns:
        ``True`` when *last_run_date* is ``None`` or is strictly earlier than
        ``now.date()``.
    """
    today = now.date()
    return last_run_date is None or last_run_date < today
