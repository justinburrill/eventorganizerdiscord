import pytest
import logging
from times import TimeRange, parse_time_string, parse_simple_timedelta_string
from datetime import timedelta, datetime, time
from utils import get_now_rounded, time_tomorrow, time_today, add_time_and_delta, strip_seconds, TimeSyntaxError, TZ


logger = logging.getLogger(__name__)


class TestCommonTime:
    def test_common_start_time(self):
        now = get_now_rounded()
        trange1 = TimeRange("in 10 minutes for 10 minutes", now=now)
        trange2 = TimeRange("for 1 hour", now=now)
        assert now + timedelta(minutes=10) == TimeRange.get_common_start_time([trange1, trange2])
        assert now == TimeRange.get_common_start_time([trange2])
        trange3 = TimeRange("in 1 hour for 5 minutes", now=now)
        assert None == TimeRange.get_common_start_time([trange1, trange2, trange3])

    def test_common_start_time2(self):
        now = get_now_rounded()
        trange1 = TimeRange("5-10", now=now)
        trange2 = TimeRange("4-11", now=now)
        trange3 = TimeRange("3-12", now=now)
        trange4 = TimeRange("1-12", now=now)
        trange5 = TimeRange("2-10", now=now)
        common = TimeRange.get_common_start_time([trange1, trange2, trange3, trange4, trange5])
        assert time_today(time(hour=17)) == common


class TestTimeParsing:
    def test_add_time_and_delta(self):
        assert time(hour=12, minute=30) == add_time_and_delta(time(hour=12), timedelta(minutes=30))
        assert time(hour=20, minute=45) == add_time_and_delta(time(hour=18), timedelta(hours=2, minutes=45))

    def test_today(self):
        assert strip_seconds(datetime.today().replace(tzinfo=TZ, hour=10, minute=0)) == time_today(time(hour=10))
        assert strip_seconds(datetime.today().replace(tzinfo=TZ, hour=23, minute=0)) == time_today(time(hour=23))

    def test_time(self):
        assert (time(hour=10), True) == parse_time_string("10am")
        assert (time(hour=22), True) == parse_time_string("10pm")
        assert (time(hour=22), False) == parse_time_string("10")
        assert (time(hour=18), False) == parse_time_string("6")
        assert (time(hour=18), True) == parse_time_string("6pm")
        assert (time(hour=6), True) == parse_time_string("6am")
        assert (time(hour=6), True) == parse_time_string("6    am")

    def test_timedelta(self):
        for s in ["5", "5min", "5 minutes", "5m", "5minutes"]:
            assert timedelta(minutes=5) == (td := parse_simple_timedelta_string(s)), f"{s=}, {td=}"
        for s in ["5 hours", "5hr", "5hrs", "5 hour", "5h", "5 h"]:
            assert timedelta(hours=5) == (td := parse_simple_timedelta_string(s)), f"{s=}, {td=}"


class TestTimeRangeParsing:
    def test_easy_range(self):
        trange = TimeRange("5-9")
        assert time_today(time(hour=17)) == trange.start_time_available
        assert time_today(time(hour=21)) == trange.get_end_time_available()
        trange = TimeRange("6 - 10")
        assert time_today(time(hour=18)) == trange.start_time_available
        assert time_today(time(hour=22)) == trange.get_end_time_available()
        trange = TimeRange("6-12")
        assert time_today(time(hour=18)) == trange.start_time_available
        assert time_tomorrow(time(hour=0)) == trange.get_end_time_available()
        trange = TimeRange("9pm - 10 pm")
        assert time_today(time(hour=21)) == trange.start_time_available
        assert time_today(time(hour=22)) == trange.get_end_time_available()
        trange = TimeRange("5am - 12pm")
        assert time_today(time(hour=5)) == trange.start_time_available
        assert time_today(time(hour=12)) == trange.get_end_time_available()
        trange = TimeRange("12pm - 5am")
        assert time_today(time(hour=12)) == trange.start_time_available
        assert time_tomorrow(time(hour=5)) == trange.get_end_time_available()
        trange = TimeRange("8 - 1:30am")
        assert time_today(time(hour=20)) == trange.start_time_available
        assert time_tomorrow(time(hour=1, minute=30)) == trange.get_end_time_available()

    def test_fail_easy_range(self):
        now = time_today(time(hour=12))
        with pytest.raises(ValueError):
            TimeRange("9-6", now=now)  # backwards time range

    def test_start_time(self):
        now: datetime = time_today(time(hour=12))
        trange = TimeRange("", now=now)
        assert now == trange.start_time_available
        assert TimeRange.DEFAULT_DURATION == trange.duration_available
        trange = TimeRange("in 5 minutes", now=now)
        assert now + timedelta(minutes=5) == trange.start_time_available
        trange = TimeRange("in 2 hours", now=now)
        assert now + timedelta(hours=2) == trange.start_time_available

        trange = TimeRange("in 20m", now=now)
        assert now + timedelta(minutes=20) == trange.start_time_available
        trange = TimeRange("at 2pm", now=now)
        assert time_today(time(hour=14)) == trange.start_time_available
        trange = TimeRange("in 5", now=now)
        assert now + timedelta(minutes=5) == trange.start_time_available


    def test_end_time(self):
        now = time_today(time(hour=12, minute=30))
        trange = TimeRange("until 10", now=now)
        assert now == trange.start_time_available
        assert time_today(time(hour=22)) == trange.get_end_time_available()
        assert trange.time_in_range(time_today(time(hour=14)))
        trange = TimeRange("until 7pm", now=now)
        assert now == trange.start_time_available
        assert time_today(time(hour=19)) == trange.get_end_time_available()
        trange = TimeRange("until 1pm", now=now)
        assert now == trange.start_time_available
        assert time_today(time(hour=13)) == trange.get_end_time_available()
        trange = TimeRange("until 1am", now=now)
        assert now == trange.start_time_available
        assert time_tomorrow(time(hour=1)) == trange.get_end_time_available()
        trange = TimeRange("until 12", now=now)
        assert now == trange.start_time_available
        assert time_tomorrow(time(hour=0)) == trange.get_end_time_available()

    def test_duration(self):
        now = get_now_rounded()
        trange = TimeRange("for 30 min", now=now)
        assert now == trange.start_time_available
        assert now + timedelta(minutes=30) == trange.get_end_time_available()
        trange = TimeRange("for 45min", now=now)
        assert now == trange.start_time_available
        assert now + timedelta(minutes=45) == trange.get_end_time_available()
        trange = TimeRange("for 5 hours", now=now)
        assert now == trange.start_time_available
        assert now + timedelta(hours=5) == trange.get_end_time_available()
        trange = TimeRange("for 2hrs", now=now)
        assert now == trange.start_time_available
        assert now + timedelta(hours=2) == trange.get_end_time_available()
        trange = TimeRange("for 5min", now=now)
        assert now == trange.start_time_available
        assert now + timedelta(minutes=5) == trange.get_end_time_available()
        trange = TimeRange("for 100 hours", now=now)
        assert now == trange.start_time_available
        assert now + timedelta(hours=100) == trange.get_end_time_available()

    def test_extra_words(self):
        try:
            now = get_now_rounded()
            trange = TimeRange("in an hour", now=now)
            assert now + timedelta(hours=1) == trange.start_time_available
            trange = TimeRange("for an hour", now=now)
            assert now == trange.start_time_available
            assert timedelta(hours=1) == trange.duration_available
            trange = TimeRange("in a minute", now=now)
            assert now + timedelta(minutes=1) == trange.start_time_available
            trange = TimeRange("now", now=now)
            assert now == trange.start_time_available
            assert TimeRange.DEFAULT_DURATION == trange.duration_available
        except BaseException as e:
            logger.error(e)
            raise e


    def test_compound(self):
        now = time_today(time(hour=12))
        trange = TimeRange("in 5 minutes for 1 hour", now=now)
        assert now + timedelta(minutes=5) == trange.start_time_available
        assert timedelta(hours=1) == trange.duration_available
        trange = TimeRange("for 2hr in 1 hour", now=now)
        assert now + timedelta(hours=1) == trange.start_time_available
        assert timedelta(hours=2) == trange.duration_available
        trange = TimeRange("for 5 hours at 3 pm", now=now)
        assert time_today(time(hour=15)) == trange.start_time_available
        assert timedelta(hours=5) == trange.duration_available
        trange = TimeRange("in 1 hr until 11:30", now=now)
        assert now + timedelta(hours=1) == trange.start_time_available
        assert time_today(time(hour=23, minute=30)) == trange.get_end_time_available()
        trange = TimeRange("from 7 pm to 9 pm", now=now)
        assert time_today(time(hour=19)) == trange.start_time_available
        assert time_today(time(hour=21)) == trange.get_end_time_available()
        trange = TimeRange("7 pm to 9 pm", now=now)
        assert time_today(time(hour=19)) == trange.start_time_available
        assert time_today(time(hour=21)) == trange.get_end_time_available()
        trange = TimeRange("from 7:30 to 9:30", now=now)
        assert time_today(time(hour=19, minute=30)) == trange.start_time_available
        assert time_today(time(hour=21, minute=30)) == trange.get_end_time_available()

    def test_fail_compound(self):
        now = time_today(time(hour=12))
        with pytest.raises(TimeSyntaxError):
            TimeRange("at 5 at 6", now=now)
        with pytest.raises(TimeSyntaxError):
            TimeRange("at 7:30:30", now=now)
        with pytest.raises(TimeSyntaxError):
            TimeRange("12 to at 12", now=now)
        with pytest.raises(TimeSyntaxError):
            TimeRange("from until 7pm", now=now)
        with pytest.raises(TimeSyntaxError):
            TimeRange("in 5 minutes in 5 minutes", now=now)
        with pytest.raises(TimeSyntaxError):
            TimeRange("hello", now=now)
        with pytest.raises(TimeSyntaxError):
            TimeRange("for 5 minutes hello", now=now)
        with pytest.raises(TimeSyntaxError):
            TimeRange("for 5pm minutes", now=now)

    def test_smushed_time(self):
        try:
            now: datetime = time_today(time(hour=12))
            trange = TimeRange("at 830", now=now)
            assert trange.start_time_available == time_today(time(hour=20, minute=30))
            trange = TimeRange("at 745", now=now)
            assert trange.start_time_available == time_today(time(hour=19, minute=45))
        except TimeSyntaxError as e:
            logger.error(e)
            raise e

