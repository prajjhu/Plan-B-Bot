import discord
import os
import random
import time
import asyncio
import re
from openai import AsyncOpenAI

# ================= CONFIG =================
# ----made by ap.snake--------
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

# ------------------ SENTINEL ------------------
INSTANT_JAIL_WORDS = [
    "nigger", "faggot", "rape", "pedophile",
    "nazi", "hitler", "heil", "childporn", "kanker"
]

SEVERE_PHRASES = [
    "kill yourself",
    "fucking die",
    "nobody loves you",
    "suicide"
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
            "Easy there.",
            "Let’s keep it chill.",
            "No need for that.",
            "Keep it respectful."
        ],
        "enforce": [
            "That’s getting out of hand.",
            "You’re pushing it now.",
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
                        "You are a VERY lenient moderation AI.\n\n"
                        "Context matters more than words.\n"
                        "Most messages are jokes or friendly.\n\n"
                        "SAFE = friendly or joking\n"
                        "LOW = mild negativity\n"
                        "MEDIUM = targeted harassment\n"
                        "HIGH = real threats or harmful intent\n\n"
                        "If it seems friendly, return SAFE.\n"
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
# -----I love you my Aditi always and forever <3-------
@client.event
async def on_message(message):

    if message.author == client.user:
        return

    user_id = str(message.author.id)
    content = message.content.lower()
    normalized = normalize_text(content)
    is_jail = message.channel.name in JAIL_CHANNELS
    now = time.time()

    # ------------------ DECAY ------------------
    if user_id in user_last_message_time:
        if now - user_last_message_time[user_id] > WARNING_TIMEOUT:
            user_warnings[user_id] = 0
    user_last_message_time[user_id] = now

    # ------------------ MENTION ------------------
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
    # 🔴 HARD SENTINEL
    # ==================================================
    if any(w in content or w in normalized for w in INSTANT_JAIL_WORDS):
        await message.delete()
        await message.channel.send(random_reply("severe"), delete_after=5)
        await cleanup_messages(message.channel, message.author)
        await jail_user(message.author, message.guild, message.channel)
        return

    # ==================================================
    # 🧠 AI CONTEXT CHECK
    # ==================================================
    if any(p in content for p in SEVERE_PHRASES):
        result = await analyze_message(message.content)
    else:
        result = "SAFE"

    if result == "MEDIUM":
        await message.channel.send(random_reply("enforce"), delete_after=5)
        await cleanup_messages(message.channel, message.author)
        await jail_user(message.author, message.guild, message.channel)
        return

    elif result == "HIGH":
        await message.delete()
        await message.channel.send(random_reply("severe"), delete_after=5)
        await cleanup_messages(message.channel, message.author)
        await jail_user(message.author, message.guild, message.channel)
        return

    # ==================================================
    # 🧩 BEHAVIOR SYSTEM
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

    # Flood
    user_message_times.setdefault(user_id, []).append(now)
    user_message_times[user_id] = [t for t in user_message_times[user_id] if now - t < 5]

    if len(user_message_times[user_id]) >= 6:
        await message.channel.send("Slow down.", delete_after=5)
        await cleanup_messages(message.channel, message.author)
        await jail_user(message.author, message.guild, message.channel)
        return

    # Escalation (IMPORTANT ADD BACK)
    user_recent_messages.setdefault(user_id, []).append(content)
    user_recent_messages[user_id] = user_recent_messages[user_id][-5:]

    combined = " ".join(user_recent_messages[user_id])

    if any(w in combined for w in ["fuck you", "idiot", "retard"]):
        if len(user_recent_messages[user_id]) >= 5:
            await message.channel.send(random_reply("enforce"), delete_after=5)
            await cleanup_messages(message.channel, message.author)
            await jail_user(message.author, message.guild, message.channel)
            return

client.run(os.getenv("TOKEN"))
