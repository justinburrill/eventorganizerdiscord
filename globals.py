from datetime import datetime
from discord import TextChannel

g_players_needed: int = 5
g_channel: TextChannel | None = None
g_debug_mode: bool = False
g_confirmed_start_time: datetime | None = None
g_waiting: bool = False
