import discord
import os
import random
import time
import re
from openai import AsyncOpenAI

# ================= CONFIG =================
PREFIX = "="
JAIL_CHANNELS = ["jail-1", "jail-2"]
COOLDOWN_TIME = 5
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

# ------------------ RESET ------------------
def reset_user_state(user_id):
    user_last_content.pop(user_id, None)
    user_repeat_count.pop(user_id, None)
    user_message_times.pop(user_id, None)
    user_recent_messages.pop(user_id, None)

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
    replacements = {"@": "a", "4": "a", "0": "o", "1": "i", "$": "s"}
    for k, v in replacements.items():
        text = text.replace(k, v)
    text = re.sub(r'[\W_]+', '', text)
    text = re.sub(r'(.)\1+', r'\1', text)
    return text

# ------------------ PERSONALITY ------------------
def random_reply(level):
    return random.choice({
        "warn": ["easy there 😅", "chill a bit", "not needed fr"],
        "enforce": ["that’s enough now", "you’re pushing it ngl"],
        "severe": ["nah… not happening", "yeah that crossed the line"]
    }[level])

# ------------------ AI MODERATION ------------------
async def analyze_message(text):
    try:
        res = await client_ai.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a lenient moderation AI.\n"
                        "SAFE = friendly/joking\n"
                        "LOW = mild negativity\n"
                        "MEDIUM = harassment\n"
                        "HIGH = threats\n"
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

    reset_user_state(str(member.id))
    user_offense_count[str(member.id)] = 0
    user_cooldowns[str(member.id)] = time.time() + COOLDOWN_TIME

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
    now = time.time()
    is_jail = message.channel.name in JAIL_CHANNELS

    # ------------------ COOLDOWN ------------------
    in_cooldown = user_id in user_cooldowns and now < user_cooldowns[user_id]

    # ------------------ MENTION ------------------
    if client.user in message.mentions:
        await message.channel.send("yo 👋", delete_after=5)
        return

    # ==================================================
# 🔓 GLOBAL RELEASE COMMAND (WORKS EVERYWHERE)
# ==================================================
if content.startswith(PREFIX + "release"):

    if not message.author.guild_permissions.administrator:
        return

    if message.mentions:
        user = message.mentions[0]
        role = discord.utils.get(message.guild.roles, name="Jailed")

        if role:
            try:
                await user.remove_roles(role)

                # 🔥 RESET USER STATE
                reset_user_state(str(user.id))
                user_offense_count[str(user.id)] = 0

                # delete command after 5 sec
                await message.delete(delay=5)

                await message.channel.send(
                    f"{user.mention} has been released.",
                    delete_after=5
                )

            except Exception as e:
                print(f"Release error: {e}")
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
                    reset_user_state(str(user.id))
                    user_offense_count[str(user.id)] = 0

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

        res = await client_ai.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "Talk like a chill Gen Z human."},
                {"role": "user", "content": prompt}
            ]
        )

        await message.channel.send(res.choices[0].message.content[:2000])
        return

    # ==================================================
    # 🔴 SENTINEL
    # ==================================================
    if any(w in content or w in normalized for w in INSTANT_JAIL_WORDS):
        await message.delete()
        await cleanup_messages(message.channel, message.author)
        await jail_user(message.author, message.guild, message.channel)
        return

    # ==================================================
    # 🧠 AI CONTEXT
    # ==================================================
    if any(p in content for p in SEVERE_PHRASES):
        result = await analyze_message(message.content)

        if result in ["MEDIUM", "HIGH"]:
            await message.channel.send(random_reply("severe"), delete_after=5)
            await cleanup_messages(message.channel, message.author)
            await jail_user(message.author, message.guild, message.channel)
            return

    # ==================================================
    # 🧩 SPAM SYSTEM (FIXED)
    # ==================================================
    user_last_content.setdefault(user_id, content)
    user_repeat_count[user_id] = user_repeat_count.get(user_id, 0)

    if user_last_content[user_id] == content:
        user_repeat_count[user_id] += 1
    else:
        user_last_content[user_id] = content
        user_repeat_count[user_id] = 1

    if user_repeat_count[user_id] >= 5:

        # 🔥 FIX: cooldown now IGNORES instead of punishes
        if in_cooldown:
            return

        user_offense_count[user_id] = user_offense_count.get(user_id, 0) + 1

        if user_offense_count[user_id] == 1:
            await message.channel.send("stop spamming bro", delete_after=5)

        elif user_offense_count[user_id] == 2:
            await message.channel.send("last warning fr", delete_after=5)

        else:
            await message.channel.send(
                "you’ve been spamming repeatedly, take a break.",
                delete_after=5
            )
            await cleanup_messages(message.channel, message.author)
            await jail_user(message.author, message.guild, message.channel)
            user_offense_count[user_id] = 0

        reset_user_state(user_id)
        user_cooldowns[user_id] = time.time() + COOLDOWN_TIME
        return

    # ==================================================
    # ⚡ FLOOD
    # ==================================================
    user_message_times.setdefault(user_id, []).append(now)
    user_message_times[user_id] = [t for t in user_message_times[user_id] if now - t < 5]

    if len(user_message_times[user_id]) >= 6:
        await message.channel.send("slow down fr", delete_after=5)
        await cleanup_messages(message.channel, message.author)
        await jail_user(message.author, message.guild, message.channel)
        return

    # ==================================================
    # 📈 ESCALATION
    # ==================================================
    user_recent_messages.setdefault(user_id, []).append(content)
    user_recent_messages[user_id] = user_recent_messages[user_id][-5:]

    combined = " ".join(user_recent_messages[user_id])

    if any(w in combined for w in ["idiot", "retard", "fuck you"]):
        if len(user_recent_messages[user_id]) >= 5:
            await message.channel.send(random_reply("enforce"), delete_after=5)
            await cleanup_messages(message.channel, message.author)
            await jail_user(message.author, message.guild, message.channel)
            return

client.run(os.getenv("TOKEN"))
