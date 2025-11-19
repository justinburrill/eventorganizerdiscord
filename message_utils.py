from collections import OrderedDict
from datetime import datetime

from discord import TextChannel, Message
from discord.abc import User

from times import TimeRange
import logging

logger = logging.getLogger(__name__)


# name : (times, selected)
g_available_players: OrderedDict[User, tuple[TimeRange, bool]] = OrderedDict()

g_players_needed: int = 5
_g_channel: TextChannel | None = None
g_debug_mode: bool = False
g_confirmed_start_time: datetime | None = None
g_waiting: bool = False


def get_channel() -> TextChannel | None:
    return _g_channel


def set_channel(c: TextChannel) -> None:
    global _g_channel
    _g_channel = c


def state() -> str:
    return f"{g_available_players=}\n{g_confirmed_start_time=}"


async def send(message: str) -> Message | None:
    logging.info(f"sending message: {message}")
    channel = get_channel()
    if channel is not None:
        return await channel.send(message)
    else:
        logging.warning(f"not sending message because {channel=}")
        return None
