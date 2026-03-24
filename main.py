# (FULL FINAL — NOTHING REMOVED, ONLY ADDED)

import discord
import os
import time
import re
import datetime
import random
import asyncio
from difflib import SequenceMatcher
from openai import AsyncOpenAI

# ================= CONFIG =================
PREFIX = "="

JAIL_CHANNELS = ["jail-1", "jail-2"]
AI_CHANNEL_NAME = "ai-chat"
LOG_CHANNEL_NAME = "ai-logs"
GENERAL_CHANNEL_NAME = "chat"

WELCOME_CHANNEL = "👋│welcome"
RULES_CHANNEL = "📜│rules"
SYSTEM_CHANNEL = "🤖│how-plan-b-works"

# ✅ NEW
SANDBOX_CHANNEL = "🧪│test-plan-b"
SANDBOX_ROLE = "Sandbox"

SIMILARITY_THRESHOLD = 0.85

client_ai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)

# ================= MEMORY =================
user_message_times = {}
user_last_content = {}
user_repeat_count = {}

user_medium_strikes = {}
user_high_strikes = {}

user_jail_lock = {}

# ================= FILTER =================
BANNED = ["nigger","faggot","rape","pedophile","nazi","hitler","heil","childporn","kanker"]
TRIGGERS = ["idiot","retard","fuck you","bitch","nigga","kill","die","hate","stupid"]

# ================= PERSONALITY =================
def bot_reply(level):
    return random.choice({
        "warn": ["easy there 😅", "chill a bit", "not that serious", "watch it 👀"],
        "serious": ["that crossed the line", "not cool", "you’re pushing it"],
        "jail": ["yeah… take a break", "straight to jail 💀", "you earned that"]
    }[level])

# ================= EMBEDS =================
def get_welcome_embed():
    return discord.Embed(
        title="👋 Welcome to Plan B",
        description="Fair moderation. No bias. Be yourself.",
        color=0x5865F2
    )

def get_rules_embed():
    return discord.Embed(
        title="📜 Rules",
        description="Respect, no hate, no spam, follow ToS.",
        color=0xED4245
    )

def get_system_embed():
    return discord.Embed(
        title="🤖 System",
        description="AI watches patterns, not single messages.",
        color=0x57F287
    )

# ================= HELPERS =================
def normalize_text(text):
    text = text.lower()
    replacements = {"@":"a","4":"a","0":"o","1":"i","3":"e","$":"s","!":"i"}
    for k,v in replacements.items():
        text = text.replace(k,v)
    text = re.sub(r'[\W_]+','',text)
    text = re.sub(r'(.)\1+',r'\1',text)
    return text

NORMALIZED_BANNED = [normalize_text(w) for w in BANNED]

def is_similar(a,b):
    return SequenceMatcher(None,a,b).ratio() >= SIMILARITY_THRESHOLD

async def cleanup_spam(channel,user,ref,limit=30):
    def check(msg):
        return msg.author == user and is_similar(msg.content.lower(), ref.lower())
    try:
        await channel.purge(limit=limit, check=check)
    except:
        pass

async def log_action(guild,title,desc):
    ch = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)
    if ch:
        embed = discord.Embed(title=title, description=desc, color=discord.Color.red())
        embed.timestamp = discord.utils.utcnow()
        await ch.send(embed=embed)

# ================= AI =================
async def analyze(text):
    try:
        res = await client_ai.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role":"system","content":"SAFE, MEDIUM, HIGH"},
                {"role":"user","content":text}
            ]
        )
        return res.choices[0].message.content.strip()
    except:
        return "SAFE"

# ================= JAIL =================
async def jail_user(member, guild, reason):
    uid = str(member.id)
    now = time.time()

    if uid in user_jail_lock and now - user_jail_lock[uid] < 3:
        return
    user_jail_lock[uid] = now

    role = discord.utils.get(guild.roles, name="Jailed")

    if role:
        try:
            await member.add_roles(role)
        except:
            pass

    await log_action(guild, "🚨 User Jailed", f"{member.mention}\n{reason}")

# ================= SANDBOX CLEAN =================
async def sandbox_cleaner():
    await client.wait_until_ready()

    while not client.is_closed():
        try:
            for guild in client.guilds:
                channel = discord.utils.get(guild.text_channels, name=SANDBOX_CHANNEL)

                if not channel:
                    continue

                messages = []
                async for msg in channel.history(limit=50):
                    if not msg.pinned:
                        messages.append(msg)

                if messages:
                    await channel.send("🧪 Sandbox clearing in 2 minutes.")
                    await asyncio.sleep(120)
                    await channel.purge(limit=200, check=lambda m: not m.pinned)

        except Exception as e:
            print("Sandbox error:", e)

        await asyncio.sleep(1800)

# ================= FACT LOOP =================
async def send_hourly_fact():
    await client.wait_until_ready()

    while not client.is_closed():
        try:
            for guild in client.guilds:
                channel = discord.utils.get(guild.text_channels, name=GENERAL_CHANNEL_NAME)
                if channel:
                    res = await client_ai.chat.completions.create(
                        model="gpt-4.1-mini",
                        messages=[{"role":"system","content":"Give one short interesting fact."}]
                    )
                    await channel.send(f"🧠 {res.choices[0].message.content.strip()}")
        except:
            pass

        await asyncio.sleep(3600)

# ================= READY =================
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    client.loop.create_task(send_hourly_fact())
    client.loop.create_task(sandbox_cleaner())

# ================= MAIN =================
@client.event
async def on_message(message):

    if message.author == client.user:
        return

    # ✅ SANDBOX IGNORE
    if message.channel.name == SANDBOX_CHANNEL:
        return

    # 👀 PRESENCE
    if client.user in message.mentions:
        await message.channel.send("I’m active and watching 👀", delete_after=5)
        return

    content = message.content.lower()
    uid = str(message.author.id)
    normalized = normalize_text(content)
    now = time.time()

    # ===== SANDBOX ROLE =====
    if content == PREFIX + "sandbox":
        role = discord.utils.get(message.guild.roles, name=SANDBOX_ROLE)
        if role:
            await message.author.add_roles(role)
            await message.channel.send("🧪 Sandbox mode enabled", delete_after=5)
        return

    if content == PREFIX + "exit":
        role = discord.utils.get(message.guild.roles, name=SANDBOX_ROLE)
        if role:
            await message.author.remove_roles(role)
            await message.channel.send("Exited sandbox mode", delete_after=5)
        return

    # ===== SETUP =====
    if content == PREFIX + "setup":
        if not message.author.guild_permissions.administrator:
            return

        guild = message.guild

        welcome_ch = discord.utils.get(guild.text_channels, name=WELCOME_CHANNEL)
        rules_ch = discord.utils.get(guild.text_channels, name=RULES_CHANNEL)
        system_ch = discord.utils.get(guild.text_channels, name=SYSTEM_CHANNEL)

        if welcome_ch:
            await welcome_ch.send(embed=get_welcome_embed())
        if rules_ch:
            await rules_ch.send(embed=get_rules_embed())
        if system_ch:
            await system_ch.send(embed=get_system_embed())

        return

    # ===== AI CHAT =====
    if content.startswith(PREFIX + "chat"):

        if message.channel.name != AI_CHANNEL_NAME:
            await message.channel.send("Go to #ai-chat 🤖", delete_after=5)
            return

        role = discord.utils.get(message.guild.roles, name="AI Access")

        if role not in message.author.roles:
            await message.channel.send(
                "You don’t have access. DM @ap.snake 🔐",
                delete_after=5
            )
            return

        prompt = message.content[len(PREFIX + "chat"):].strip()

        res = await client_ai.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role":"system","content":"Talk like a chill Gen Z human."},
                {"role":"user","content":prompt}
            ]
        )

        await message.channel.send(res.choices[0].message.content[:2000])
        return

    # ===== HARD FILTER =====
    if any(b in normalized for b in NORMALIZED_BANNED):
        await message.delete()
        await cleanup_spam(message.channel, message.author, content)
        await message.channel.send(bot_reply("jail"), delete_after=5)
        await jail_user(message.author, message.guild, "Banned word")
        return

    # ===== BURST SPAM =====
    user_message_times.setdefault(uid, []).append(now)
    user_message_times[uid] = [t for t in user_message_times[uid] if now - t < 3]

    if len(user_message_times[uid]) >= 7:
        await message.author.timeout(datetime.timedelta(minutes=10))
        await cleanup_spam(message.channel, message.author, content)
        await jail_user(message.author, message.guild, "Raid spam")
        return

    # ===== AI MOD =====
    if len(content) > 20 or any(w in content for w in TRIGGERS):

        result = await analyze(message.content)

        if result == "MEDIUM":
            s = user_medium_strikes.get(uid, 0) + 1
            user_medium_strikes[uid] = s

            if s < 3:
                await message.channel.send(bot_reply("warn"), delete_after=5)
            else:
                await message.channel.send(bot_reply("jail"), delete_after=5)
                await jail_user(message.author, message.guild, "Harassment")
                user_medium_strikes[uid] = 0
            return

        if result == "HIGH":
            s = user_high_strikes.get(uid, 0) + 1
            user_high_strikes[uid] = s

            if s < 3:
                await message.channel.send(bot_reply("serious"), delete_after=5)
            else:
                await cleanup_spam(message.channel, message.author, content)
                await message.channel.send(bot_reply("jail"), delete_after=5)
                await jail_user(message.author, message.guild, "Severe behavior")
                user_high_strikes[uid] = 0
            return

    # ===== SIMILAR SPAM =====
    last = user_last_content.get(uid)

    if last and is_similar(last, content):
        user_repeat_count[uid] = user_repeat_count.get(uid, 0) + 1
    else:
        user_last_content[uid] = content
        user_repeat_count[uid] = 1

    if user_repeat_count[uid] >= 5:
        await cleanup_spam(message.channel, message.author, content)
        await message.channel.send(bot_reply("jail"), delete_after=5)
        await jail_user(message.author, message.guild, "Spam")
        return

client.run(os.getenv("TOKEN"))
