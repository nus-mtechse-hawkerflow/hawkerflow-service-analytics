"""Singapore calendar-day boundaries expressed as naive UTC.

Pure module: no framework and no database imports, so a future Lambda
adapter can call these functions unchanged.

Why naive UTC: orders.f_created_at is `timestamp without time zone`
(verified against the live database), and the order service writes it from
datetime.now(timezone.utc), so stored values are UTC wall-clock with the
offset dropped. Comparisons must therefore be made against naive UTC
datetimes, not aware ones.

Singapore is UTC+8 year-round with no daylight saving, so a Singapore day
always begins at 16:00 UTC on the previous calendar day.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

SINGAPORE = ZoneInfo("Asia/Singapore")
UTC = ZoneInfo("UTC")


def singapore_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """Return the half-open interval [start, end) covering `day` in Singapore.

    Both values are naive UTC so they can be compared directly against the
    stored timestamp column. The interval is half-open: midnight belongs to
    the following day, so consecutive days neither overlap nor leave a gap.

    :param day: the Singapore calendar date
    :return: (start, end) as naive UTC datetimes
    """
    start_local = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end_local = start_local + timedelta(days=1)

    return (
        start_local.astimezone(UTC).replace(tzinfo=None),
        end_local.astimezone(UTC).replace(tzinfo=None),
    )


def singapore_today() -> date:
    """Today's date on the Singapore calendar, whatever the server's timezone."""
    return datetime.now(UTC).date()


def to_singapore_hour(stored_utc: datetime) -> int:
    """Map a stored timestamp to its hour (0-23) in Singapore.

    A naive value is interpreted as UTC, matching how the order service
    writes it. An aware value keeps its own offset rather than being
    reinterpreted.
    """
    if stored_utc.tzinfo is None:
        stored_utc = stored_utc.replace(tzinfo=UTC)

    return stored_utc.astimezone(UTC).hour
