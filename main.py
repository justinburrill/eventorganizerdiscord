#!/bin/env python3
import discord
from command_handlers import CommandHandler, func_map, G_PREFIX
import json
from discord_globals import client

file = open("info.json", "r")
SECRET_TOKEN = json.load(file)["secret"]
file.close()

import logging
logger = logging.getLogger(__name__)

async def parse_command(message: discord.Message):
    message.content = message.content.lower()
    command: str = message.content.removeprefix(G_PREFIX).split(" ")[0]
    args: str = message.content.removeprefix(G_PREFIX).removeprefix(command).strip()
    if len(command) == 0 or "!" in command:
        # this is when someone sends a exclamation mark or !!!!
        return
    f: CommandHandler | None = func_map.get(command)
    if f is None:
        is_match: list[bool] = list(
            map(lambda k: k.startswith(command), keys := list(func_map.keys()))
        )
        matched_commands = [keys[i] for i in range(len(is_match)) if is_match[i]]
        if (count := is_match.count(True)) == 1:  # found command!
            f = func_map.get(matched_commands[0])
        elif count > 1:
            return await message.channel.send(
                f'Ambiguous command: "{command}" ({", ".join(matched_commands)})'
            )
        else:
            return await message.channel.send(f"huh? what does that mean?")
    if f is None:
        raise TypeError("")
    _ = await f(message, args)  # call the handle command function


@client.event
async def on_ready():
    print(f"We have logged in as {client.user}")


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:  # skip if I sent this message
        return
    if message.content.startswith(G_PREFIX):
        try:
            await parse_command(message)
        except BaseException as e:
            print(f"failed to parse command: {e}")
            await message.reply("failed to parse command. sorry.")


def main():
    logging.basicConfig(level=logging.INFO)
    logger.info("starting...")
    client.run(SECRET_TOKEN)
    logger.info("exiting???")


if __name__ == "__main__":
    main()
