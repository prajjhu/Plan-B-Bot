import discord
import os
from openai import AsyncOpenAI

client_ai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)

user_warnings = {}

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

async def analyze_message(message_content):
    response = await client_ai.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a moderation AI with three severity levels. "
                    "Classify the message and respond with ONLY one word:\n"
                    "LOW — mild rudeness, casual insults, or minor disruption.\n"
                    "MEDIUM — repeated disruptive behaviour, targeted insults, or provocative content.\n"
                    "HIGH — serious harassment, hate speech, threats, or harmful intent.\n"
                    "SAFE — normal, acceptable conversation."
                )
            },
            {
                "role": "user",
                "content": message_content
            }
        ]
    )

    return response.choices[0].message.content.strip()

async def jail_user(member, guild):
    role = discord.utils.get(guild.roles, name="jailed")
    if role:
        await member.add_roles(role)

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if client.user in message.mentions:
        await message.channel.send("Hey 👋 I'm here. What's up?")
        return

    if message.content == "!testjail":
        if message.author.guild_permissions.administrator:
            await jail_user(message.author, message.guild)
            await message.channel.send("Test: You have been jailed.")
        else:
            await message.channel.send("You don't have permission to use this.")
        return

    user_id = str(message.author.id)

    try:
        result = await analyze_message(message.content)
    except:
        result = "SAFE"

    # 🟢 LEVEL 1 — Guardian
    if result == "LOW":
        user_warnings[user_id] = user_warnings.get(user_id, 0) + 1

        if user_warnings[user_id] >= 2:
            await message.channel.send("Alright, let's keep it respectful 👍")
            user_warnings[user_id] = 0

    # 🔵 LEVEL 2 — Enforcer
    elif result == "MEDIUM":
        await message.channel.send("Please stop this behavior. You're being disruptive.")

    # 🔴 LEVEL 3 — Sentinel
    elif result == "HIGH":
        await message.channel.send("This violates critical rules. Moderators have been alerted.")

    # SAFE → do nothing

client.run(os.getenv("DISCORD_TOKEN"))
