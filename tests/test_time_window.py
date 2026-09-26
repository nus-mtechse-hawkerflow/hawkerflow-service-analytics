from datetime import date, datetime, timedelta, timezone

from analytics.time_window import singapore_day_bounds_utc, singapore_today, to_singapore_hour


def test_day_starts_at_1600_utc_the_previous_day():
    start, end = singapore_day_bounds_utc(date(2026, 9, 26))

    assert start == datetime(2026, 9, 25, 16, 0, 0)
    assert end == datetime(2026, 9, 26, 16, 0, 0)


def test_bounds_are_naive_to_match_the_stored_columns():
    start, end = singapore_day_bounds_utc(date(2026, 9, 26))

    assert start.tzinfo is None
    assert end.tzinfo is None


def test_interval_is_exactly_24_hours():
    start, end = singapore_day_bounds_utc(date(2026, 9, 26))

    assert (end - start).total_seconds() == 24 * 3600


def test_singapore_has_no_daylight_saving_so_every_day_is_the_same_length():
    for day in (date(2026, 1, 1), date(2026, 3, 29), date(2026, 10, 25), date(2026, 12, 31)):
        start, end = singapore_day_bounds_utc(day)
        assert (end - start).total_seconds() == 24 * 3600, day


# Review Focus 3: a late-evening order must not fall into yesterday.
def test_an_order_at_2330_singapore_belongs_to_that_singapore_day():
    # 23:30 SGT on 26 Sep == 15:30 UTC on 26 Sep
    stored = datetime(2026, 9, 26, 15, 30, 0)
    start, end = singapore_day_bounds_utc(date(2026, 9, 26))

    assert start <= stored < end
    assert to_singapore_hour(stored) == 23


def test_an_order_at_0030_singapore_belongs_to_that_singapore_day():
    # 00:30 SGT on 26 Sep == 16:30 UTC on 25 Sep
    stored = datetime(2026, 9, 25, 16, 30, 0)
    start, end = singapore_day_bounds_utc(date(2026, 9, 26))

    assert start <= stored < end
    assert to_singapore_hour(stored) == 0


def test_the_interval_is_half_open_so_midnight_belongs_to_the_next_day():
    start, end = singapore_day_bounds_utc(date(2026, 9, 26))
    next_start, _ = singapore_day_bounds_utc(date(2026, 9, 27))

    # The day's end is exactly the next day's start, and belongs to the next day.
    assert end == next_start
    assert not (start <= end < end)


def test_consecutive_days_neither_overlap_nor_leave_a_gap():
    _, first_end = singapore_day_bounds_utc(date(2026, 9, 26))
    second_start, _ = singapore_day_bounds_utc(date(2026, 9, 27))

    assert first_end == second_start


def test_hour_mapping_covers_the_whole_day():
    # 16:00 UTC is 00:00 SGT; walk 24 hours and expect each hour exactly once.
    midnight_sgt_as_utc = datetime(2026, 9, 25, 16, 0)
    hours = [to_singapore_hour(midnight_sgt_as_utc + timedelta(hours=h)) for h in range(24)]

    assert hours == list(range(24))


def test_an_aware_timestamp_is_respected_rather_than_assumed_utc():
    # 08:00 at UTC+8 is 00:00 UTC, which is 08:00 in Singapore.
    aware = datetime(2026, 9, 26, 8, 0, tzinfo=timezone(timedelta(hours=8)))

    assert to_singapore_hour(aware) == 8


def test_singapore_today_returns_a_date():
    today = singapore_today()

    assert isinstance(today, date)
