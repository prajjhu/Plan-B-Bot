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

SIMILARITY_THRESHOLD = 0.85
# ==========================================

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
        description=(
            "**This isn’t just another server.**\n\n"
            "Plan B is built around **fairness, not control.**\n"
            "No power-tripping mods. No random punishments.\n\n"
            "🧠 AI moderation runs quietly in the background\n"
            "⚖️ Human moderators handle edge cases\n\n"
            "Just be yourself — and don’t ruin the space for others."
        ),
        color=0x5865F2
    )

def get_rules_embed():
    return discord.Embed(
        title="📜 Plan B Rules",
        description=(
            "**Simple. Fair. Consistent.**\n\n"
            "1. Respect the space\n"
            "2. No hate or harmful intent\n"
            "3. No spam or disruption\n"
            "4. No privacy violations\n"
            "5. Follow Discord ToS\n\n"
            "**The system reacts to patterns — not single messages.**"
        ),
        color=0xED4245
    )

def get_system_embed():
    return discord.Embed(
        title="🤖 How Moderation Works",
        description=(
            "Plan B uses **AI-assisted moderation**.\n\n"
            "• Context-aware\n"
            "• Pattern-based\n"
            "• Less bias\n\n"
            "Warnings → Jail (if behavior continues)\n\n"
            "Humans still exist for final decisions."
        ),
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
                {
                    "role":"system",
                    "content":(
                        "You are a smart moderation AI.\n"
                        "Understand context and intent.\n\n"
                        "SAFE = normal or joking\n"
                        "MEDIUM = harassment/insults\n"
                        "HIGH = threats, hate, telling someone to die\n\n"
                        "Targeting groups = HIGH\n"
                        "Repeated toxicity increases severity\n\n"
                        "Respond ONLY: SAFE, MEDIUM, HIGH"
                    )
                },
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

# ================= MAIN =================
@client.event
async def on_message(message):

    if message.author == client.user:
        return

    # 👀 PRESENCE
    if client.user in message.mentions:
        await message.channel.send("I’m active and watching 👀", delete_after=5)
        return

    content = message.content.lower()
    uid = str(message.author.id)
    normalized = normalize_text(content)
    now = time.time()

    # ===== SETUP COMMAND =====
    if content == PREFIX + "setup":
        if message.author.guild_permissions.administrator:
            await message.channel.send(embed=get_welcome_embed())
            await message.channel.send(embed=get_rules_embed())
            await message.channel.send(embed=get_system_embed())
        return

    # ===== RELEASE =====
    if content.startswith(PREFIX + "release"):
        if message.author.guild_permissions.administrator and message.mentions:
            user = message.mentions[0]
            role = discord.utils.get(message.guild.roles, name="Jailed")
            if role:
                await user.remove_roles(role)

            await log_action(message.guild, "🔓 Released", f"{user.mention}")
            await message.channel.send(f"{user.mention} released", delete_after=5)
        return

    # ===== JAIL CHANNEL =====
    if message.channel.name in JAIL_CHANNELS:
        return

    # ===== AI CHAT =====
    if content.startswith(PREFIX + "chat"):

        if message.channel.name != AI_CHANNEL_NAME:
            await message.channel.send("Go to #ai-chat 🤖", delete_after=5)
            return

        role = discord.utils.get(message.guild.roles, name="AI Access")

        if role not in message.author.roles:
            await message.channel.send(
                "You don’t have access. DM @ap.snake for role 🔐",
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
