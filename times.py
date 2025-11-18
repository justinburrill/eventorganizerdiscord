from functools import cmp_to_key
from typing import override
from enum import IntEnum
from datetime import timedelta, datetime, date, time
from utils import (
    add_plurals,
    TimeSyntaxError,
    set_tz_wrapper,
    round_time_wrapper,
    find_first_to_contain,
    strip_seconds,
    time_today,
    get_now_rounded,
    fmt_dt,
    reverse_lookup,
)

hour_suffixes = list(reversed(sorted(add_plurals(["hr", "h", "hour", "hour"]))))
minute_suffixes = list(reversed(sorted(add_plurals(["min", "minute", "m"]))))
time_suffixes = hour_suffixes + minute_suffixes + ["am", "pm"]


class TimeIndicatorType(IntEnum):
    StartTime, EndTime, Duration, Delay = range(4)


@set_tz_wrapper
@round_time_wrapper
def parse_time_string(string: str) -> tuple[time, bool] | None:
    """
    :returns: (t: `time`, lock: `bool`) lock represents if we are certain about the am/pm
    """
    is_PM: bool | None = None
    if "am" in string and "pm" in string:
        raise TimeSyntaxError("Can't be am and pm, that's dumb")
    elif "am" in string:
        is_PM = False
    elif "pm" in string:
        is_PM = True

    string = string.strip().removesuffix("pm").removesuffix("am").strip()
    if len(string) == 0:
        raise TimeSyntaxError("not enough information")
    parts: list[str] = string.split(":")
    minute: int = 0
    parsed_parts: list[int] = []
    for i in range(len(parts)):
        part = parts[i].strip()
        if not part.isnumeric():
            raise TimeSyntaxError(f"Can't make a number out of {parts[i]}")
        parsed_parts.append(int(parts[i]))
    if len(parts) > 2:
        raise TimeSyntaxError("Don't give me seconds")
    elif len(parts) == 2:
        (hour, minute) = parsed_parts
    elif len(parts) == 1:
        hour = parsed_parts[0]
    else:
        raise TimeSyntaxError("Couldn't figure out a time from {string}")
    if not (0 <= hour <= 23):
        raise TimeSyntaxError(f"Hour {hour} is out of range")
    if not (0 <= minute <= 59):
        raise TimeSyntaxError(f"Minute {minute} is out of range")
    if is_PM is True and hour > 12:
        raise TimeSyntaxError(f"Can't have an hour > 12 (provided {hour}) when PM")
    lock = is_PM is not None
    if is_PM in [None, False]:
        if is_PM is None and hour < 12:
            hour += 12
        return time(hour=hour, minute=minute), lock
    elif is_PM is True:
        if hour == 12:
            hour = 0  # adjust down
        return time(hour=hour + 12, minute=minute), lock


@set_tz_wrapper
@round_time_wrapper
def parse_simple_timedelta_string(string: str) -> timedelta | None:
    """
    Will probably return None

    :param string: the string to parse...
    :returns: `timedelta` if we really think this string is a time delta
    """
    is_hour: bool = False
    string = string.strip()
    if string.isnumeric():
        return timedelta(minutes=int(string))
    if (s := find_first_to_contain(string, hour_suffixes)) is not None:
        is_hour = True
        string = string.removesuffix(s).strip()
    elif (s := find_first_to_contain(string, minute_suffixes)) is not None:
        is_hour = False
        string = string.removesuffix(s).strip()
    if not string.isnumeric():
        return None
    return timedelta(hours=int(string)) if is_hour else timedelta(minutes=int(string))


@set_tz_wrapper
@round_time_wrapper
def parse_time_range_string(string: str, now: datetime | None = None) -> tuple[datetime, timedelta, bool]:
    """
    examples:
    5min (available in 5 min for default duration)
    7-9 (available from 7pm to 9pm)
    for 5hrs (available from now for 5hrs)
    until 10 (available from now until 10pm)
    """
    if now is None:
        now = get_now_rounded()
    indicators: dict[TimeIndicatorType, list[str]] = {
        TimeIndicatorType.StartTime: ["from", "at"],
        TimeIndicatorType.EndTime: ["until", "til", "till", "to"],
        TimeIndicatorType.Duration: ["for"],
        TimeIndicatorType.Delay: ["in"],
    }
    string = string.lower()
    # easy range
    if "-" in string:
        parts = string.split("-")
        if len(parts) != 2:
            raise TimeSyntaxError("why this amount of dashes in your message? do something like 7-10")
        r1: tuple[time, bool] | None = parse_time_string(parts[0])
        r2: tuple[time, bool] | None = parse_time_string(parts[1])
        if r1 is None or r2 is None:
            raise TimeSyntaxError("couldn't parse a time range from this")
        fst_time, lock1 = r1
        snd_time, lock2 = r2
        fst_date: datetime = datetime.combine(date.today(), fst_time)
        snd_date: datetime = datetime.combine(date.today(), snd_time)
        if fst_time < snd_time < time(hour=6):
            fst_date += timedelta(days=1)  # if given a 3am, they probably mean the next day
        if snd_time < time(hour=6):
            snd_date += timedelta(days=1)
        if snd_date < fst_date and snd_time.hour <= 12:
            snd_date += timedelta(hours=12)
        dur = snd_date - fst_date
        return fst_date, dur, False
    # attempt to dissect string
    start_time: time | None = None
    end_time: time | None = None
    duration: timedelta | None = None
    delay: timedelta | None = None
    last_word: str | None = None
    last_time: time | None = None
    last_duration: timedelta | None = None
    last_ind_type: TimeIndicatorType | None = None
    words = [s.strip() for s in string.split(" ") if not s.isspace() and not len(s) == 0]
    skip = False
    lock_end_time_am_pm = False
    for i, word in enumerate(words):
        if skip:
            skip = False
            continue
        if word.isnumeric():
            if i != len(words) - 1 and words[i + 1] in time_suffixes:
                word = word + " " + words[i + 1]
                skip = True
        # is indicator?
        if word in (w for l in indicators.values() for w in l):
            if last_ind_type is not None:  # two indicators in a row
                raise TimeSyntaxError(TimeSyntaxError.bad_word_seq_err(last_word, word))
            ind_type = reverse_lookup(word, indicators)
            # previously the time was given without an indicator, it's probably the start time
            if last_time is not None:
                start_time = last_time
            last_ind_type = ind_type
            last_word = word
            continue  # next word
        # is time?
        try:
            parse_time_result = parse_time_string(word)
            if parse_time_result is None:
                raise TimeSyntaxError("no time")
            t, lock_time = parse_time_result
            match last_ind_type:
                case TimeIndicatorType.StartTime:
                    if start_time is not None:
                        raise TimeSyntaxError(TimeSyntaxError.duplicate_info_err)
                    start_time = t
                case TimeIndicatorType.EndTime:
                    if end_time is not None:
                        raise TimeSyntaxError(TimeSyntaxError.duplicate_info_err)
                    end_time = t
                    lock_end_time_am_pm = lock_time
                case TimeIndicatorType.Delay | TimeIndicatorType.Duration:
                    raise TimeSyntaxError(TimeSyntaxError.bad_word_seq_err(last_word, word))
                case _:
                    last_time = t
            last_word = word
            last_ind_type = None
            continue  # next word!
        except TimeSyntaxError:
            pass  # not a valid time ...
        # is duration?
        try:
            d = parse_simple_timedelta_string(word)
            if d is not None:
                match last_ind_type:
                    case TimeIndicatorType.Duration:
                        if duration is not None:
                            raise TimeSyntaxError(TimeSyntaxError.duplicate_info_err)
                        duration = d
                    case TimeIndicatorType.Delay:
                        if delay is not None:
                            raise TimeSyntaxError(TimeSyntaxError.duplicate_info_err)
                        delay = d
                    case TimeIndicatorType.EndTime | TimeIndicatorType.StartTime:
                        raise TimeSyntaxError(TimeSyntaxError.duplicate_info_err)
                    case _:
                        last_duration = d
                last_word = word
                last_ind_type = None
                continue
        except TimeSyntaxError:
            pass  # not a valid duration
        raise TimeSyntaxError(f"Unrecognized word '{word}'")
    # time to datetime
    [start_datetime, end_datetime] = map(lambda t: time_today(t) if t is not None else None, [start_time, end_time])

    # done figuring out string, get info from results
    return *parse_time_range_results(start_datetime, end_datetime, duration, delay, now=now), lock_end_time_am_pm


def parse_time_range_results(
    start_time: datetime | None,
    end_time: datetime | None,
    duration: timedelta | None,
    delay: timedelta | None,
    now=None,
) -> tuple[datetime, timedelta]:
    if now is None:
        now = get_now_rounded()
    match (start_time, end_time, duration, delay):
        case (None, None, None, None):
            raise TimeSyntaxError("i got literally nothing from that")
        case (s, None, None, None):
            return s, TimeRange.DEFAULT_DURATION
        case (None, e, None, None):
            return now, e - now
        case (None, None, None, w):
            return now + w, TimeRange.DEFAULT_DURATION
        case (None, None, d, None):
            return now, d
        case (s, None, d, None):
            return s, d
        case (s, e, None, None):
            return s, e - s
        case (None, None, d, w):
            return now + w, d
        case (None, e, None, w):
            return (s := (now + w)), e - s
        case _:
            raise TimeSyntaxError("couldn't make sense of this")


class TimeRange:
    DEFAULT_DURATION: timedelta = timedelta(hours=6)

    def __init__(self, string: str, now: datetime | None = None):
        if now is None:
            now = get_now_rounded()
        if len(string.strip()) == 0:
            self.start_time_available = now
            self.duration_available = TimeRange.DEFAULT_DURATION
            return
        result: tuple[datetime, timedelta, bool] = parse_time_range_string(string, now=now)
        dt, td, lock = result
        # if fst_time < snd_time < time(hour=6):
        #     fst_date += timedelta(days=1)  # if given a 3am, they probably mean the next day
        # if snd_time < time(hour=6):
        #     snd_date += timedelta(days=1)
        # if snd_date < fst_date and snd_time.hour <= 12:
        #     snd_date += timedelta(hours=12)
        for i in range(2):
            if (end := dt + td) < dt and end.time().hour < 13:
                td += timedelta(hours=24) if lock else timedelta(hours=12)
        if td.total_seconds() <= 0:
            raise ValueError(f"End time must be after start time:\n{dt=}, {td=}")
        if not isinstance(dt, datetime):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(f"dt wasn't datetime: {type(dt)=} {dt=}")
        if not isinstance(td, timedelta):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(f"td wasn't timedelta: {type(td)=} {td=}")
        self.start_time_available: datetime = dt
        self.duration_available: timedelta = td

    @override
    def __str__(self) -> str:
        return f"available from {fmt_dt(self.start_time_available)} to {fmt_dt(self.get_end_time_available())}"

    @override
    def __repr__(self) -> str:
        return str(self)

    def time_in_range(self, t: datetime):
        return strip_seconds(self.start_time_available) <= t <= self.get_end_time_available()

    def get_end_time_available(self) -> datetime:
        return self.start_time_available + self.duration_available

    @staticmethod
    def cmp_by_start_time(a: "TimeRange", b: "TimeRange") -> int:
        return int((b.start_time_available - a.start_time_available).total_seconds())

    @staticmethod
    @set_tz_wrapper
    @round_time_wrapper
    def get_common_start_time(ranges: list["TimeRange"]) -> datetime | None:
        """
        :param ranges: A list of TimeRanges to compare
        :return: A datetime object representing the start of when everyone is available, or None if there is no total overlap
        """
        if len(ranges) == 0:
            return None
        ranges_by_start_time = list(reversed(sorted(ranges, key=cmp_to_key(TimeRange.cmp_by_start_time))))
        last_start_time = ranges_by_start_time[-1].start_time_available
        for r in ranges_by_start_time:
            if r.get_end_time_available() < last_start_time:
                return None
        else:
            return last_start_time
