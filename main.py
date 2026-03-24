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

# ------------------ MEMORY ------------------
user_warnings = {}
user_last_message_time = {}

user_last_content = {}
user_repeat_count = {}

user_message_times = {}
user_recent_messages = {}

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
                        "Most messages are jokes or sarcasm.\n"
                        "Do NOT overreact.\n\n"
                        "SAFE = normal conversation or jokes\n"
                        "LOW = mild negativity\n"
                        "MEDIUM = targeted harassment\n"
                        "HIGH = real threats or harmful intent\n\n"
                        "Respond ONLY with SAFE, LOW, MEDIUM, or HIGH"
                    )
                },
                {"role": "user", "content": message_content}
            ]
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"AI error: {e}")
        return "SAFE"

# ------------------ JAIL ------------------
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
            f"{mod_role.mention} {member.mention} has been jailed.",
            delete_after=10
        )

# ------------------ CLEANUP ------------------
async def cleanup_messages(channel, user):
    def check(msg):
        return msg.author == user

    try:
        await channel.purge(limit=3, check=check)
    except:
        pass

# ------------------ READY ------------------
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

# ------------------ MAIN ------------------
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    user_id = str(message.author.id)
    content = message.content.lower()
    is_jail_channel = message.channel.name in JAIL_CHANNELS

    # ------------------ TIME DECAY ------------------
    now = time.time()
    if user_id in user_last_message_time:
        if now - user_last_message_time[user_id] > WARNING_TIMEOUT:
            user_warnings[user_id] = 0
    user_last_message_time[user_id] = now

    # ------------------ BOT MENTION ------------------
    if client.user in message.mentions:
        await message.channel.send("Hey 👋 I'm here.", delete_after=5)
        return

    # ==================================================
    # 🔒 JAIL CHANNEL
    # ==================================================
    if is_jail_channel:

        if message.content.startswith(PREFIX + "release"):
            if message.author.guild_permissions.administrator:
                if message.mentions:
                    user = message.mentions[0]
                    role = discord.utils.get(message.guild.roles, name="Jailed")

                    if role:
                        await user.remove_roles(role)
                        await message.delete(delay=5)
                        await message.channel.send(
                            f"{user.mention} released.",
                            delete_after=5
                        )
            return

        # Only block extreme spam
        if len(content) > 400 or content.count("\n") > 5:
            await message.delete()
            return

        return

    # ==================================================
    # 🤖 AI CHAT
    # ==================================================
    if content.startswith(PREFIX + "chat"):

        role = discord.utils.get(message.guild.roles, name="AI Access")
        if role not in message.author.roles:
            return

        prompt = message.content[len(PREFIX + "chat"):].strip()

        if not prompt:
            return

        response = await client_ai.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are friendly and casual."},
                {"role": "user", "content": prompt}
            ]
        )

        reply = response.choices[0].message.content
        await message.channel.send(reply[:2000])
        return

    # ==================================================
    # 🧠 BEHAVIOR DETECTION (MOST IMPORTANT)
    # ==================================================

    # 🔁 Repeat spam
    if user_id not in user_last_content:
        user_last_content[user_id] = content
        user_repeat_count[user_id] = 1
    else:
        if user_last_content[user_id] == content:
            user_repeat_count[user_id] += 1
        else:
            user_last_content[user_id] = content
            user_repeat_count[user_id] = 1

    if user_repeat_count[user_id] >= 5:
        await message.channel.send("Stop spamming.", delete_after=5)
        await cleanup_messages(message.channel, message.author)
        await jail_user(message.author, message.guild, message.channel)
        user_repeat_count[user_id] = 0
        return

    # ⚡ Flood detection
    if user_id not in user_message_times:
        user_message_times[user_id] = []

    user_message_times[user_id].append(now)
    user_message_times[user_id] = [t for t in user_message_times[user_id] if now - t < 5]

    if len(user_message_times[user_id]) >= 6:
        await message.channel.send("Slow down.", delete_after=5)
        await cleanup_messages(message.channel, message.author)
        await jail_user(message.author, message.guild, message.channel)
        return

    # 📈 Escalation detection
    if user_id not in user_recent_messages:
        user_recent_messages[user_id] = []

    user_recent_messages[user_id].append(content)
    user_recent_messages[user_id] = user_recent_messages[user_id][-5:]

    combined = " ".join(user_recent_messages[user_id])

    if any(word in combined for word in ["fuck you", "idiot", "retard"]):
        if len(user_recent_messages[user_id]) >= 5:
            await message.channel.send("You're going too far.", delete_after=5)
            await cleanup_messages(message.channel, message.author)
            await jail_user(message.author, message.guild, message.channel)
            return

    # ==================================================
    # 🧠 AI MODERATION (LENIENT)
    # ==================================================

    suspicious = [
        "kys", "kill yourself", "go kill yourself",
        "worthless", "nobody likes you",
        "rape", "threat"
    ]

    if any(word in content for word in suspicious):
        result = await analyze_message(message.content)
    else:
        result = "SAFE"

    # ------------------ RESPONSES ------------------
    if result == "LOW":
        user_warnings[user_id] = user_warnings.get(user_id, 0) + 1

        if user_warnings[user_id] >= 3:
            await message.channel.send("Keep it chill.", delete_after=5)
            user_warnings[user_id] = 0

    elif result == "MEDIUM":
        await message.channel.send("This is getting too much.", delete_after=5)
        await cleanup_messages(message.channel, message.author)
        await jail_user(message.author, message.guild, message.channel)

    elif result == "HIGH":
        await message.channel.send("This crosses the line.", delete_after=5)
        await cleanup_messages(message.channel, message.author)
        await jail_user(message.author, message.guild, message.channel)

client.run(os.getenv("TOKEN"))
