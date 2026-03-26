import discord
import os
import time
import re
import datetime
import random
from difflib import SequenceMatcher
from openai import AsyncOpenAI

# ================= CONFIG =================
PREFIX = "="
JAIL_CHANNELS = ["jail-1", "jail-2"]
AI_CHANNEL_NAME = "ai-chat"
LOG_CHANNEL_NAME = "ai-logs"
GENERAL_CHANNEL_NAME = "│main-lounge"
MODERATOR_ROLE_NAME = "Club Staff"
ALLOWED_INVITE_CHANNELS = ["│link", "│partner-p4p"]

SIMILARITY_THRESHOLD = 0.85

# 🧠 REDUCED CONTEXT (LESS AGGRESSIVE)
CONTEXT_LIMIT = 1
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

user_context = {}

# ✅ NEW
user_last_seen = {}
recent_toxic_users = {}
moderation_enabled = True
standby_bot_messages = []
invite_ad_warnings = []

# ================= PERSONALITY =================
def bot_reply(level):
    return random.choice({
        "warn": ["easy there 😅", "chill a bit bro", "not that serious", "watch it 👀"],
        "serious": ["yeah that crossed the line", "nah we don’t do that here", "alright that’s enough", "you’re pushing it now"],
        "jail": ["yeah… you earned that one", "straight to jail 💀", "nah take a break", "you did that to yourself fr"]
    }[level])

# ✅ NEW
def warn_user(member, level):
    if level == "medium":
        return f"⚠️ {member.mention} chill a bit"
    if level == "high":
        return f"🚨 {member.mention} that’s too far"

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

def contains_discord_invite(text):
    return re.search(r'(?:https?://)?(?:www\.)?(?:discord\.gg|discord(?:app)?\.com/invite)/[A-Za-z0-9-]+', text, re.IGNORECASE) is not None

def is_invite_allowed_channel(channel):
    return channel.name in ALLOWED_INVITE_CHANNELS

async def cleanup_spam(channel,user,ref,limit=30):
    def check(msg):
        return msg.author == user and is_similar(msg.content.lower(), ref.lower())
    try:
        await channel.purge(limit=limit, check=check)
    except:
        pass

async def cleanup_recent_spam(channel, user, limit=30):
    recent = []
    try:
        async for msg in channel.history(limit=limit):
            if msg.author == user:
                recent.append(msg)
    except:
        return

    recent.reverse()

    spam_msgs = []
    last_text = None
    streak = 0

    for msg in recent:
        text = msg.content.strip().lower()

        if not text:
            continue

        if last_text and is_similar(last_text, text):
            streak += 1
        else:
            streak = 1

        if streak >= 2:
            spam_msgs.append(msg)

        last_text = text

    for msg in spam_msgs:
        try:
            await msg.delete()
        except:
            pass

async def log_action(guild,title,desc):
    ch = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)
    if ch:
        embed = discord.Embed(title=title, description=desc, color=discord.Color.red())
        embed.timestamp = discord.utils.utcnow()
        await ch.send(embed=embed)

async def notify_mods_jail(channel, guild, member, reason):
    role = discord.utils.get(guild.roles, name=MODERATOR_ROLE_NAME)
    if not role:
        print(f"MOD ALERT ERROR: role '{MODERATOR_ROLE_NAME}' not found")
        return

    try:
        await channel.send(
            f"{role.mention} {member.mention} has been jailed, due to: {reason}",
            allowed_mentions=discord.AllowedMentions(roles=True, users=True),
            delete_after=10
        )
    except Exception as e:
        print("MOD ALERT ERROR:", e)

async def build_bouncer_context(channel, limit=8):
    msgs = []
    try:
        async for msg in channel.history(limit=limit):
            if msg.author.bot and msg.author != client.user:
                continue
            author = "Bouncer" if msg.author == client.user else msg.author.display_name
            msgs.append(f"{author}: {msg.content}")
    except:
        return ""
    msgs.reverse()
    return "\n".join(msgs)

async def bouncer_ai_reply(message):
    try:
        chat_context = await build_bouncer_context(message.channel)
        res = await client_ai.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role":"system",
                    "content":(
                        "You are Bouncer, the chill late-night club bouncer of a Discord server called Plan B. "
                        "Moderation is currently paused, so you are only here to reply like a smart, socially aware human. "
                        "Be concise, natural, witty when it fits, and reply based on the current chat context. "
                        "Do not act like an assistant giving essays unless asked."
                    )
                },
                {
                    "role":"user",
                    "content":f"Recent chat:\n{chat_context}\n\nReply to this message naturally:\n{message.author.display_name}: {message.content}"
                }
            ]
        )
        sent = await message.reply(res.choices[0].message.content[:2000], mention_author=False)
        standby_bot_messages.append(sent)
    except Exception as e:
        print("BOUNCER REPLY ERROR:", e)

async def clear_standby_messages():
    global standby_bot_messages
    for msg in standby_bot_messages:
        try:
            await msg.delete()
        except:
            pass
    standby_bot_messages = []

# ================= FILTER =================
BANNED = ["nigger","faggot","rape","pedophile","nazi","hitler","heil","childporn","kanker"]
NORMALIZED_BANNED = [normalize_text(w) for w in BANNED]

# ✅ UPDATED
TRIGGERS = ["kill","die","hate","stupid","kys","trash","worthless"]

# ================= AI =================
async def analyze(uid, text, use_context=True):
    try:
        context_text = ""

        if use_context:
            history = user_context.get(uid, [])
            context_text = "\n".join(history[:-1])

        prompt = f"""
Previous messages:
{context_text}

Current message:
{text}
"""

        res = await client_ai.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role":"system",
                    "content":(
                        "You are a moderation AI for a chill social Discord server.\n\n"

                        "SAFE = casual language, jokes, slang, swearing\n"
                        "MEDIUM = repeated or targeted insults which should be following a pattern\n"
                        "HIGH = clear threats, hate speech, or serious harassment\n\n"

                        "IMPORTANT RULES:\n"
                        "- Do NOT punish casual swearing\n"
                        "- Do NOT punish friendly banter\n"
                        "- Do NOT overreact to single messages\n"
                        "- Only escalate if behavior is clearly repeated or harmful multiple times\n"
                        "- Only return HIGH if it is serious and intentional\n\n"

                        "Return ONLY: SAFE, MEDIUM, HIGH"
                    )
                },
                {"role":"user","content":prompt}
            ]
        )
        return res.choices[0].message.content.strip()
    except:
        return "SAFE"

# ================= JAIL =================
# ================= JAIL =================
async def jail_user(member, guild, reason, source_channel=None):
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

    # existing log (UNCHANGED)
    await log_action(guild, "🚨 User Jailed", f"{member.mention}\n{reason}")

    if source_channel:
        await notify_mods_jail(source_channel, guild, member, reason)

    # ✅ UPDATED: find jail channel (handles emoji names)
    jail_channel = None
    for ch in guild.text_channels:
        if any(name in ch.name for name in JAIL_CHANNELS):
            jail_channel = ch
            break

    # ✅ UPDATED: send temp message (non-blocking + debug)
    if jail_channel:
        try:
            await jail_channel.send(
                f"🚨 {member.mention} was jailed\nReason: {reason}",
                delete_after=60
            )
        except Exception as e:
            print("JAIL MESSAGE ERROR:", e)

# ================= READY =================
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

# ================= MAIN =================
@client.event
async def on_message(message):
    global moderation_enabled

    if message.author == client.user:
        return

    uid = str(message.author.id)
    content = message.content.lower()
    normalized = normalize_text(content)
    now = time.time()

    # ✅ DECAY SYSTEM
    last = user_last_seen.get(uid, now)
    if now - last > 10:
        user_medium_strikes[uid] = max(0, user_medium_strikes.get(uid, 0) - 1)
        user_high_strikes[uid] = max(0, user_high_strikes.get(uid, 0) - 1)
    user_last_seen[uid] = now

    # 🧠 STORE CONTEXT
    user_context.setdefault(uid, []).append(message.content)
    if len(user_context[uid]) > CONTEXT_LIMIT:
        user_context[uid].pop(0)

    # ===== RELEASE =====
    if content.startswith(PREFIX + "release"):
        if message.author.guild_permissions.administrator and message.mentions:
            user = message.mentions[0]
            role = discord.utils.get(message.guild.roles, name="Jailed")

            if role:
                await user.remove_roles(role)

            user_medium_strikes.pop(str(user.id), None)
            user_high_strikes.pop(str(user.id), None)

            await log_action(message.guild, "🔓 Released", f"{user.mention}")
            await message.channel.send(f"{user.mention} released", delete_after=5)

            try:
                await message.delete()
            except:
                pass
        return

    # ===== STANDBY =====
    if content.startswith(PREFIX + "standby"):
        if message.author.guild_permissions.administrator:
            moderation_enabled = False
            await message.channel.send("moderation standby enabled 💤", delete_after=5)
            try:
                await message.delete()
            except:
                pass
        return

    # ===== RESUME =====
    if content.startswith(PREFIX + "resume"):
        if message.author.guild_permissions.administrator:
            moderation_enabled = True
            await clear_standby_messages()
            await message.channel.send("moderation resumed ✅", delete_after=5)
            try:
                await message.delete()
            except:
                pass
        return

    # ===== DISCORD INVITE FILTER =====
    if contains_discord_invite(message.content):
        if not message.author.guild_permissions.administrator and not is_invite_allowed_channel(message.channel):
            await message.delete()

            if uid not in invite_ad_warnings:
                invite_ad_warnings.append(uid)
                await message.channel.send(
                    f"{message.author.mention}, Do not Advertise your server in these chat, Visit Partnerships, repeated offense will result in Jail-time",
                    delete_after=8
                )
            else:
                await message.channel.send(
                    f"{message.author.mention} warned already.",
                    delete_after=5
                )
                await message.channel.send(bot_reply("jail"), delete_after=5)
                await jail_user(message.author, message.guild, "Discord invite advertising", message.channel)
                invite_ad_warnings.remove(uid)
            return

    if message.channel.name in JAIL_CHANNELS:
        return

    if not moderation_enabled:
        if "bouncer" in content:
            await bouncer_ai_reply(message)
            return

        if client.user in message.mentions:
            return

    if moderation_enabled and client.user in message.mentions:
        await message.channel.send(random.choice([
            "yeah i’m watching 👀",
            "all systems running",
            "i see everything",
            "nothing escapes me",
            "you good?"
        ]), delete_after=5)
        return

     # ===== AI CHAT =====
    if content.startswith(PREFIX + "chat"):

        # ✅ FIX: handle emoji/prefix in channel name
        if AI_CHANNEL_NAME not in message.channel.name:
            await message.channel.send("Go to #ai-chat 🤖", delete_after=5)
            return

        role = discord.utils.get(message.guild.roles, name="AI Access")

        if role not in message.author.roles:
            await message.channel.send(
                "you don’t have access to AI chat, dm @ap.snake 🔐",
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

        sent = await message.channel.send(res.choices[0].message.content[:2000])
        if not moderation_enabled:
            standby_bot_messages.append(sent)
        return

    if not moderation_enabled:
        return

    # ===== HARD FILTER =====
    if any(b in normalized for b in NORMALIZED_BANNED):
        await message.delete()
        await cleanup_spam(message.channel, message.author, content)
        await message.channel.send(bot_reply("jail"), delete_after=5)
        await jail_user(message.author, message.guild, "Banned word", message.channel)
        return

    # ===== BURST SPAM =====
    user_message_times.setdefault(uid, []).append(now)
    user_message_times[uid] = [t for t in user_message_times[uid] if now - t < 3]

    if len(user_message_times[uid]) >= 7:
        await cleanup_recent_spam(message.channel, message.author)
        await message.channel.send("bro relax 💀", delete_after=5)
        await jail_user(message.author, message.guild, "Raid spam", message.channel)
        return

    # ===== AI MOD =====
    if len(content) > 5:

        use_context = any(w in content for w in TRIGGERS)

        result = await analyze(uid, message.content, use_context)
        channel_id = str(message.channel.id)

        if result == "SAFE":
            user_medium_strikes[uid] = max(0, user_medium_strikes.get(uid, 0) - 1)
            user_high_strikes[uid] = max(0, user_high_strikes.get(uid, 0) - 1)
            return

        # ===== MEDIUM =====
        if result == "MEDIUM":
            recent_toxic_users.setdefault(channel_id, [])
            recent_toxic_users[channel_id].append(uid)
            if len(recent_toxic_users[channel_id]) > 6:
                recent_toxic_users[channel_id].pop(0)

            unique_users = set(recent_toxic_users[channel_id])
            is_mutual = len(unique_users) >= 2

            if is_mutual:
                await message.channel.send(
                    f"⚠️ {message.author.mention} keep it chill (mutual)",
                    delete_after=5
                )
                return

            s = user_medium_strikes.get(uid, 0) + 1
            user_medium_strikes[uid] = s

            if s <= 2:
                await message.channel.send(
                    warn_user(message.author, "medium"),
                    delete_after=5
                )
            else:
                await message.channel.send(bot_reply("jail"), delete_after=5)
                await jail_user(message.author, message.guild, "Harassment", message.channel)
                user_medium_strikes[uid] = 0

            return


        # ===== HIGH =====
        if result == "HIGH":
            recent_toxic_users.setdefault(channel_id, [])
            recent_toxic_users[channel_id].append(uid)
            if len(recent_toxic_users[channel_id]) > 6:
                recent_toxic_users[channel_id].pop(0)

            unique_users = set(recent_toxic_users[channel_id])
            is_mutual = len(unique_users) >= 2

            if is_mutual:
                await message.channel.send(
                    f"🚨 {message.author.mention} chill, don’t escalate",
                    delete_after=5
                )

                s = user_high_strikes.get(uid, 0) + 1
                user_high_strikes[uid] = s

                if s < 3:
                    return

            s = user_high_strikes.get(uid, 0) + 1
            user_high_strikes[uid] = s

            if s == 1:
                await message.channel.send(
                    warn_user(message.author, "high"),
                    delete_after=5
                )
            else:
                await message.channel.send(bot_reply("jail"), delete_after=5)
                await jail_user(message.author, message.guild, "Severe behavior", message.channel)
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
        await cleanup_recent_spam(message.channel, message.author)
        await message.channel.send(bot_reply("jail"), delete_after=5)
        await jail_user(message.author, message.guild, "Spam", message.channel)
        return

client.run(os.getenv("TOKEN"))
