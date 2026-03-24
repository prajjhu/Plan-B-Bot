import discord
import os
import random
import time
import re
from difflib import SequenceMatcher
from openai import AsyncOpenAI

# ================= CONFIG =================
PREFIX = "="
JAIL_CHANNELS = ["jail-1", "jail-2"]
AI_CHANNEL_NAME = "ai-chat"
LOG_CHANNEL_NAME = "ai-logs"

COOLDOWN_TIME = 5
SIMILARITY_THRESHOLD = 0.85
HIGH_STRIKE_WINDOW = 30
# ==========================================

client_ai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)

# ------------------ MEMORY ------------------
user_last_content = {}
user_repeat_count = {}
user_message_times = {}
user_recent_messages = {}

user_cooldowns = {}
user_offense_count = {}

user_high_strikes = {}
user_high_timestamps = {}

# ------------------ RESET ------------------
def reset_user_state(user_id):
    user_last_content.pop(user_id, None)
    user_repeat_count.pop(user_id, None)
    user_message_times.pop(user_id, None)
    user_recent_messages.pop(user_id, None)
    user_high_strikes.pop(user_id, None)
    user_high_timestamps.pop(user_id, None)

# ------------------ SIMILARITY ------------------
def is_similar(a, b):
    return SequenceMatcher(None, a, b).ratio() >= SIMILARITY_THRESHOLD

# ------------------ CLEANUP ------------------
async def cleanup_spam(channel, user, reference, limit=30):
    def check(msg):
        return msg.author == user and is_similar(msg.content.lower(), reference.lower())
    try:
        await channel.purge(limit=limit, check=check)
    except:
        pass

# ------------------ NORMALIZE ------------------
def normalize_text(text):
    text = text.lower()
    replacements = {
        "@": "a", "4": "a", "0": "o",
        "1": "i", "3": "e", "$": "s", "!": "i"
    }
    for k, v in replacements.items():
        text = text.replace(k, v)

    text = re.sub(r'[\W_]+', '', text)
    text = re.sub(r'(.)\1+', r'\1', text)
    return text

# ------------------ LOGGING ------------------
async def log_action(guild, title, description):
    channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)
    if channel:
        embed = discord.Embed(title=title, description=description, color=discord.Color.red())
        embed.timestamp = discord.utils.utcnow()
        await channel.send(embed=embed)

# ------------------ SENTINEL ------------------
INSTANT_JAIL_WORDS = [
    "nigger", "faggot", "rape", "pedophile",
    "nazi", "hitler", "heil", "childporn", "kanker"
]

NORMALIZED_BANNED = [normalize_text(w) for w in INSTANT_JAIL_WORDS]

AI_TRIGGER_WORDS = [
    "idiot", "retard", "fuck you", "bitch",
    "nigga", "kill", "die", "hate", "stupid"
]

# ------------------ PERSONALITY ------------------
def random_reply(level):
    return random.choice({
        "warn": ["easy there 😅", "chill a bit", "not needed fr"],
        "enforce": ["that’s enough now", "you’re pushing it ngl"],
        "severe": ["nah… not happening", "yeah that crossed the line"]
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
                        "Context matters more than words.\n"
                        "SAFE = friendly/joking\n"
                        "LOW = mild negativity\n"
                        "MEDIUM = harassment or hate\n"
                        "HIGH = threats or violent intent\n"
                        "If targeting a group with harm → HIGH.\n"
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
async def jail_user(member, guild, channel, reason="No reason provided"):
    role = discord.utils.get(guild.roles, name="Jailed")
    mod_role = discord.utils.get(guild.roles, name="Moderator")

    reset_user_state(str(member.id))
    user_cooldowns[str(member.id)] = time.time() + COOLDOWN_TIME

    if role:
        try:
            await member.add_roles(role)
        except:
            pass

    if mod_role:
        await channel.send(f"{mod_role.mention} {member.mention} jailed.", delete_after=10)

    await log_action(
        guild,
        "🚨 User Jailed",
        f"User: {member.mention}\nReason: {reason}"
    )

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
    now = time.time()
    is_jail = message.channel.name in JAIL_CHANNELS
    in_cooldown = user_id in user_cooldowns and now < user_cooldowns[user_id]

    # ------------------ MENTION ------------------
    if client.user in message.mentions:
        await message.channel.send("yo 👋", delete_after=5)
        return

    # ------------------ RELEASE ------------------
    if content.startswith(PREFIX + "release"):
        if message.author.guild_permissions.administrator and message.mentions:
            user = message.mentions[0]
            role = discord.utils.get(message.guild.roles, name="Jailed")

            if role:
                await user.remove_roles(role)
                reset_user_state(str(user.id))

                await log_action(
                    message.guild,
                    "🔓 User Released",
                    f"User: {user.mention}\nBy: {message.author.mention}"
                )

                await message.delete(delay=5)
                await message.channel.send(
                    f"{user.mention} has been released.",
                    delete_after=5
                )
        return

    # ------------------ JAIL CHANNEL ------------------
    if is_jail:
        if len(content) > 250 or content.count("\n") > 5:
            await message.delete()
        return

    # ------------------ AI CHAT ------------------
    if content.startswith(PREFIX + "chat"):

        if message.channel.name != AI_CHANNEL_NAME:
            await message.channel.send(
                "AI chat is disabled here, head over to #ai-chat 🤖",
                delete_after=5
            )
            return

        role = discord.utils.get(message.guild.roles, name="AI Access")
        if role not in message.author.roles:
            return

        prompt = message.content[len(PREFIX + "chat"):].strip()

        res = await client_ai.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "Talk like a chill Gen Z human."},
                {"role": "user", "content": prompt}
            ]
        )

        reply = res.choices[0].message.content
        if random.random() < 0.2:
            reply += random.choice([" 😄", " ngl", " fr", " 👀"])

        await message.channel.send(reply[:2000])
        return

    # ------------------ HARD SENTINEL ------------------
    if any(bad in normalized for bad in NORMALIZED_BANNED):
        await message.delete()
        await cleanup_spam(message.channel, message.author, content)
        await jail_user(message.author, message.guild, message.channel, "Banned word detected")
        return

    # ------------------ AI INTENT ------------------
    should_analyze = False

    if len(content) > 80 or content.count("\n") >= 1:
        should_analyze = True

    if any(w in content for w in AI_TRIGGER_WORDS):
        should_analyze = True

    if should_analyze:
        result = await analyze_message(message.content)

        if result == "MEDIUM":
            await message.channel.send(random_reply("enforce"), delete_after=5)
            await cleanup_spam(message.channel, message.author, content)
            await jail_user(message.author, message.guild, message.channel, "AI detected harassment")
            return

        elif result == "HIGH":
            user_high_strikes[user_id] = user_high_strikes.get(user_id, 0) + 1
            user_high_timestamps[user_id] = now

            if user_high_strikes[user_id] == 1:
                await message.channel.send("yo chill… that's crossing a line ⚠️", delete_after=5)
                return

            if user_high_strikes[user_id] >= 2:
                if now - user_high_timestamps[user_id] <= HIGH_STRIKE_WINDOW:
                    await message.delete()
                    await cleanup_spam(message.channel, message.author, content)
                    await jail_user(message.author, message.guild, message.channel, "Repeated severe behavior")
                    user_high_strikes[user_id] = 0
                    return

    # ------------------ BURST SPAM ------------------
    user_message_times.setdefault(user_id, []).append(now)
    user_message_times[user_id] = [t for t in user_message_times[user_id] if now - t < 3]

    if len(user_message_times[user_id]) >= 7:
        await message.channel.send("bro relax 💀", delete_after=5)
        await cleanup_spam(message.channel, message.author, content)
        await jail_user(message.author, message.guild, message.channel, "Burst spam")
        return

    # ------------------ SIMILAR SPAM ------------------
    last = user_last_content.get(user_id)

    if last and is_similar(last, content):
        user_repeat_count[user_id] = user_repeat_count.get(user_id, 0) + 1
    else:
        user_last_content[user_id] = content
        user_repeat_count[user_id] = 1

    if user_repeat_count[user_id] >= 5:

        if in_cooldown:
            return

        user_offense_count[user_id] = user_offense_count.get(user_id, 0) + 1

        if user_offense_count[user_id] == 1:
            await message.channel.send("stop spamming bro", delete_after=5)

        elif user_offense_count[user_id] == 2:
            await message.channel.send("last warning fr", delete_after=5)

        else:
            await cleanup_spam(message.channel, message.author, content)
            await jail_user(message.author, message.guild, message.channel, "Repeated spam")

        reset_user_state(user_id)
        user_cooldowns[user_id] = time.time() + COOLDOWN_TIME
        return

client.run(os.getenv("TOKEN"))
