import discord
import os
import random
import time
import asyncio
import re
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

user_warning_timestamps = {}

# ------------------ SENTINEL WORDS ------------------
INSTANT_JAIL_WORDS = [
    "nigger", "faggot", "rape", "pedophile",
    "nazi", "hitler", "heil", "childporn", "kanker"
]

WARNING_WORDS = [
    "nigga", "asshole", "cocksucker", "twat",
    "cunt", "whore", "kill yourself", "fucking die",
    "nobody loves you", "suicide"
]

# ------------------ NORMALIZE ------------------
def normalize_text(text):
    text = text.lower()

    replacements = {
        "@": "a", "4": "a", "0": "o",
        "1": "i", "$": "s"
    }

    for k, v in replacements.items():
        text = text.replace(k, v)

    text = re.sub(r'[\W_]+', '', text)
    text = re.sub(r'(.)\1+', r'\1', text)

    return text

# ------------------ PERSONALITY ------------------
def random_reply(level):
    return random.choice({
        "warn": [
            "Let’s not go there.",
            "Keep it clean.",
            "Easy there.",
            "We don’t need that."
        ],
        "enforce": [
            "That’s getting out of hand.",
            "You’re pushing it.",
            "Let’s stop here."
        ],
        "severe": [
            "Yeah… not happening.",
            "That crosses the line.",
            "Nope. Not allowed."
        ]
    }[level])

# ------------------ AI ------------------
async def analyze_message(text):
    try:
        res = await client_ai.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a VERY lenient moderation AI.\n"
                        "Most messages are jokes.\n"
                        "SAFE = normal/joking\n"
                        "LOW = mild negativity\n"
                        "MEDIUM = harassment\n"
                        "HIGH = real threats\n"
                        "Respond ONLY SAFE, LOW, MEDIUM, HIGH"
                    )
                },
                {"role": "user", "content": text}
            ]
        )
        return res.choices[0].message.content.strip()
    except:
        return "SAFE"

# ------------------ JAIL ------------------
async def jail_user(member, guild, channel):
    role = discord.utils.get(guild.roles, name="Jailed")
    mod_role = discord.utils.get(guild.roles, name="Moderator")

    if role:
        try:
            await member.add_roles(role)
        except:
            pass

    if mod_role:
        await channel.send(
            f"{mod_role.mention} {member.mention} jailed.",
            delete_after=10
        )

# ------------------ CLEANUP ------------------
async def cleanup_messages(channel, user):
    def check(msg):
        return msg.author == user
    try:
        await channel.purge(limit=5, check=check)
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
    normalized = normalize_text(content)
    is_jail = message.channel.name in JAIL_CHANNELS

    now = time.time()

    # ------------------ TIME DECAY ------------------
    if user_id in user_last_message_time:
        if now - user_last_message_time[user_id] > WARNING_TIMEOUT:
            user_warnings[user_id] = 0
    user_last_message_time[user_id] = now

    # ------------------ BOT MENTION ------------------
    if client.user in message.mentions:
        await message.channel.send("Hey 👋", delete_after=5)
        return

    # ==================================================
    # 🔒 JAIL CHANNEL
    # ==================================================
    if is_jail:

        if content.startswith(PREFIX + "release"):
            if message.author.guild_permissions.administrator and message.mentions:
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

        if len(content) > 250 or content.count("\n") > 5:
            await message.delete()
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

        res = await client_ai.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are friendly."},
                {"role": "user", "content": prompt}
            ]
        )

        await message.channel.send(res.choices[0].message.content[:2000])
        return

    # ==================================================
    # 🔴 SENTINEL SYSTEM
    # ==================================================

    # Instant jail
    if any(w in content or w in normalized for w in INSTANT_JAIL_WORDS):
        await message.delete()
        await message.channel.send(random_reply("severe"), delete_after=5)
        await cleanup_messages(message.channel, message.author)
        await jail_user(message.author, message.guild, message.channel)
        return

    # Warning escalation system (20 sec window)
    if any(w in content or w in normalized for w in WARNING_WORDS):

        await message.delete()

        user_warning_timestamps.setdefault(user_id, []).append(now)

        user_warning_timestamps[user_id] = [
            t for t in user_warning_timestamps[user_id] if now - t <= 20
        ]

        count = len(user_warning_timestamps[user_id])

        if count == 5:
            await message.channel.send(random_reply("warn"), delete_after=5)
            return

        if count > 5:
            await message.channel.send(random_reply("enforce"), delete_after=5)
            await cleanup_messages(message.channel, message.author)
            await jail_user(message.author, message.guild, message.channel)
            user_warning_timestamps[user_id] = []
            return

        return

    # ==================================================
    # 🧠 BEHAVIOR DETECTION
    # ==================================================

    # Repeat spam
    user_last_content.setdefault(user_id, content)
    user_repeat_count[user_id] = user_repeat_count.get(user_id, 0)

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

    # Flood detection
    user_message_times.setdefault(user_id, []).append(now)
    user_message_times[user_id] = [t for t in user_message_times[user_id] if now - t < 5]

    if len(user_message_times[user_id]) >= 6:
        await message.channel.send("Slow down.", delete_after=5)
        await cleanup_messages(message.channel, message.author)
        await jail_user(message.author, message.guild, message.channel)
        return

    # Escalation
    user_recent_messages.setdefault(user_id, []).append(content)
    user_recent_messages[user_id] = user_recent_messages[user_id][-5:]

    combined = " ".join(user_recent_messages[user_id])

    if any(w in combined for w in ["fuck you", "idiot", "retard"]):
        if len(user_recent_messages[user_id]) >= 5:
            await message.channel.send(random_reply("enforce"), delete_after=5)
            await cleanup_messages(message.channel, message.author)
            await jail_user(message.author, message.guild, message.channel)
            return

    # ==================================================
    # 🧠 AI MODERATION
    # ==================================================

    suspicious = [
        "kys", "kill yourself", "go kill yourself",
        "worthless", "nobody likes you",
        "rape", "threat"
    ]

    if any(w in content for w in suspicious):
        result = await analyze_message(message.content)
    else:
        result = "SAFE"

    if result == "LOW":
        user_warnings[user_id] = user_warnings.get(user_id, 0) + 1
        if user_warnings[user_id] >= 3:
            await message.channel.send(random_reply("warn"), delete_after=5)
            user_warnings[user_id] = 0

    elif result == "MEDIUM":
        await message.channel.send(random_reply("enforce"), delete_after=5)
        await cleanup_messages(message.channel, message.author)
        await jail_user(message.author, message.guild, message.channel)

    elif result == "HIGH":
        await message.channel.send(random_reply("severe"), delete_after=5)
        await cleanup_messages(message.channel, message.author)
        await jail_user(message.author, message.guild, message.channel)

client.run(os.getenv("TOKEN"))
