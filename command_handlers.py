import time
from collections import OrderedDict

PREFIX = "!"
from times import *

import discord
from discord import Member, Message
from utils import get_now

# name : times
available_players: dict[Member, TimeRange] = {}

PLAYERS_NEEDED = 5

CHANNEL: discord.TextChannel | None = None

DEBUG_MODE = False


def check_player_count() -> bool:
    return len(available_players) >= PLAYERS_NEEDED


def get_current_available() -> list[tuple[Member, TimeRange]]:
    return [(m, tr) for (m, tr) in available_players.items() if tr.time_in_range(get_now())]


def count_current_available() -> int:
    return len(get_current_available())


def get_mention_available_players() -> [str]:
    return [player.mention for player in available_players]


async def inform_available_players_of_start(t: datetime):
    """
    Contact everyone who says they'll play
    """
    if CHANNEL is None: return
    while get_now() < t:
        time.sleep(30)
    await CHANNEL.send(f"{" ".join(get_mention_available_players())} time to play!")
    global available_players
    available_players.clear()


async def inform_available_players_of_agreed_time(t: datetime):
    """
    Contact everyone who says they'll play
    """
    if CHANNEL is None: return
    await CHANNEL.send(f"{" ".join(get_mention_available_players())} start time has been set to {fmt_time(t)}")


async def handle_available(message: Message, args: str):
    if CHANNEL is None:
        await handle_setup(message, "")
    try:
        available_players[message.author] = TimeRange(args)
    except ValueError as e:
        if DEBUG_MODE:
            await message.reply(f"These numbers don't look right: {e}")
        else:
            await message.reply("These numbers don't look right...")
    except TimeSyntaxError as e:
        await message.reply(e.message)
    else:
        await message.add_reaction("👍")
        if check_player_count():
            t = TimeRange.get_common_start_time(available_players.values())
            await inform_available_players_of_agreed_time(t)
            await inform_available_players_of_start(t)


async def handle_unavailable(message: Message, args: str):
    if message.author not in available_players.keys():
        return await message.reply(f"We weren't expecting you!")
    # delete em!
    del available_players[message.author]
    await message.add_reaction("🖕")


async def handle_setup(message: Message, args: str):
    global CHANNEL
    CHANNEL = message.channel
    await CHANNEL.send(f"the channel '{CHANNEL.name}' ({CHANNEL.id}) is now where I will be sending messages")


async def enable_debug(message: Message, args: str):
    global DEBUG_MODE
    DEBUG_MODE = True
    await message.channel.send("debug mode on")


async def disable_debug(message: Message, args: str):
    global DEBUG_MODE
    DEBUG_MODE = False
    await message.channel.send("debug mode off")


async def handle_count(message: Message, args: str):
    global PLAYERS_NEEDED
    if len(args.strip()) == 0:
        return await message.reply(f"We need {PLAYERS_NEEDED} players")
    if not args.isnumeric():
        await message.reply(f"Can't make a number out of '{args}'")
    else:
        PLAYERS_NEEDED = int(args)
        await message.reply(f"Players needed is now '{args}'")


async def handle_status(message: Message, args: str):
    s = f"{count_current_available()} players currently available"
    global available_players
    for m, tr in available_players.items():
        s += f"\n{m.name}: {str(tr)}"
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
