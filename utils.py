from datetime import datetime, timedelta, time, date
import zoneinfo
from typing import Any, TypeVar, Callable
from collections.abc import Iterable

TZ = zoneinfo.ZoneInfo(key="America/Toronto")


class TimeSyntaxError(RuntimeError):

    def __init__(self, message: str):
        self.message: str = message
        super().__init__()

    bad_word_seq_err: Callable[[str | None, str], str] = (
        lambda last_word, word: f"can't understand '{last_word}' followed by '{word}'"
    )
    duplicate_info_err: str = f"got two of the same piece of information"


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%m/%d %H:%M")


K = TypeVar("K")
V = TypeVar("V")


def reverse_lookup(value: V, d: dict[K, list[V]] | dict[K, V]) -> None | K:
    for k, v in d.items():
        if v == value or (isinstance(v, Iterable) and value in v):
            return k
    return None


def add_time_and_delta(t: time, td: timedelta) -> time:
    return (datetime.combine(date.today(), t) + td).time()


T = TypeVar("T", datetime, time, timedelta)


def strip_seconds(obj: T) -> T:
    match obj:
        case time():
            return add_time_and_delta(obj, -(timedelta(seconds=obj.second, microseconds=obj.microsecond)))
        case datetime():
            return obj - timedelta(seconds=obj.second) - timedelta(microseconds=obj.microsecond)
        case timedelta():
            return obj - timedelta(seconds=obj.seconds) - timedelta(microseconds=obj.microseconds)
        case _:  # pyright: ignore[reportUnnecessaryComparison]
            raise TypeError(
                f"Can't round time off of variable {obj=} which has type {type(obj)}"
            )  # pyright: ignore[reportUnreachable]


def add_plurals(strs: list[str]) -> list[str]:
    return strs + [s + "s" for s in strs]


def remove_any(string: str, strs: list[str]) -> str:
    for s in strs:
        if s in string:
            string = string.replace(s, "")
    return string


def apply_func_to_timelike_var(arg, f: Callable[..., Any]):
    match arg:
        case None:
            return None
        case datetime() | time():
            return f(arg)
        case list() | tuple() | set():
            return type(arg)(map(lambda e: apply_func_to_timelike_var(e, f), arg))
        case _:
            return arg


def round_time_wrapper(f: Callable[..., Any]):
    def wrapper(*args, **kwargs):
        result = f(*args, **kwargs)
        result = apply_func_to_timelike_var(result, strip_seconds)
        return result

    return wrapper


def set_tz_wrapper(f: Callable[..., Any]):
    def wrapper(*args, **kwargs):
        result = f(*args, **kwargs)
        result = apply_func_to_timelike_var(result, lambda t: t.replace(tzinfo=TZ))
        return result

    return wrapper


def contains_any(first, iterable: Iterable[Any]) -> bool:
    for e in iterable:
        if e in first:
            return True
    else:
        return False


E = TypeVar("E")


def find_first_to_contain(first, iterable: Iterable[E]) -> E | None:
    for e in iterable:
        if e in first:
            return e
    else:
        return None


@set_tz_wrapper
@round_time_wrapper
def time_today(t: time) -> datetime:
    """
    Make a datetime with today's date and the provided time
    :param t: The time of day
    :return: datetime
    """
    return datetime.combine(date.today(), t)


def time_tomorrow(t: time) -> datetime:
    return time_today(t) + timedelta(days=1)


@set_tz_wrapper
@round_time_wrapper
def get_now_rounded() -> datetime:
    return datetime.now()


@set_tz_wrapper
def get_now() -> datetime:
    return datetime.now()
