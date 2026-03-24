import discord
import os
import random
import time
import re
import datetime
import asyncio
from difflib import SequenceMatcher
from openai import AsyncOpenAI

# ================= CONFIG =================
PREFIX = "="
JAIL_CHANNELS = ["jail-1", "jail-2"]
AI_CHANNEL_NAME = "ai-chat"
LOG_CHANNEL_NAME = "ai-logs"

COOLDOWN_TIME = 5
SIMILARITY_THRESHOLD = 0.85
# ==========================================

client_ai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)

# ------------------ MEMORY ------------------
user_message_times = {}
user_last_content = {}
user_repeat_count = {}

user_medium_strikes = {}
user_high_strikes = {}

user_jail_lock = {}

# ------------------ NORMALIZE ------------------
def normalize_text(text):
    text = text.lower()

    replacements = {
        "@":"a","4":"a","0":"o",
        "1":"i","3":"e","$":"s","!":"i"
    }

    for k,v in replacements.items():
        text = text.replace(k,v)

    text = re.sub(r'[\W_]+','',text)
    text = re.sub(r'(.)\1+',r'\1',text)

    return text

# ------------------ SIMILARITY ------------------
def is_similar(a,b):
    return SequenceMatcher(None,a,b).ratio() >= SIMILARITY_THRESHOLD

# ------------------ CLEANUP ------------------
async def cleanup_spam(channel,user,ref,limit=30):
    def check(msg):
        return msg.author == user and is_similar(msg.content.lower(),ref.lower())
    try:
        await channel.purge(limit=limit, check=check)
    except:
        pass

# ------------------ LOG ------------------
async def log_action(guild,title,desc):
    ch = discord.utils.get(guild.text_channels,name=LOG_CHANNEL_NAME)
    if ch:
        embed = discord.Embed(title=title,description=desc,color=discord.Color.red())
        embed.timestamp = discord.utils.utcnow()
        await ch.send(embed=embed)

# ------------------ SENTINEL ------------------
BANNED = [
    "nigger","faggot","rape","pedophile",
    "nazi","hitler","heil","childporn","kanker"
]

NORMALIZED_BANNED = [normalize_text(w) for w in BANNED]

TRIGGERS = [
    "idiot","retard","fuck you","bitch",
    "nigga","kill","die","hate","stupid"
]

# ------------------ AI ------------------
async def analyze(text):
    try:
        r = await client_ai.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role":"system",
                    "content":(
                        "Classify message strictly:\n"
                        "SAFE = friendly\n"
                        "MEDIUM = harassment\n"
                        "HIGH = threats / hate / harmful intent\n"
                        "Return only SAFE, MEDIUM, HIGH"
                    )
                },
                {"role":"user","content":text}
            ]
        )
        return r.choices[0].message.content.strip()
    except:
        return "SAFE"

# ------------------ JAIL ------------------
async def jail_user(member,guild,channel,reason):
    uid = str(member.id)
    now = time.time()

    # prevent duplicate jail spam
    if uid in user_jail_lock and now - user_jail_lock[uid] < 3:
        return
    user_jail_lock[uid] = now

    role = discord.utils.get(guild.roles,name="Jailed")

    # timeout first (clean UX)
    try:
        await member.timeout(datetime.timedelta(minutes=10))
    except:
        pass

    await asyncio.sleep(1)

    # then jail
    if role:
        try:
            await member.add_roles(role)
        except:
            pass

    await log_action(guild,"🚨 User Jailed",f"{member.mention}\nReason: {reason}")

# ------------------ READY ------------------
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

# ------------------ MAIN ------------------
@client.event
async def on_message(message):

    if message.author == client.user:
        return

    uid = str(message.author.id)
    content = message.content.lower()
    normalized = normalize_text(content)
    now = time.time()

    # ------------------ AI CHAT ------------------
    if content.startswith(PREFIX+"chat"):

        if message.channel.name != AI_CHANNEL_NAME:
            await message.channel.send(
                "AI chat is disabled in here, head over to #ai-chat 🤖",
                delete_after=5
            )
            return

        role = discord.utils.get(message.guild.roles,name="AI Access")
        if role not in message.author.roles:
            return

        prompt = message.content[len(PREFIX+"chat"):].strip()

        res = await client_ai.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role":"system","content":"Talk like a chill Gen Z human."},
                {"role":"user","content":prompt}
            ]
        )

        reply = res.choices[0].message.content

        if random.random() < 0.2:
            reply += random.choice([" 😄"," ngl"," fr"," 👀"])

        await message.channel.send(reply[:2000])
        return

    # ------------------ HARD SLUR ------------------
    if any(b in normalized for b in NORMALIZED_BANNED):
        await message.delete()
        await cleanup_spam(message.channel,message.author,content)
        await jail_user(message.author,message.guild,message.channel,"Banned word")
        return

    # ------------------ BURST SPAM ------------------
    user_message_times.setdefault(uid,[]).append(now)
    user_message_times[uid] = [t for t in user_message_times[uid] if now-t < 3]

    if len(user_message_times[uid]) >= 7:
        await cleanup_spam(message.channel,message.author,content)
        await jail_user(message.author,message.guild,message.channel,"Burst spam")
        return

    # ------------------ AI MODERATION ------------------
    should_check = False

    if len(content) > 80:
        should_check = True

    if any(w in content for w in TRIGGERS):
        should_check = True

    if should_check:
        result = await analyze(message.content)

        # 🟡 MEDIUM
        if result == "MEDIUM":
            s = user_medium_strikes.get(uid,0) + 1
            user_medium_strikes[uid] = s

            if s == 1:
                await message.channel.send("⚠️ warning 1",delete_after=5)
                return

            elif s == 2:
                await message.channel.send("⚠️ warning 2",delete_after=5)
                return

            else:
                await message.channel.send("muted for 10 mins",delete_after=5)
                try:
                    await message.author.timeout(datetime.timedelta(minutes=10))
                except:
                    pass
                user_medium_strikes[uid] = 0
                return

        # 🔴 HIGH
        if result == "HIGH":
            s = user_high_strikes.get(uid,0) + 1
            user_high_strikes[uid] = s

            if s == 1:
                await message.channel.send("⚠️ serious warning 1",delete_after=5)
                return

            elif s == 2:
                await message.channel.send("⚠️ serious warning 2",delete_after=5)
                return

            else:
                await cleanup_spam(message.channel,message.author,content)
                await jail_user(message.author,message.guild,message.channel,"Severe behavior")
                user_high_strikes[uid] = 0
                return

    # ------------------ SIMILAR SPAM ------------------
    last = user_last_content.get(uid)

    if last and is_similar(last,content):
        user_repeat_count[uid] = user_repeat_count.get(uid,0) + 1
    else:
        user_last_content[uid] = content
        user_repeat_count[uid] = 1

    if user_repeat_count[uid] >= 5:
        await cleanup_spam(message.channel,message.author,content)
        await jail_user(message.author,message.guild,message.channel,"Repeated spam")
        return

client.run(os.getenv("TOKEN"))
