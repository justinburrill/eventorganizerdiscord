from collections import OrderedDict
from discord.abc import User

from datetime import datetime, timedelta
import logging
from message_utils import debug_log
from times import TimeRange
from utils import fmt_dt, get_now_rounded
from globals import g_players_needed

logger = logging.getLogger(__name__)

class AvailablePlayers:
    # name : (times available)
    unselected_players: OrderedDict[User, TimeRange]
    selected_players: OrderedDict[User, TimeRange]
    # name : (times available, when game started)
    playing_players: dict[User, tuple[TimeRange, datetime]]

    def __init__(self):
        self.unselected_players = OrderedDict()
        self.selected_players = OrderedDict()
        self.playing_players = {}

    def start_game(self):
        """
        Move selected players to playing
        """
        self.playing_players = {u: (tr, datetime.now()) for (u, tr) in self.selected_players.items()}
        self.selected_players.clear()

    def items(self) -> list[tuple[User, tuple[TimeRange, bool]]]:
        return [(u, (tr, sel)) for (u, tr, sel)
                in [(u, tr, True) for u, tr in self.selected_players.items()] + [(u, tr, False) for u, tr in self.unselected_players.items()]]

    def values(self) -> list[tuple[TimeRange, bool]]:
        return [(tr, sel) for (_, (tr, sel)) in self.items()]

    def keys(self) -> list[User]:
        return [u for (u, _) in self.items()]

    def __len__(self) -> int:
        """
        Selected and unselected players
        """
        return len(self.unselected_players) + len(self.selected_players)

    def add_player(self, player: User, timerange: TimeRange):
        if self.has_enough_players():
            self.unselected_players[player] = timerange
        else:
            self.selected_players[player] = timerange

    def user_is_selected(self, player: User) -> bool:
        return player in self.selected_players

    def has_enough_players(self) -> bool:
        return len(self.selected_players) >= g_players_needed

    def select_player(self, player: User):
        if player not in self.unselected_players:
            logger.error(f"can't select player: {player} because they aren't unselected")
            return
        self.selected_players[player] = self.unselected_players[player]
        del self.unselected_players[player]

    def deselect_player(self, player: User):
        if player not in self.selected_players:
            logger.error(f"can't deselect player: {player} because they aren't selected")
            return
        self.unselected_players[player] = self.selected_players[player]
        del self.selected_players[player]

    def deselect_all_players(self):
        for p, tr in self.selected_players.items():
            self.unselected_players[p] = tr
        self.selected_players.clear()

    def reselect_first_available_players(self):
        self.deselect_all_players()
        for ( i, m ) in enumerate(self.unselected_players):
            if i >= g_players_needed:
                break
            self.select_player(m)

    def delete(self, player: User):
        self.playing_players.pop(player, None)
        self.unselected_players.pop(player, None)
        self.selected_players.pop(player, None)

    async def prune(self):
        to_delete: list[User] = []
        for m, (tr, _sel) in self.items():
            if tr.get_end_time_available() < get_now_rounded():
                await debug_log(f"pruning player {m.name} (end time {fmt_dt(tr.get_end_time_available())})")
                to_delete.append(m)
        for m in to_delete:
            self.delete(m)
        if len(self) < g_players_needed:
            self.reselect_first_available_players()

        game_length = timedelta(minutes=25)
        for (m, (tr, start_time)) in self.playing_players.items():
            end_time = start_time + game_length
            if datetime.now() > end_time:
                del self.playing_players[m]
                self.selected_players[m] = tr
                self.delete(m)




g_available_players: AvailablePlayers = AvailablePlayers()
