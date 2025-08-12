import asyncio
from collections import OrderedDict
from datetime import datetime
from zoneinfo import ZoneInfo

from times import TimeRange, fmt_dt, TimeSyntaxError
import discord
from discord import Member, Message
from utils import get_now_rounded, get_now, remove_any

PREFIX = "!"

# name : times
available_players: dict[Member, TimeRange] = {}

PLAYERS_NEEDED = 5

CHANNEL: discord.TextChannel | None = None

DEBUG_MODE = False

CONFIRMED_START_TIME: datetime | None = None

waiting = False


def state() -> str:
    return f"{available_players=}\n{CONFIRMED_START_TIME=}"


async def prune_available_players() -> None:
    global available_players
    now = get_now_rounded()
    to_delete = []
    for (m, tr) in available_players.items():
        if tr.get_end_time_available() < now:
            if DEBUG_MODE:
                await CHANNEL.send(f"pruning player {m.name} (end time {fmt_dt(tr.get_end_time_available())})")
            to_delete.append(m)
    for m in to_delete:
        del available_players[m]


async def check_player_count():
    """
    Check if we have enough players, and handle it as needed
    :return: None
    """
    await prune_available_players()
    if CHANNEL is None:
        return

    if (count := len(available_players)) >= PLAYERS_NEEDED:
        if DEBUG_MODE:
            await CHANNEL.send("We have enough players, checking for common start time...")
        t = TimeRange.get_common_start_time(list(available_players.values()))
        if t is not None:
            await inform_available_players_of_agreed_time(t)
            await inform_available_players_of_start(t)
        else:
            await CHANNEL.send("Players don't have a common start time...")
    elif DEBUG_MODE:
        await CHANNEL.send(f"Not enough players. (need {PLAYERS_NEEDED}, have {count} total)")


async def get_current_available() -> list[tuple[Member, TimeRange]]:
    global available_players
    await prune_available_players()
    # return [(m, tr) for (m, tr) in available_players.items() if tr.time_in_range(get_now_rounded())]
    out = []
    for (m, tr) in available_players.items():
        if tr.time_in_range((now := get_now_rounded())):
            out.append((m, tr))
            if DEBUG_MODE:
                await CHANNEL.send(
                    f"Member {str(m)} available because {str(tr.start_time_available)} < {str(now)} < {str(tr.get_end_time_available())}")
    return out


async def count_current_available() -> int:
    return len(await get_current_available())


async def get_mention_available_players() -> [str]:
    global available_players
    await prune_available_players()
    return [player.mention for player in available_players]


async def inform_available_players_of_start(t: datetime):
    """
    Contact everyone who says they'll play
    """
    global waiting
    global CONFIRMED_START_TIME
    global available_players
    if CHANNEL is None: return
    if waiting and CONFIRMED_START_TIME == t: return
    CONFIRMED_START_TIME = t
    delay = (t - get_now()).total_seconds()
    if DEBUG_MODE:
        await CHANNEL.send(f"Waiting until {t} ({delay:.2f} seconds, current time is {get_now()})")
    waiting = True
    if delay > 0: await asyncio.sleep(delay)
    if CONFIRMED_START_TIME != t:
        return # someone else took over
    await CHANNEL.send(f"{" ".join(await get_mention_available_players())} time to play!")
    available_players.clear()
    CONFIRMED_START_TIME = None
    waiting = False


async def inform_available_players_of_agreed_time(t: datetime):
    """
    Contact everyone who says they'll play
    """
    if CHANNEL is None: return
    await CHANNEL.send(f"{" ".join(await get_mention_available_players())} start time has been set to {fmt_dt(t)}")


async def handle_available(message: Message, args: str):
    global available_players
    if CHANNEL is None:
        await handle_setup(message, "")
    try:
        now = message.created_at.astimezone()
        args = remove_any(args, ["now"])
        available_players[message.author] = TimeRange(args, now=now)
        if DEBUG_MODE: await message.reply(f"got {available_players[message.author]}\n{state()}")
    except ValueError as e:
        if DEBUG_MODE:
            await message.reply(f"These numbers don't look right: {e}")
        else:
            await message.reply("These numbers don't look right...")
    except TimeSyntaxError as e:
        await message.reply(e.message)
    else:
        await check_player_count()
        await message.add_reaction("👍")


async def handle_unavailable(message: Message, _args: str):
    if CHANNEL is None:
        await handle_setup(message, "")
    global available_players
    await prune_available_players()
    if message.author not in available_players.keys():
        return await message.reply(f"We weren't expecting you!")
    # delete em!
    del available_players[message.author]
    await message.add_reaction("🖕")
    # TODO: cancel confirmed time


async def handle_setup(message: Message, _args: str):
    global CHANNEL
    CHANNEL = message.channel
    await CHANNEL.send(f"the channel \"{CHANNEL.name}\" ({CHANNEL.id}) is now where I will be sending messages")


async def enable_debug(message: Message, _args: str):
    if CHANNEL is None:
        await handle_setup(message, "")
    global DEBUG_MODE
    DEBUG_MODE = True
    await message.channel.send("debug mode on")


async def disable_debug(message: Message, _args: str):
    if CHANNEL is None:
        await handle_setup(message, "")
    global DEBUG_MODE
    DEBUG_MODE = False
    await message.channel.send("debug mode off")


async def handle_count(message: Message, args: str):
    if CHANNEL is None:
        await handle_setup(message, "")
    global PLAYERS_NEEDED
    if len(args.strip()) == 0:
        return await message.reply(f"We need {PLAYERS_NEEDED} players")
    if not args.isnumeric():
        await message.reply(f"Can't make a number out of \"{args}\"")
    else:
        PLAYERS_NEEDED = int(args)
        await message.reply(f"Players needed is now \"{args}\"")
        await check_player_count()


async def handle_status(message: Message, _args: str):
    if CHANNEL is None:
        await handle_setup(message, "")
    await prune_available_players()
    s = f"({await count_current_available()}/{PLAYERS_NEEDED}) players currently available"
    if CONFIRMED_START_TIME is not None: s += f"\nStart time confirmed for: {fmt_dt(CONFIRMED_START_TIME)}"
    if DEBUG_MODE: s += f"\nDEBUG MODE ON\nCURRENT TIME {fmt_dt(get_now_rounded())}\n{state()}"
    global available_players
    available_emoji = "✔️"
    unavailable_emoji = "❌"
    for m, tr in available_players.items():
        emoji = available_emoji if tr.time_in_range(get_now()) else unavailable_emoji
        s += f"\n{emoji} {m.name}: {str(tr)}"
    await message.reply(s)


func_map: OrderedDict = OrderedDict({
    "available": handle_available,
    "unavailable": handle_unavailable,
    "setup": handle_setup,
    "debug": enable_debug,
    "nodebug": disable_debug,
    "count": handle_count,
    "status": handle_status,
})
