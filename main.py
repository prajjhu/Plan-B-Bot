import discord
import os
import random
import time
import asyncio
from openai import AsyncOpenAI

# ================= CONFIG =================
PREFIX = "="
JAIL_CHANNELS = ["jail-1", "jail-2"]
WARNING_TIMEOUT = 60
# ==========================================

client_ai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)

user_warnings = {}
user_last_message_time = {}

# ------------------ AI ANALYSIS ------------------
async def analyze_message(message_content):
    try:
        response = await client_ai.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a VERY lenient moderation AI.\n\n"
                        "SAFE = jokes, sarcasm, casual insults\n"
                        "LOW = mild negativity but not harmful\n"
                        "MEDIUM = clear targeted harassment\n"
                        "HIGH = threats, hate speech, or harmful intent\n\n"
                        "Do NOT overreact.\n"
                        "Respond ONLY with: SAFE, LOW, MEDIUM, or HIGH"
                    )
                },
                {"role": "user", "content": message_content}
            ]
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"AI error: {e}")
        return "SAFE"

# ------------------ JAIL FUNCTION ------------------
async def jail_user(member, guild, channel):
    role = discord.utils.get(guild.roles, name="Jailed")
    mod_role = discord.utils.get(guild.roles, name="Moderator")

    try:
        if role:
            await member.add_roles(role)
    except Exception as e:
        print(f"Role assign error: {e}")

    if mod_role:
        await channel.send(
            f"{mod_role.mention} User {member.mention} has been jailed for review.",
            delete_after=10
        )

# ------------------ CLEANUP FUNCTION ------------------
async def cleanup_messages(channel, user):
    def check(msg):
        return msg.author == user

    try:
        await channel.purge(limit=3, check=check)
    except Exception as e:
        print(f"Cleanup error: {e}")

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
    is_jail_channel = message.channel.name in JAIL_CHANNELS

    # ------------------ TIME DECAY ------------------
    current_time = time.time()
    if user_id in user_last_message_time:
        if current_time - user_last_message_time[user_id] > WARNING_TIMEOUT:
            user_warnings[user_id] = 0
    user_last_message_time[user_id] = current_time

    # ------------------ BOT MENTION ------------------
    if client.user in message.mentions:
        await message.channel.send("Hey 👋 I'm here. What's up?", delete_after=5)
        return

    # ==================================================
    # 🔒 JAIL CHANNEL LOGIC
    # ==================================================
    if is_jail_channel:

        if message.content.startswith(PREFIX + "release"):
            if message.author.guild_permissions.administrator:
                if message.mentions:
                    user = message.mentions[0]
                    role = discord.utils.get(message.guild.roles, name="Jailed")

                    try:
                        if role:
                            await user.remove_roles(role)
                            await message.delete(delay=5)
                            await message.channel.send(
                                f"{user.mention} has been released.",
                                delete_after=5
                            )
                    except Exception as e:
                        print(f"Release error: {e}")
            return

        # Only stop extreme spam
        if len(message.content) > 400 or message.content.count("\n") > 5:
            try:
                await message.delete()
                await message.channel.send(
                    "Let’s keep messages reasonable here.",
                    delete_after=5
                )
            except Exception as e:
                print(f"Jail moderation error: {e}")

        return

    # ==================================================
    # 🤖 AI CHAT SYSTEM
    # ==================================================
    if message.content.startswith(PREFIX + "chat"):

        allowed_role = discord.utils.get(message.guild.roles, name="AI Access")
        if allowed_role not in message.author.roles:
            return

        user_input = message.content[len(PREFIX + "chat"):].strip()

        if not user_input:
            await message.channel.send("Say something after =chat", delete_after=5)
            return

        try:
            response = await client_ai.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful, friendly assistant."},
                    {"role": "user", "content": user_input}
                ]
            )

            reply = response.choices[0].message.content
            await message.channel.send(reply[:2000])

        except Exception as e:
            print(e)
            await message.channel.send("Something went wrong.", delete_after=5)

        return

    # ==================================================
    # 🌍 NORMAL MODERATION (LENIENT AI TRIGGER)
    # ==================================================

    suspicious_keywords = [
        "kill", "die", "kys", "worthless",
        "nobody likes you", "go kill yourself",
        "rape", "threat"
    ]

    if any(word in content for word in suspicious_keywords):
        result = await analyze_message(message.content)
    else:
        result = "SAFE"

    # ------------------ RESPONSES ------------------
    guardian_responses = [
        "Let’s keep it chill 🙂",
        "No need to take it that far.",
        "Keep things respectful 👍"
    ]

    enforcer_responses = [
        "This is getting a bit much, let’s stop here.",
        "You’re pushing it now.",
        "Let’s not continue like this."
    ]

    sentinel_responses = [
        "This crosses the line.",
        "This kind of content isn’t allowed.",
        "Moderation has stepped in."
    ]

    # ------------------ LEVEL SYSTEM ------------------

    if result == "LOW":
        user_warnings[user_id] = user_warnings.get(user_id, 0) + 1

        if user_warnings[user_id] >= 3:
            await asyncio.sleep(1.5)
            await message.channel.send(random.choice(guardian_responses), delete_after=5)
            user_warnings[user_id] = 0

    elif result == "MEDIUM":
        await asyncio.sleep(1.5)
        await message.channel.send(random.choice(enforcer_responses), delete_after=5)
        await cleanup_messages(message.channel, message.author)
        await jail_user(message.author, message.guild, message.channel)

    elif result == "HIGH":
        await asyncio.sleep(1.5)
        await message.channel.send(random.choice(sentinel_responses), delete_after=5)
        await cleanup_messages(message.channel, message.author)
        await jail_user(message.author, message.guild, message.channel)

client.run(os.getenv("TOKEN"))
