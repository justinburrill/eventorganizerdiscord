import asyncio
import math
from collections import OrderedDict
from datetime import datetime
from types import CoroutineType
from discord_globals import client

from times import TimeRange
import discord
from discord import Member, Message
from discord.abc import User
from utils import get_now_rounded, get_now, remove_any, fmt_dt, TimeSyntaxError
from typing import Protocol, Callable

from message_utils import (
    g_available_players,
    g_channel,
    g_confirmed_start_time,
    g_debug_mode,
    g_players_needed,
    g_waiting,
    state,
    send,
)


class CommandHandler(Protocol):
    def __call__(
        self, message: discord.Message, _args: str
    ) -> CoroutineType[Message, str, None]: ...


PREFIX = "!"


async def prune_players() -> None:
    global g_available_players
    to_delete: list[User] = []
    for m, (tr, _sel) in g_available_players.items():
        if tr.get_end_time_available() < get_now_rounded():
            if g_debug_mode:
                await send(
                    f"pruning player {m.name} (end time {fmt_dt(tr.get_end_time_available())})"
                )
            to_delete.append(m)
    for m in to_delete:
        del g_available_players[m]


async def announce_game_full() -> None:
    if g_channel is not None:
        if g_debug_mode:
            await send("We have enough players, checking for common start time...")
        t = TimeRange.get_common_start_time([tr for (tr, _sel) in g_available_players.values()])
        if t is not None:
            await inform_available_players_of_agreed_time(t)
            await inform_available_players_of_start(t)
        else:
            await send("We have enough players, but their start times do not overlap")
    else:
        print("Need to set channel...")


async def handle_extra_players() -> None:
    if g_debug_mode:
        await send("Handling extra players")
    selected: list[tuple[User, TimeRange]] = [
        (u, tr) for u, (tr, sel) in g_available_players.items() if sel
    ]
    unselected: list[tuple[User, TimeRange]] = [
        (u, tr) for u, (tr, sel) in g_available_players.items() if not sel
    ]
    latest_selected: User = max(selected, key=lambda u: u[1].start_time_available)[0]
    first_unselected: User = min(unselected, key=lambda u: u[1].start_time_available)[0]
    latest_selected_user = latest_selected
    other_selected = [p[0].mention for p in selected if p[0] != latest_selected]
    msg = await send(
        f"{other_selected} vote to replace {latest_selected_user.mention} with {first_unselected.mention}"
    )
    if msg is None:
        print("Failed to add reacts to message")
        return
    yes = "✅"
    no = "❌"
    await msg.add_reaction(yes)
    await msg.add_reaction(no)
    count_reactions = lambda m, react: len([r for r in m.reactions if r.emoji == react])
    vote_passes: Callable[[Message], bool] = lambda m: count_reactions(m, yes) > (
        math.ceil((g_players_needed - 1) / 2)
    )
    try:
        _result = await client.wait_for("reaction_add", check=vote_passes, timeout=(60 * 60 * 6))
    except asyncio.TimeoutError:
        pass
    else:
        tr, _sel = g_available_players[latest_selected_user]
        g_available_players[latest_selected_user] = tr, False

        tr, _sel = g_available_players[first_unselected]
        g_available_players[first_unselected] = tr, True
        if g_debug_mode:
            await send(f"replacing {latest_selected_user.mention} with {first_unselected.mention}")
        await announce_game_full()


async def check_player_count() -> None:
    """
    Check if we have enough players, and handle it as needed
    """
    await prune_players()
    if g_channel is None:
        return

    if (count := len(g_available_players)) == g_players_needed:
        if g_debug_mode:
            await send("Game full")
        await announce_game_full()
    if count > g_players_needed:
        await handle_extra_players()
    elif g_debug_mode:
        await send(f"Not enough players. (need {g_players_needed}, have {count} total)")


async def get_current_available() -> list[tuple[Member, TimeRange]]:
    global g_available_players
    await prune_players()
    out = []
    for m, (tr, _sel) in g_available_players.items():
        if tr.time_in_range((now := get_now_rounded())):
            out.append((m, tr))
            if g_debug_mode:
                await send(
                    f"Member {str(m)} available because {str(tr.start_time_available)} < {str(now)} < {str(tr.get_end_time_available())}"
                )
    return out


async def count_current_available() -> int:
    return len(await get_current_available())


async def get_mention_available_players(*, only_selected=True, only_unselected=True) -> list[str]:
    global g_available_players
    await prune_players()
    return [
        player.mention
        for player, (_tr, sel) in g_available_players.items()
        if (sel if only_selected else True)
        if (not sel if only_unselected else True)
    ]


async def inform_available_players_of_start(t: datetime):
    """
    Contact everyone who says they'll play
    """
    global g_waiting
    global g_confirmed_start_time
    global g_available_players
    if g_channel is None:
        return
    if g_waiting and g_confirmed_start_time == t:
        return
    g_confirmed_start_time = t
    delay = (t - get_now()).total_seconds()
    if g_debug_mode:
        await send(f"Waiting until {t} ({delay:.2f} seconds, current time is {get_now()})")
    g_waiting = True
    if delay > 0:
        await asyncio.sleep(delay)
    if g_confirmed_start_time != t:
        return  # someone else took over
    await send(f"{" ".join(await get_mention_available_players())} time to play!")
    g_available_players.clear()
    g_confirmed_start_time = None
    g_waiting = False


async def inform_available_players_of_agreed_time(t: datetime):
    """
    Contact everyone who says they'll play
    """
    if g_channel is None:
        return
    await send(
        f"{" ".join(await get_mention_available_players())} start time has been set to {fmt_dt(t)}"
    )


async def handle_available(message: Message, _args: str) -> None:
    global g_available_players
    if g_channel is None:
        await handle_setup(message, "")
    try:
        now = message.created_at.astimezone()
        _args = remove_any(_args, ["now"]) # TODO: ???
        is_selected = True if len(g_available_players) < g_players_needed else False
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
        await check_player_count()
        await message.add_reaction("👍")


async def handle_unavailable(message: Message, _args: str) -> None:
    global g_available_players, g_confirmed_start_time, g_channel
    if g_channel is None:
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
        if len(g_available_players) < g_players_needed:
            g_confirmed_start_time = None
            other_selected_players: list[str] = [
                player
                for player in await get_mention_available_players(only_selected=True)
                if player != author
            ]
            await send(
                f"{' '.join(other_selected_players)} game has been cancelled due to {author.mention}, boo him"
            )
        elif len(g_available_players) >= g_players_needed:
            i = 0
            # set first X players to selected
            for m, (tr, _sel) in g_available_players.items():
                if i >= g_players_needed:
                    break
                g_available_players.update({m: (tr, True)})
                i += 1

            await send("...")


async def handle_setup(message: Message, _args: str) -> None:
    global g_channel
    if isinstance(message.channel, discord.TextChannel):
        g_channel = message.channel
        await g_channel.send(
            f'the channel "{g_channel.name}" ({g_channel.id}) is now where I will be sending messages'
        )


async def enable_debug(message: Message, _args: str) -> None:
    if g_channel is None:
        await handle_setup(message, "")
    global g_debug_mode
    g_debug_mode = True
    await message.channel.send("debug mode on")


async def disable_debug(message: Message, _args: str) -> None:
    if g_channel is None:
        await handle_setup(message, "")
    global g_debug_mode
    g_debug_mode = False
    await message.channel.send("debug mode off")


async def handle_count(message: Message, _args: str) -> None:
    if g_channel is None:
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
    if g_channel is None:
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
    sel_players: list[tuple[User, TimeRange]] = [
        (m, tr) for m, (tr, sel) in g_available_players.items() if sel
    ]
    unsel_players: list[tuple[User, TimeRange]] = [
        (m, tr) for m, (tr, sel) in g_available_players.items() if not sel
    ]
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
    if g_channel is None:
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
