import discord
import os
import random
import time
import asyncio
from openai import AsyncOpenAI

# AI disabled for now
client_ai = None

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)

# Memory
user_warnings = {}
user_last_message_time = {}

WARNING_TIMEOUT = 60  # seconds

# ------------------ JAIL FUNCTION ------------------
async def jail_user(member, guild):
    role = discord.utils.get(guild.roles, name="Jailed")
    if role:
        await member.add_roles(role)

# ------------------ READY ------------------
@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

# ------------------ MAIN ------------------
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    user_id = str(message.author.id)
    content = message.content.lower()

    # ------------------ TIME DECAY ------------------
    current_time = time.time()

    if user_id in user_last_message_time:
        if current_time - user_last_message_time[user_id] > WARNING_TIMEOUT:
            user_warnings[user_id] = 0

    user_last_message_time[user_id] = current_time

    # ------------------ BOT MENTION ------------------
    if client.user in message.mentions:
        await message.channel.send("Hey 👋 I'm here. What's up?")
        return

    # ------------------ ADMIN COMMANDS ------------------
    if message.content == "!testjail":
        if message.author.guild_permissions.administrator:
            await jail_user(message.author, message.guild)
            await message.channel.send("Test: You have been jailed.")
        return

    if message.content.startswith("!release"):
        if message.author.guild_permissions.administrator:
            if message.mentions:
                user = message.mentions[0]
                role = discord.utils.get(message.guild.roles, name="Jailed")
                if role:
                    await user.remove_roles(role)
                    await message.channel.send(f"{user.mention} has been released.")
        return

    # ------------------ TESTING LOGIC (NO AI) ------------------
    if "spamtest" in content:
        result = "MEDIUM"
    elif "serious" in content:
        result = "HIGH"
    elif "annoying" in content:
        result = "LOW"
    else:
        result = "SAFE"

    # ------------------ RESPONSES ------------------
    guardian_responses = [
        "Alright, let’s keep it respectful 👍",
        "Let’s not take it too far.",
        "Hey, ease it down a bit.",
        "Keep it chill 🙂",
        "No need to push it further."
    ]

    enforcer_responses = [
        "This is getting disruptive, let’s stop here.",
        "You’re crossing the line now.",
        "Please tone it down.",
        "Let’s not continue like this."
    ]

    sentinel_responses = [
        "This violates critical rules.",
        "This kind of content is not allowed.",
        "Moderation has been triggered for this.",
        "This is a serious violation."
    ]

    # ------------------ LEVEL SYSTEM ------------------

    # 🟢 Guardian
    if result == "LOW":
        user_warnings[user_id] = user_warnings.get(user_id, 0) + 1

        if user_warnings[user_id] >= 3:
            await asyncio.sleep(1.5)
            await message.channel.send(random.choice(guardian_responses))
            user_warnings[user_id] = 0

    # 🔵 Enforcer
    elif result == "MEDIUM":
        await asyncio.sleep(1.5)
        await message.channel.send(random.choice(enforcer_responses))
        await jail_user(message.author, message.guild)

    # 🔴 Sentinel
    elif result == "HIGH":
        await asyncio.sleep(1.5)
        await message.channel.send(random.choice(sentinel_responses))
        await jail_user(message.author, message.guild)

    # SAFE → do nothing

client.run(os.getenv("TOKEN"))
