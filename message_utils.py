
from discord import TextChannel, Message
import logging

from globals import g_debug_mode, g_channel

logger = logging.getLogger(__name__)


async def debug_log(msg) -> None:
    logger.debug(msg)
    if g_debug_mode:
        await send(msg)

def get_channel() -> TextChannel | None:
    return g_channel


def set_channel(c: TextChannel) -> None:
    global g_channel
    g_channel = c




async def send(message: str) -> Message | None:
    logger.info(f"sending message: {message}")
    channel = get_channel()
    if channel is not None:
        return await channel.send(message)
    else:
        logger.warning(f"not sending message because {channel=}")
        return None
