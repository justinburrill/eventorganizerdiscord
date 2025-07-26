from functools import cmp_to_key
from enum import Enum
from datetime import timedelta, datetime, date
from utils import *

hour_suffixes = list(reversed(sorted(["hr", "hrs", "h", "hour", "hours"])))
minute_suffixes = list(reversed(sorted(["min", "minute", "minutes", "m"])))
time_suffixes = hour_suffixes + minute_suffixes + ["am", "pm"]


class TimeIndicatorType(Enum):
    StartTime, EndTime, Duration, Delay = range(4)


@set_tz
@round_time
def parse_time_string(string: str) -> time:
    PM: bool | None = None
    if "am" in string and "pm" in string:
        raise TimeSyntaxError("Can't be am and pm, that's dumb")
    elif "am" in string:
        PM = False
    elif "pm" in string:
        PM = True

    string = string.strip().removesuffix("pm").removesuffix("am").strip()
    if len(string) == 0: raise TimeSyntaxError("not enough information")
    parts: list[string] = string.split(":")
    hour: int | None = None
    minute: int = 0
    for i in range(len(parts)):
        parts[i] = parts[i].strip()
        if not (parts[i]).isnumeric(): raise TimeSyntaxError(f"Can't make a number out of {parts[i]}")
        parts[i] = int(parts[i])
    if len(parts) > 2:
        raise TimeSyntaxError("Don't give me seconds")
    elif len(parts) == 2:
        (hour, minute) = parts
    elif len(parts) == 1:
        hour = parts[0]
    if not (0 <= hour <= 23): raise TimeSyntaxError(f"Hour {hour} is out of range")
    if not (0 <= minute <= 59): raise TimeSyntaxError(f"Minute {minute} is out of range")
    if PM is True and hour > 12: raise TimeSyntaxError(f"Can't have an hour > 12 (provided {hour}) when PM")
    if PM in [None, False]:
        if PM is None and hour < 12: hour += 12
        return time(hour=hour, minute=minute)
    elif PM is True:
        if hour == 12: hour = 0  # adjust down
        return time(hour=hour + 12, minute=minute)


@set_tz
@round_time
def parse_simple_timedelta_string(string: str) -> timedelta | None:
    """
    Will probably return None
    :param string: the string to parse...
    :return: timedelta if we really think this string is a time delta
    """
    is_hour: bool = False
    string = string.strip()
    if string.isnumeric():
        return timedelta(minutes=int(string))
    if (s := contains_any(string, hour_suffixes, return_found_item=True)) is not False:
        is_hour = True
        string = string.removesuffix(s).strip()
    elif (s := contains_any(string, minute_suffixes, return_found_item=True)) is not False:
        is_hour = False
        string = string.removesuffix(s).strip()
    if not string.isnumeric():
        return None
    return timedelta(hours=int(string)) if is_hour else timedelta(minutes=int(string))


@set_tz
@round_time
def parse_time_range_string(string: str, now=get_now()) -> (datetime, timedelta):
    """
    examples:
    5min (available in 5 min for default duration)
    7-9 (available from 7pm to 9pm)
    for 5hrs (available from now for 5hrs)
    until 10 (available from now until 10pm)
    """
    indicators: dict[TimeIndicatorType, list[string]] = {
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
        fst_time: time = parse_time_string(parts[0])
        snd_time: time = parse_time_string(parts[1])
        fst_date: datetime = datetime.combine(date.today(), fst_time)
        snd_date: datetime = datetime.combine(date.today(), snd_time)
        if fst_time < snd_time < time(hour=6):
            fst_date += timedelta(days=1)  # if given a 3am, they probably mean the next day
        if snd_time < time(hour=6):
            snd_date += timedelta(days=1)
        dur = snd_date - fst_date
        return fst_date, dur
    # attempt to dissect string
    start_time: time | None = None
    end_time: time | None = None
    duration: timedelta | None = None
    delay: timedelta | None = None
    last_word: str | None = None
    last_time: time | None = None
    last_duration: timedelta | None = None
    last_ind_type: TimeIndicatorType | None | int = None
    words = string.split(" ")
    skip = False
    for (i, word) in enumerate(words):
        if skip:
            skip = False
            continue
        if word.isnumeric():
            if i != len(words) - 1 and words[i + 1] in time_suffixes:
                word = word + " " + words[i + 1]
                skip = True
        bad_word_seq_err = f"can't understand '{last_word}' followed by '{word}'"
        # is indicator?
        if word in (w for l in indicators.values() for w in l):
            if last_ind_type is not None:  # two indicators in a row
                raise TimeSyntaxError(bad_word_seq_err)
            ind_type = reverse_lookup(word, indicators)
            last_ind_type = ind_type
            last_word = word
            continue  # next word
        # is time?
        try:
            t = parse_time_string(word)
            if t is not None:
                match last_ind_type:
                    case TimeIndicatorType.StartTime:
                        start_time = t
                    case TimeIndicatorType.EndTime:
                        end_time = t
                    case TimeIndicatorType.Delay | TimeIndicatorType.Duration:
                        raise TimeSyntaxError(bad_word_seq_err)
                    case None:
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
                        duration = d
                    case TimeIndicatorType.Delay:
                        delay = d
                    case TimeIndicatorType.EndTime | TimeIndicatorType.StartTime:
                        raise TimeSyntaxError(bad_word_seq_err)
                    case None:
                        last_duration = d
                last_word = word
                last_ind_type = None
                continue
        except TimeSyntaxError:
            pass  # not a valid duration
        raise TimeSyntaxError(f"Unrecognized word {word}")
    # time to datetime
    [start_time, end_time] = map(lambda t: time_today(t) if t is not None else None, [start_time, end_time])

    # done figuring out string, get info from results
    return parse_time_range_results(start_time, end_time, duration, delay, now=now)


def parse_time_range_results(start_time: datetime | None, end_time: datetime | None, duration: timedelta | None,
                             delay: timedelta | None, now=get_now()) -> (datetime, timedelta):
    match [start_time, end_time, duration, delay]:
        case [None, None, None, None]:
            raise TimeSyntaxError("i got literally nothing from that")
        case [s, None, None, None]:
            return s, TimeRange.DEFAULT_DURATION
        case [None, e, None, None]:
            return now, e - now
        case [None, None, d, None]:
            return now, d
        case [s, None, d, None]:
            return s, d
        case [s, e, None, None]:
            return s, e - s
        case [None, None, None, w]:
            return now + w, TimeRange.DEFAULT_DURATION
        case [None, None, d, w]:
            return now + w, d
        case _:
            raise TimeSyntaxError("couldn't make sense of this")


# @set_tz
# @round_time
# def parse_time_range_string(string: str) -> (datetime, timedelta):
#     """
#     examples:
#     5min (available in 5 min for default duration)
#     7-9 (available from 7pm to 9pm)
#     for 5hrs (available from now for 5hrs)
#     until 10 (available from now until 10pm)
#     """
#     indicators: dict[TimeIndicatorType, list[string]] = {
#         TimeIndicatorType.StartTime: ["from", "at"],
#         TimeIndicatorType.EndTime: ["until", "til", "till"],
#         TimeIndicatorType.Duration: ["for"],
#         TimeIndicatorType.Delay: ["in"],
#     }
#     string = string.lower()
#     # easy range
#     if "-" in string:
#         parts = string.split("-")
#         if len(parts) != 2:
#             raise TimeSyntaxError("why this amount of dashes in your message? do something like 7-10")
#         fst_time: time = parse_time_string(parts[0])
#         snd_time: time = parse_time_string(parts[1])
#         fst_date = datetime.combine(date.today(), fst_time)
#         snd_date = datetime.combine(date.today(), snd_time)
#         if time(hour=6) > fst_time > snd_time:
#             fst_date += timedelta(days=1)  # if given a 3am, they probably mean the next day
#         if snd_time < time(hour=6):
#             snd_date += timedelta(days=1)
#         dur = snd_date - fst_date
#         return fst_date, dur
#     # attempt to dissect string
#     start_time: datetime | None = None
#     end_time: datetime | None = None
#     duration: timedelta | None = None
#     delay: timedelta | None = None
#     last_word: str | None = None
#     last_time: datetime | None = None
#     last_duration: datetime | None = None
#     last_ind: TimeIndicatorType | None | int = None
#     for word in string.split(" "):
#         word = word.strip()
#         the_time: time = parse_time_string(word)
#         time_dur: timedelta = parse_simple_timedelta_string(word)
#         # if the last word was an indicator then match it to var
#         for tit in TimeIndicatorType:
#             if last_ind == tit:
#                 if the_time is None:
#                     raise TimeSyntaxError(f"expected a time and got {word}")
#                 match tit:  # if we see an indicator, assign the last received number to the proper var
#                     case TimeIndicatorType.StartTime:
#                         start_time = the_time
#                     case TimeIndicatorType.EndTime:
#                         end_time = the_time
#                     case TimeIndicatorType.Duration:
#                         duration = time_dur
#                     case TimeIndicatorType.Delay:
#                         delay = time_dur
#                     case _:
#                         raise TimeSyntaxError("internal: unknown TIT?")
#                 break  # reach here if we have matched the TIT to the last indicator and saved the time
#         else:
#             pass  # reach here if we did not match
#
#         if last_time is not None or last_duration is not None:
#             raise TimeSyntaxError("can't understand two numbers in a row?. try something like 7 - 10")
#         raise NotImplementedError()
#         last_time = the_time
#         last_duration = time_dur
#         last_word = word
#
#         # handle anything that ISN'T a time (IS an indicator)
#         for (ind_type, words) in indicators.values():
#             if word in words:
#                 last_ind = ind_type
#     # done figuring out string, get info from results
#     now = datetime.now()
#     match [start_time, end_time, duration, delay]:
#         case [None, None, None, None]:
#             raise TimeSyntaxError("i got literally nothing from that")
#         case [s, None, None, None]:
#             return s, TimeRange.DEFAULT_DURATION
#         case [None, e, None, None]:
#             return now, e - now
#         case [None, None, d, None]:
#             return now, d
#         case [s, None, d, None]:
#             return s, d
#         case [s, e, None, None]:
#             return s, e - s
#         case [None, None, None, w]:
#             return now + w, TimeRange.DEFAULT_DURATION
#         case [None, None, d, w]:
#             return now + w, d
#         case _:
#             raise TimeSyntaxError("couldn't make sense of this")
#

class TimeRange:
    DEFAULT_DURATION = timedelta(hours=3)

    def __init__(self, string: str, now=get_now()):
        if len(string.strip()) == 0:
            self.start_time_available = now
            self.duration_available = TimeRange.DEFAULT_DURATION
            return
        result: tuple[datetime, timedelta] = parse_time_range_string(string, now=now)
        dt, td = result
        if td.total_seconds() <= 0:
            raise ValueError(f"End time must be after start time:\n{dt=}, {td=}")
        if not isinstance(dt, datetime): raise TypeError(f"dt wasn't datetime: {type(dt)=} {dt=}")
        if not isinstance(td, timedelta): raise TypeError(f"td wasn't timedelta: {type(td)=} {td=}")
        self.start_time_available: datetime = dt
        self.duration_available: timedelta = td

    def __str__(self) -> str:
        fmt = lambda t: t.strftime("%m/%d %H:%M")
        return f"available from {fmt(self.start_time_available)} to {fmt(self.get_end_time_available())}"

    def time_in_range(self, t: datetime):
        return self.start_time_available <= t <= self.get_end_time_available()

    def get_end_time_available(self) -> datetime:
        return self.start_time_available + self.duration_available

    @staticmethod
    def cmp_by_start_time(a: "TimeRange", b: "TimeRange") -> int:
        return int((b.start_time_available - a.start_time_available).total_seconds())

    @staticmethod
    @set_tz
    @round_time
    def get_common_start_time(ranges: ["TimeRange"]) -> datetime | None:
        """
        :param ranges: A list of TimeRanges to compare
        :return: A datetime object representing the start of when everyone is available, or None if there is no total overlap
        """
        if len(ranges) == 0:
            return None
        ranges_by_start_time = sorted(ranges, key=cmp_to_key(TimeRange.cmp_by_start_time))
        last_start_time = ranges_by_start_time[-1].start_time_available
        for r in ranges_by_start_time:
            if r.get_end_time_available() < last_start_time:
                return None
        else:
            return last_start_time
