from collections import OrderedDict
from datetime import datetime

from discord import TextChannel, Message
from discord.abc import User

from times import TimeRange


# name : (times, selected)
g_available_players: OrderedDict[User, tuple[TimeRange, bool]] = OrderedDict()

g_players_needed: int = 5
g_channel: TextChannel | None = None
g_debug_mode: bool = False
g_confirmed_start_time: datetime | None = None
g_waiting: bool = False


def state() -> str:
    return f"{g_available_players=}\n{g_confirmed_start_time=}"


async def send(message: str) -> Message | None:
    if g_channel is not None:
        return await g_channel.send(message)

