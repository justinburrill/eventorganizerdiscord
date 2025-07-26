import discord
from command_handlers import func_map, PREFIX
import json

file = open("info.json", "r")
SECRET_TOKEN = json.load(file)["secret"]
file.close()

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

client = discord.Client(intents=intents)


async def parse_command(message):
    command: str = message.content.removeprefix(PREFIX).split(" ")[0]
    args: str = message.content.removeprefix(PREFIX).removeprefix(command).strip()
    f: callable = func_map.get(command)
    if f is None:
        is_match: [bool] = list(map(lambda k: k.startswith(command), keys := list(func_map.keys())))
        matched_commands = [keys[i] for i in range(len(is_match)) if is_match[i]]
        if (count := is_match.count(True)) == 1:  # found command!
            f = func_map.get(matched_commands[0])
        elif count > 1:
            return await message.channel.send(f"Ambiguous command: '{command}' ({", ".join(matched_commands)})")
        else:
            return await message.channel.send(f"huh? what does that mean?")

    _ = await f(message, args)  # call the handle command function


@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:  # skip if I sent this message
        return
    if message.content.startswith(PREFIX):
        await parse_command(message)


def main():
    client.run(SECRET_TOKEN)


if __name__ == "__main__":
    main()
