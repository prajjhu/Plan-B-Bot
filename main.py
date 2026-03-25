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
GENERAL_CHANNEL_NAME = "│main-lounge"
MODERATOR_ROLE_NAME = "Club Staff"

SIMILARITY_THRESHOLD = 0.85

# 🧠 REDUCED CONTEXT (LESS AGGRESSIVE)
CONTEXT_LIMIT = 3
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

def find_channel_partial(guild, target):
    target = target.lower().replace(" ", "").replace("│", "")
    for ch in guild.text_channels:
        name = ch.name.lower().replace(" ", "").replace("│", "")
        if name == target or target in name:
            return ch
    return None

async def post_setup_embeds(guild):
    welcome_channel = find_channel_partial(guild, "welcome")
    rules_channel = find_channel_partial(guild, "rules")
    works_channel = find_channel_partial(guild, "how-plan-b-works")

    welcome_embed = discord.Embed(
        title="🌙 Welcome to Plan B",
        description=(
            "The backup spot that turned out better.\n\n"
            "Plan B is where people land when the other server was too strict, too dead, or just not it. "
            "This place is built for real conversations, late-night vibes, and people who want room to breathe without the server turning into chaos."
        ),
        color=discord.Color.from_rgb(135, 70, 190)
    )
    welcome_embed.add_field(
        name="What this place is",
        value=(
            "A relaxed social server where you can talk freely, hang out properly, and actually enjoy the space. "
            "Banter is fine, personality is fine, and people are allowed to sound human."
        ),
        inline=False
    )
    welcome_embed.add_field(
        name="How moderation works",
        value=(
            "Moderation runs quietly in the background through AI-assisted checks. "
            "It looks at context, repetition, escalation, and intent instead of panicking over every small message.\n\n"
            "Admins and Club Staff still make the final call when something serious needs a human decision."
        ),
        inline=False
    )
    welcome_embed.add_field(
        name="What to do first",
        value=(
            "• Read the rules\n"
            "• Check how Plan B works\n"
            "• Pick your roles and colours\n"
            f"• Then head into {GENERAL_CHANNEL_NAME} and settle in"
        ),
        inline=False
    )
    welcome_embed.set_footer(text="Be yourself. Don’t ruin the room.")

    rules_embed = discord.Embed(
        title="📜 Plan B Rules",
        description="Simple. Fair. Consistent.",
        color=discord.Color.from_rgb(220, 80, 80)
    )
    rules_embed.add_field(
        name="1) Respect people",
        value="Disagree, joke, banter, argue — just do not turn it into targeted harassment or obsession.",
        inline=False
    )
    rules_embed.add_field(
        name="2) No hate or harmful intent",
        value="Slurs, hate speech, serious threats, or genuinely harmful behavior cross the line fast.",
        inline=False
    )
    rules_embed.add_field(
        name="3) No spam or disruption",
        value="Do not raid, flood, or repeatedly try to wreck the vibe for everyone else.",
        inline=False
    )
    rules_embed.add_field(
        name="4) No privacy violations",
        value="No doxxing, leaking private information, stalking behavior, or putting another user at risk.",
        inline=False
    )
    rules_embed.add_field(
        name="5) Do not abuse leniency",
        value="Just because the bot is calm does not mean you can keep pushing obvious bad behavior.",
        inline=False
    )
    rules_embed.add_field(
        name="6) Final calls",
        value="AI handles most moderation flow, but admins and Club Staff decide serious edge cases and final outcomes.",
        inline=False
    )
    rules_embed.set_footer(text="Talk freely. Act right when it matters.")

    works_embed = discord.Embed(
        title="🤖 How Plan B Works",
        description=(
            "Plan B uses AI-assisted moderation built to stay calm, understand context, and avoid overreacting."
        ),
        color=discord.Color.from_rgb(70, 170, 200)
    )
    works_embed.add_field(
        name="What AI allows",
        value="Casual swearing, friendly banter, normal disagreements, and people talking like actual humans.",
        inline=False
    )
    works_embed.add_field(
        name="What AI checks",
        value="Repetition, escalation, targeted harassment, harmful intent, spam behavior, and severe filtered words.",
        inline=False
    )
    works_embed.add_field(
        name="How actions escalate",
        value="Warning → escalation if it continues → jail if the user keeps pushing it or crosses the line badly enough.",
        inline=False
    )
    works_embed.add_field(
        name="Final decisions",
        value="The bot handles most moderation automatically, but admins and Club Staff step in when a human call is needed.",
        inline=False
    )
    works_embed.set_footer(text="AI watches the pattern. Humans decide the final call.")

    if welcome_channel:
        await welcome_channel.send(embed=welcome_embed)
    if rules_channel:
        await rules_channel.send(embed=rules_embed)
    if works_channel:
        await works_channel.send(embed=works_embed)

# ================= FILTER =================
BANNED = ["nigger","faggot","rape","pedophile","nazi","hitler","heil","childporn","kanker"]
NORMALIZED_BANNED = [normalize_text(w) for w in BANNED]

# ✅ UPDATED
TRIGGERS = ["idiot","retard","fuck you","bitch","kill","die","hate","stupid","kys","trash","worthless"]

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
                        "MEDIUM = repeated or targeted insults\n"
                        "HIGH = clear threats, hate speech, or serious harassment\n\n"

                        "IMPORTANT RULES:\n"
                        "- Do NOT punish casual swearing\n"
                        "- Do NOT punish friendly banter\n"
                        "- Do NOT overreact to single messages\n"
                        "- Only escalate if behavior is clearly repeated or harmful\n"
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

        except Exception as e:
            print("Fact error:", e)

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

    if client.user in message.mentions:
        await message.channel.send(random.choice([
            "yeah i’m watching 👀",
            "all systems running",
            "i see everything",
            "nothing escapes me",
            "you good?"
        ]), delete_after=5)
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

    # ===== SETUP =====
    if content.startswith(PREFIX + "setup"):
        if message.author.guild_permissions.administrator:
            await post_setup_embeds(message.guild)
            await message.channel.send("setup sent ✅", delete_after=5)
            try:
                await message.delete()
            except:
                pass
        return

    if message.channel.name in JAIL_CHANNELS:
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

        await message.channel.send(res.choices[0].message.content[:2000])
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

        use_context = any(w in content for w in TRIGGERS) or len(user_context[uid]) >= 2

        result = await analyze(uid, message.content, use_context)

        # ✅ MUTUAL DETECTION
        channel_id = str(message.channel.id)
        recent_toxic_users.setdefault(channel_id, [])
        recent_toxic_users[channel_id].append(uid)
        if len(recent_toxic_users[channel_id]) > 6:
            recent_toxic_users[channel_id].pop(0)

        unique_users = set(recent_toxic_users[channel_id])
        is_mutual = len(unique_users) >= 2

        # ===== MEDIUM =====
        if result == "MEDIUM":

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
