from unittest import TestCase
from times import TimeRange, parse_time_string, parse_simple_timedelta_string
from datetime import timedelta, datetime, time
from utils import get_now_rounded, time_tomorrow, time_today, add_time_and_delta, strip_seconds, TimeSyntaxError, TZ


class CommonTimeTests(TestCase):
    def test_common_start_time(self):
        now = get_now_rounded()
        trange1 = TimeRange("in 10 minutes for 10 minutes", now=now)
        trange2 = TimeRange("for 1 hour", now=now)
        self.assertEqual(now + timedelta(minutes=10), TimeRange.get_common_start_time([trange1, trange2]))
        self.assertEqual(now, TimeRange.get_common_start_time([trange2]))
        trange3 = TimeRange("in 1 hour for 5 minutes", now=now)
        self.assertEqual(None, TimeRange.get_common_start_time([trange1, trange2, trange3]))

    def test_common_start_time2(self):
        now = get_now_rounded()
        trange1 = TimeRange("5-10", now=now)
        trange2 = TimeRange("4-11", now=now)
        trange3 = TimeRange("3-12", now=now)
        trange4 = TimeRange("1-12", now=now)
        trange5 = TimeRange("2-10", now=now)
        common = TimeRange.get_common_start_time([trange1, trange2, trange3, trange4, trange5])
        self.assertEqual(time_today(time(hour=17)), common)


class TimeParsingTests(TestCase):
    def test_add_time_and_delta(self):
        self.assertEqual(time(hour=12, minute=30), add_time_and_delta(time(hour=12), timedelta(minutes=30)))
        self.assertEqual(time(hour=20, minute=45), add_time_and_delta(time(hour=18), timedelta(hours=2, minutes=45)))

    def test_today(self):
        self.assertEqual(strip_seconds(datetime
                                       .today()
                                       .replace(tzinfo=TZ, hour=10, minute=0)),
                         time_today(time(hour=10)))
        self.assertEqual(strip_seconds(datetime
                                       .today()
                                       .replace(tzinfo=TZ, hour=23, minute=0)),
                         time_today(time(hour=23)))

    def test_time(self):
        self.assertEqual((time(hour=10), True), parse_time_string("10am"))
        self.assertEqual((time(hour=22), True), parse_time_string("10pm"))
        self.assertEqual((time(hour=22), False), parse_time_string("10"))
        self.assertEqual((time(hour=18), False), parse_time_string("6"))
        self.assertEqual((time(hour=18), True), parse_time_string("6pm"))
        self.assertEqual((time(hour=6), True), parse_time_string("6am"))
        self.assertEqual((time(hour=6), True), parse_time_string("6    am"))

    def test_timedelta(self):
        for s in ["5", "5min", "5 minutes", "5m", "5minutes"]:
            self.assertEqual(timedelta(minutes=5), (td := parse_simple_timedelta_string(s)), msg=f"{s=}, {td=}")
        for s in ["5 hours", "5hr", "5hrs", "5 hour", "5h", "5 h"]:
            self.assertEqual(timedelta(hours=5), (td := parse_simple_timedelta_string(s)), msg=f"{s=}, {td=}")


class TimeRangeParsingTests(TestCase):
    def test_easy_range(self):
        trange = TimeRange("5-9")
        self.assertEqual(time_today(time(hour=17)), trange.start_time_available)
        self.assertEqual(time_today(time(hour=21)), trange.get_end_time_available())
        trange = TimeRange("6 - 10")
        self.assertEqual(time_today(time(hour=18)), trange.start_time_available)
        self.assertEqual(time_today(time(hour=22)), trange.get_end_time_available())
        trange = TimeRange("6-12")
        self.assertEqual(time_today(time(hour=18)), trange.start_time_available)
        self.assertEqual(time_tomorrow(time(hour=0)), trange.get_end_time_available())
        trange = TimeRange("9pm - 10 pm")
        self.assertEqual(time_today(time(hour=21)), trange.start_time_available)
        self.assertEqual(time_today(time(hour=22)), trange.get_end_time_available())
        trange = TimeRange("5am - 12pm")
        self.assertEqual(time_today(time(hour=5)), trange.start_time_available)
        self.assertEqual(time_today(time(hour=12)), trange.get_end_time_available())
        trange = TimeRange("12pm - 5am")
        self.assertEqual(time_today(time(hour=12)), trange.start_time_available)
        self.assertEqual(time_tomorrow(time(hour=5)), trange.get_end_time_available())
        trange = TimeRange("8 - 1:30am")
        self.assertEqual(time_today(time(hour=20)), trange.start_time_available)
        self.assertEqual(time_tomorrow(time(hour=1,minute=30)), trange.get_end_time_available())


    def test_fail_easy_range(self):
        now = time_today(time(hour=12))
        self.assertRaises(ValueError, TimeRange, "9-6", now=now)  # backwards time range

    def test_start_time(self):
        now: datetime = time_today(time(hour=12))
        trange = TimeRange("", now=now)
        self.assertEqual(now, trange.start_time_available)
        self.assertEqual(TimeRange.DEFAULT_DURATION, trange.duration_available)
        trange = TimeRange("in 5 minutes", now=now)
        self.assertEqual(now + timedelta(minutes=5), trange.start_time_available)
        trange = TimeRange("in 2 hours", now=now)
        self.assertEqual(now + timedelta(hours=2), trange.start_time_available)
        trange = TimeRange("in 20m", now=now)
        self.assertEqual(now + timedelta(minutes=20), trange.start_time_available)
        trange = TimeRange("at 2pm", now=now)
        self.assertEqual(time_today(time(hour=14)), trange.start_time_available)
        trange = TimeRange("in 5", now=now)
        self.assertEqual(now + timedelta(minutes=5), trange.start_time_available)

    def test_end_time(self):
        now = time_today(time(hour=12, minute=30))
        trange = TimeRange("until 10", now=now)
        self.assertEqual(now, trange.start_time_available)
        self.assertEqual(time_today(time(hour=22)), trange.get_end_time_available())
        self.assertTrue(trange.time_in_range(time_today(time(hour=14))))
        trange = TimeRange("until 7pm", now=now)
        self.assertEqual(now, trange.start_time_available)
        self.assertEqual(time_today(time(hour=19)), trange.get_end_time_available())
        trange = TimeRange("until 1pm", now=now)
        self.assertEqual(now, trange.start_time_available)
        self.assertEqual(time_today(time(hour=13)), trange.get_end_time_available())
        trange = TimeRange("until 1am", now=now)
        self.assertEqual(now, trange.start_time_available)
        self.assertEqual(time_tomorrow(time(hour=1)), trange.get_end_time_available())
        trange = TimeRange("until 12", now=now)
        self.assertEqual(now, trange.start_time_available)
        self.assertEqual(time_tomorrow(time(hour=0)), trange.get_end_time_available())

    def test_duration(self):
        now = get_now_rounded()
        trange = TimeRange("for 30 min", now=now)
        self.assertEqual(now, trange.start_time_available)
        self.assertEqual(now + timedelta(minutes=30), trange.get_end_time_available())
        trange = TimeRange("for 45min", now=now)
        self.assertEqual(now, trange.start_time_available)
        self.assertEqual(now + timedelta(minutes=45), trange.get_end_time_available())
        trange = TimeRange("for 5 hours", now=now)
        self.assertEqual(now, trange.start_time_available)
        self.assertEqual(now + timedelta(hours=5), trange.get_end_time_available())
        trange = TimeRange("for 2hrs", now=now)
        self.assertEqual(now, trange.start_time_available)
        self.assertEqual(now + timedelta(hours=2), trange.get_end_time_available())
        trange = TimeRange("for 5min", now=now)
        self.assertEqual(now, trange.start_time_available)
        self.assertEqual(now + timedelta(minutes=5), trange.get_end_time_available())
        trange = TimeRange("for 100 hours", now=now)
        self.assertEqual(now, trange.start_time_available)
        self.assertEqual(now + timedelta(hours=100), trange.get_end_time_available())

    def test_compound(self):
        now = time_today(time(hour=12))
        trange = TimeRange("in 5 minutes for 1 hour", now=now)
        self.assertEqual(now + timedelta(minutes=5), trange.start_time_available)
        self.assertEqual(timedelta(hours=1), trange.duration_available)
        trange = TimeRange("for 2hr in 1 hour", now=now)
        self.assertEqual(now + timedelta(hours=1), trange.start_time_available)
        self.assertEqual(timedelta(hours=2), trange.duration_available)
        trange = TimeRange("for 5 hours at 3 pm", now=now)
        self.assertEqual(time_today(time(hour=15)), trange.start_time_available)
        self.assertEqual(timedelta(hours=5), trange.duration_available)
        trange = TimeRange("in 1 hr until 11:30", now=now)
        self.assertEqual(now + timedelta(hours=1), trange.start_time_available)
        self.assertEqual(time_today(time(hour=23, minute=30)), trange.get_end_time_available())
        trange = TimeRange("from 7 pm to 9 pm", now=now)
        self.assertEqual(time_today(time(hour=19)), trange.start_time_available)
        self.assertEqual(time_today(time(hour=21)), trange.get_end_time_available())
        trange = TimeRange("7 pm to 9 pm", now=now)
        self.assertEqual(time_today(time(hour=19)), trange.start_time_available)
        self.assertEqual(time_today(time(hour=21)), trange.get_end_time_available())
        trange = TimeRange("from 7:30 to 9:30", now=now)
        self.assertEqual(time_today(time(hour=19, minute=30)), trange.start_time_available)
        self.assertEqual(time_today(time(hour=21, minute=30)), trange.get_end_time_available())

    def test_fail_compound(self):
        now = time_today(time(hour=12))
        self.assertRaises(TimeSyntaxError, TimeRange, "at 5 at 6", now=now)
        self.assertRaises(TimeSyntaxError, TimeRange, "at 7:30:30", now=now)
        self.assertRaises(TimeSyntaxError, TimeRange, "12 to at 12", now=now)
        self.assertRaises(TimeSyntaxError, TimeRange, "from until 7pm", now=now)
        self.assertRaises(TimeSyntaxError, TimeRange, "in 5 minutes in 5 minutes", now=now)
        self.assertRaises(TimeSyntaxError, TimeRange, "hello", now=now)
        self.assertRaises(TimeSyntaxError, TimeRange, "for 5 minutes hello", now=now)
        self.assertRaises(TimeSyntaxError, TimeRange, "for 5pm minutes", now=now)
