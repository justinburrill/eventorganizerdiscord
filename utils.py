from datetime import datetime, timedelta, time, date
from zoneinfo import ZoneInfo
from typing import Any
from collections.abc import Collection, Iterable


class TimeSyntaxError(RuntimeError):
    def __init__(self, message):
        self.message = message
        super().__init__()


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%m/%d %H:%M")


def reverse_lookup(value, d: dict):
    for k, v in d.items():
        if v == value or (isinstance(v, list) and value in v):
            return k
    return None


def add_time_and_delta(t: time, td: timedelta) -> time:
    return (datetime.combine(date.today(), t) + td).time()


def strip_seconds(obj: datetime | time | timedelta) -> datetime | time | timedelta:
    match obj:
        case time():
            return add_time_and_delta(obj, -(timedelta(seconds=obj.second, microseconds=obj.microsecond)))
        case datetime():
            return obj - timedelta(seconds=obj.second) - timedelta(microseconds=obj.microsecond)
        case timedelta():
            return obj - timedelta(seconds=obj.seconds) - timedelta(microseconds=obj.microseconds)
        case _:
            raise TypeError(f"Can't round time off of variable {obj=} which has type {type(obj)}")


def apply_func_to_timelike_var(arg, f: callable):
    match arg:
        case None:
            return None
        case datetime() | time():
            return f(arg)
        case list() | tuple() | set():
            return type(arg)(map(lambda e: apply_func_to_timelike_var(e, f), arg))
        case _:
            return arg
        # case _:
        #     raise TypeError(f"Can't of apply function to variable {arg=} which has type {type(arg)}")


def round_time(f):
    def wrapper(*args, **kwargs):
        result = f(*args, **kwargs)
        result = apply_func_to_timelike_var(result, strip_seconds)
        return result

    return wrapper


def set_tz(f):
    def wrapper(*args, **kwargs):
        result = f(*args, **kwargs)
        result = apply_func_to_timelike_var(result, lambda t: t.replace(tzinfo=ZoneInfo("America/Toronto")))
        return result

    return wrapper


def contains_any(first, iterable: Iterable, return_found_item=False) -> bool | Any:
    for e in iterable:
        if e in first:
            if return_found_item:
                return e
            else:
                return True
    else:
        return False


@set_tz
@round_time
def time_today(t: time) -> datetime:
    """
    Make a datetime with today's date and the provided time
    :param t: The time of day
    :return: datetime
    """
    return datetime.combine(date.today(), t)


def time_tomorrow(t: time) -> datetime:
    return time_today(t) + timedelta(days=1)


@set_tz
@round_time
def get_now_rounded() -> datetime:
    return datetime.now()

@set_tz
def get_now() -> datetime:
    return datetime.now()
