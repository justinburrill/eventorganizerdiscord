import asyncio
import math
import logging

from collections import OrderedDict
from datetime import datetime
from types import CoroutineType
from discord_globals import client

from times import TimeRange
import discord
from discord import Member, Message
from discord.abc import User
from utils import get_now_rounded, get_now, fmt_dt, TimeSyntaxError
from typing import Protocol, Callable

from message_utils import (
    g_available_players,
    g_confirmed_start_time,
    g_debug_mode,
    g_players_needed,
    g_waiting,
    get_channel,
    set_channel,
    state,
    send,
    debug_log,
)

logger = logging.getLogger(__name__)
G_PREFIX = "!"


class CommandHandler(Protocol):
    def __call__(self, message: discord.Message, _args: str) -> CoroutineType[Message, str, None]: ...


async def reselect_first_players() -> None:
    logger.debug("function reselect_players")
    # set first X players to selected
    i = 0
    for m, (tr, _sel) in g_available_players.items():
        if i >= g_players_needed:
            break
        g_available_players.update({m: (tr, True)})
        i += 1


async def prune_players() -> None:
    logger.debug("function prune_players")
    global g_available_players
    to_delete: list[User] = []
    for m, (tr, _sel) in g_available_players.items():
        if tr.get_end_time_available() < get_now_rounded():
            await debug_log(f"pruning player {m.name} (end time {fmt_dt(tr.get_end_time_available())})")
            to_delete.append(m)
    for m in to_delete:
        del g_available_players[m]
    if len(g_available_players) < g_players_needed:
        await reselect_first_players()


async def announce_game_full() -> None:
    logger.debug("function announce_game_full")
    if get_channel() is not None:
        await debug_log("We have enough players, checking for common start time...")
        t = TimeRange.get_common_start_time([tr for (tr, sel) in g_available_players.values() if sel])
        if t is not None:
            await inform_available_players_of_agreed_time(t)
            await inform_available_players_of_start(t)
        else:
            await send("We have enough players, but their start times do not overlap")
    else:
        logger.error("Need to set channel...")


async def handle_extra_players() -> None:
    logger.debug("function handle_extra_players")
    selected: list[tuple[User, TimeRange]] = [(u, tr) for u, (tr, sel) in g_available_players.items() if sel]
    unselected: list[tuple[User, TimeRange]] = [(u, tr) for u, (tr, sel) in g_available_players.items() if not sel]
    if len(selected) < g_players_needed:
        await reselect_first_players()
        await handle_extra_players() # retry function
        return
    latest_selected: User = max(selected, key=lambda u: u[1].start_time_available)[0]
    first_unselected: User = min(unselected, key=lambda u: u[1].start_time_available)[0]
    latest_selected_user = latest_selected
    other_selected = [p[0].mention for p in selected if p[0] != latest_selected]
    msg = await send(
        f"{' '.join(other_selected)} vote to replace {latest_selected_user.mention} with {first_unselected.mention}"
    )
    if msg is None:
        logger.error("Failed to add send vote message somehow")
        return
    yes, no = "✅", "❌"
    await msg.add_reaction(yes)
    await msg.add_reaction(no)
    count_reactions: Callable[[Message, str], int] = lambda m, react: len([r for r in m.reactions if r.emoji == react])

    def vote_passes(msg: Message):
        result = (c := count_reactions(msg, yes)) > (n := math.ceil((g_players_needed - 1) / 2))
        if result:
            logger.info(f"Got {c} reactions, vote passes")
        else:
            logger.info(f"Got reaction on message but only have {c} votes yes when we we need {n}")
        return result

    try:
        _result = await client.wait_for("reaction_add", check=vote_passes, timeout=(60 * 60 * 6))
    except asyncio.TimeoutError:
        logger.info("timed out vote to replace")
        pass
    else:  # if we don't time out, then:
        await debug_log("replacing player")
        tr, _sel = g_available_players[latest_selected_user]
        g_available_players[latest_selected_user] = tr, False

        tr, _sel = g_available_players[first_unselected]
        g_available_players[first_unselected] = tr, True
        await send(f"replacing {latest_selected_user.mention} with {first_unselected.mention}")
        await announce_game_full()


async def check_player_count() -> None:
    """
    Check if we have enough players, and handle it as needed
    """
    logger.debug("function check_player_count")
    await prune_players()
    if get_channel() is None:
        return
    await debug_log("Checking player count")

    if len(g_available_players) == g_players_needed:
        await debug_log("Game full")
        await announce_game_full()
    elif len(g_available_players) > g_players_needed:
        await debug_log("Handling extra players")
        await handle_extra_players()
    else:
        await debug_log(f"Not enough players. (need {g_players_needed}, have {len(g_available_players)} total)")


async def get_current_available() -> list[tuple[Member, TimeRange]]:
    logger.debug("function get_current_available")
    global g_available_players
    await prune_players()
    out = []
    for m, (tr, _sel) in g_available_players.items():
        if tr.time_in_range(now := get_now_rounded()):
            out.append((m, tr))
            await debug_log(f"Member {str(m)} available because {str(tr.start_time_available)} < {str(now)} < {str(tr.get_end_time_available())}")
    return out


async def count_current_available() -> int:
    logger.debug("function count_current_available")
    return len(await get_current_available())


async def get_mention_available_players(*, only_selected=False, only_unselected=False) -> list[str]:
    logger.debug("function get_mention_available_players")
    global g_available_players
    await prune_players()
    return [
        player.mention
        for player, (_tr, sel) in g_available_players.items()
        if (sel if only_selected else True)
        if (not sel if only_unselected else True)
    ]


async def inform_available_players_of_start(t: datetime):
    logger.debug("function inform_available_players_of_start")
    """
    Contact everyone who says they'll play
    """
    global g_waiting, g_confirmed_start_time, g_available_players, g_debug_mode
    if get_channel() is None:
        return
    if g_waiting and g_confirmed_start_time == t:
        return
    g_confirmed_start_time = t
    delay = (t - get_now()).total_seconds()
    await debug_log(f"Waiting until {t} ({delay:.2f} seconds, current time is {get_now()})")
    g_waiting = True
    if delay > 0:
        await asyncio.sleep(delay)
    if g_confirmed_start_time != t:
        return  # someone else took over
    await send(f"{" ".join(await get_mention_available_players(only_selected=True))} time to play!")
    g_confirmed_start_time = None
    g_waiting = False
    g_available_players.clear()


async def inform_available_players_of_agreed_time(t: datetime):
    logger.debug("function inform_available_players_of_agreed_time")
    """
    Contact everyone who says they'll play
    """
    if get_channel() is None:
        return
    await send(
        f"{" ".join(await get_mention_available_players(only_selected=True))} start time has been set to {fmt_dt(t)}"
    )


async def handle_available(message: Message, _args: str) -> None:
    logger.debug("function handle_available")
    global g_available_players
    if get_channel() is None:
        await handle_setup(message, "")
    try:
        now = message.created_at.astimezone()
        is_selected = len(g_available_players) < g_players_needed
        g_available_players[message.author] = (TimeRange(_args, now=now), is_selected)
        if g_debug_mode:
            await message.reply(f"got {g_available_players[message.author]}\n{state()}")
    except ValueError as e:
        if g_debug_mode:
            await message.reply(f"These numbers don't look right: {e}")
        else:
            await message.reply("These numbers don't look right...")
    except TimeSyntaxError as e:
        await message.reply(e.message)
    else:
        await message.add_reaction("👍")
        await check_player_count()


async def handle_unavailable(message: Message, _args: str) -> None:
    logger.debug("function handle_unavailable")
    global g_available_players, g_confirmed_start_time
    if get_channel() is None:
        await handle_setup(message, "")
    await prune_players()
    author: User = message.author
    if author not in g_available_players.keys():
        await message.reply(f"We weren't expecting you!")
        return
    user_was_selected: bool = g_available_players[author][1]
    del g_available_players[author]  # delete em!
    await message.add_reaction("🖕" if user_was_selected else "👋")

    if user_was_selected:
        if len(g_available_players) == g_players_needed - 1:
            g_confirmed_start_time = None
            other_selected_players: list[str] = [
                player for player in await get_mention_available_players(only_selected=True) if player != author
            ]
            await send(f"{' '.join(other_selected_players)} game has been cancelled due to {author.mention}, boo him")
        elif len(g_available_players) >= g_players_needed:

            await send(f"replaced {author.mention}")
            await reselect_first_players()
            await check_player_count()


async def handle_setup(message: Message, _args: str) -> None:
    logger.debug("function handle_setup")
    if isinstance(message.channel, discord.TextChannel):
        set_channel(message.channel)
        logger.info(f"get_channel() becomes {message.channel=}: {get_channel()=}")
        # await send(f'the channel "{message.channel}" ({message.channel.id}) is now where I will be sending messages')


async def enable_debug(message: Message, _args: str) -> None:
    logger.debug("function enable_debug")
    if get_channel() is None:
        await handle_setup(message, "")
    global g_debug_mode
    g_debug_mode = True
    await send("debug mode on")


async def disable_debug(message: Message, _args: str) -> None:
    logger.debug("function disable_debug")
    if get_channel() is None:
        await handle_setup(message, "")
    global g_debug_mode
    g_debug_mode = False
    await send("debug mode off")


async def handle_count(message: Message, _args: str) -> None:
    logger.debug("function handle_count")
    if get_channel() is None:
        await handle_setup(message, "")
    global g_players_needed
    if len(_args.strip()) == 0:
        await message.reply(f"We need {g_players_needed} players")
        return
    if not _args.isnumeric():
        await message.reply(f'Can\'t make a number out of "{_args}"')
    else:
        g_players_needed = int(_args)
        await message.reply(f'Players needed is now "{_args}"')
        await check_player_count()


async def handle_status(message: Message, _args: str) -> None:
    logger.debug("function handle_status")
    if get_channel() is None:
        await handle_setup(message, "")
    await prune_players()
    s = f"({await count_current_available()}/{g_players_needed}) players currently available"
    if g_confirmed_start_time is not None:
        s += f"\nStart time confirmed for: {fmt_dt(g_confirmed_start_time)}"
    if g_debug_mode:
        s += f"\nDEBUG MODE ON\nCURRENT TIME {fmt_dt(get_now_rounded())}\n{state()}"
    global g_available_players
    available_emoji = "✅"
    unavailable_emoji = "❌"
    sel_players: list[tuple[User, TimeRange]] = [(m, tr) for m, (tr, sel) in g_available_players.items() if sel]
    unsel_players: list[tuple[User, TimeRange]] = [(m, tr) for m, (tr, sel) in g_available_players.items() if not sel]
    for m, tr in sel_players:
        emoji = available_emoji if tr.time_in_range(get_now()) else unavailable_emoji
        s += f"\n{emoji} {m.name}: {str(tr)}"
    if len(unsel_players) > 0:
        s += f"\nBackup players:"
        for m, tr in unsel_players:
            emoji = available_emoji if tr.time_in_range(get_now()) else unavailable_emoji
            s += f"\n{emoji} {m.name}: {str(tr)}"
    await message.reply(s)


async def handle_help(message: Message, _args: str) -> None:
    logger.debug("function handle_help")
    if get_channel() is None:
        await handle_setup(message, "")
    await message.reply("All commands: " + ", ".join(f"!{k}" for k in func_map.keys()))


func_map: OrderedDict[str, CommandHandler] = OrderedDict(
    {
        "help": handle_help,
        "available": handle_available,
        "unavailable": handle_unavailable,
        "setup": handle_setup,
        "debug": enable_debug,
        "nodebug": disable_debug,
        "count": handle_count,
        "status": handle_status,
    }
)
