import discord
from discord.ext import commands, tasks
import json
import os
import asyncio
import aiohttp
import datetime
from PIL import Image, ImageDraw, ImageFont
import io
import requests
import re
from flask import Flask
from threading import Thread

# ─────────────────────────────────────────────
#  KEEP-ALIVE — Wajib untuk Render Web Service
# ─────────────────────────────────────────────
app = Flask("")

@app.route("/")
def home():
    return "✅ Asisten Lurah BFL sedang online!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# ─────────────────────────────────────────────
#  KONFIGURASI — Dibaca dari Environment Variables
# ─────────────────────────────────────────────
TOKEN                   = os.environ["TOKEN"]
OWNER_ID                = int(os.environ["OWNER_ID"])
SPAM_CHANNEL_ID         = int(os.environ["SPAM_CHANNEL_ID"])
TIKTOK_USERNAME         = os.environ["TIKTOK_USERNAME"]
TIKTOK_CHECK_CHANNEL_ID = int(os.environ["TIKTOK_CHECK_CHANNEL_ID"])

DATA_FILE        = "data.json"
LAST_TIKTOK_FILE = "last_tiktok.json"

# ─────────────────────────────────────────────
#  LEVEL CONFIG
# ─────────────────────────────────────────────
LEVEL_CONFIG = {
    1: {"name": "Bot",          "xp_required": 0,    "color": (108, 117, 125)},
    2: {"name": "Side Brother", "xp_required": 100,  "color": (23, 162, 184)},
    3: {"name": "Member",       "xp_required": 300,  "color": (40, 167, 69)},
    4: {"name": "Brother",      "xp_required": 700,  "color": (255, 193, 7)},
    5: {"name": "Big Brother",  "xp_required": 1500, "color": (220, 53, 69)},
}
XP_PER_MESSAGE = 10

# ─────────────────────────────────────────────
#  BOT INIT
# ─────────────────────────────────────────────
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ─────────────────────────────────────────────
#  DATA HELPERS
# ─────────────────────────────────────────────
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_last_tiktok():
    if not os.path.exists(LAST_TIKTOK_FILE):
        return {}
    with open(LAST_TIKTOK_FILE, "r") as f:
        return json.load(f)

def save_last_tiktok(data):
    with open(LAST_TIKTOK_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_level(xp):
    current_level = 1
    for lvl in sorted(LEVEL_CONFIG.keys(), reverse=True):
        if xp >= LEVEL_CONFIG[lvl]["xp_required"]:
            current_level = lvl
            break
    return current_level

def get_xp_for_next_level(level):
    next_level = level + 1
    if next_level > max(LEVEL_CONFIG.keys()):
        return None
    return LEVEL_CONFIG[next_level]["xp_required"]

# ─────────────────────────────────────────────
#  RANK CARD
# ─────────────────────────────────────────────
def create_rank_card(username, avatar_bytes, xp, level):
    W, H = 700, 200
    card = Image.new("RGBA", (W, H), (30, 30, 46))
    draw = ImageDraw.Draw(card)
    level_color = LEVEL_CONFIG[level]["color"]

    for i in range(W):
        alpha = int(80 * (i / W))
        draw.line([(i, 0), (i, H)], fill=(*level_color, alpha))

    try:
        avatar_img = Image.open(io.BytesIO(avatar_bytes)).resize((130, 130)).convert("RGBA")
        mask = Image.new("L", (130, 130), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 130, 130), fill=255)
        avatar_img.putalpha(mask)
        card.paste(avatar_img, (30, 35), avatar_img)
    except Exception:
        draw.ellipse([30, 35, 160, 165], fill=(60, 60, 80))

    draw.ellipse([28, 33, 162, 167], outline=level_color, width=3)

    try:
        font_big   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        font_med   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    except Exception:
        font_big = font_med = font_small = ImageFont.load_default()

    draw.text((190, 30), username, fill=(255, 255, 255), font=font_big)
    draw.text((190, 70), f"Level {level}  ·  {LEVEL_CONFIG[level]['name']}", fill=level_color, font=font_med)

    next_xp = get_xp_for_next_level(level)
    if next_xp:
        xp_text  = f"XP: {xp} / {next_xp}"
        progress = min(xp / next_xp, 1.0)
    else:
        xp_text  = f"XP: {xp}  (MAX LEVEL)"
        progress = 1.0

    draw.text((190, 105), xp_text, fill=(200, 200, 220), font=font_small)

    bar_x, bar_y, bar_w, bar_h = 190, 135, 450, 20
    draw.rounded_rectangle([bar_x, bar_y, bar_x+bar_w, bar_y+bar_h], radius=10, fill=(50, 50, 70))
    fill_w = int(bar_w * progress)
    if fill_w > 0:
        draw.rounded_rectangle([bar_x, bar_y, bar_x+fill_w, bar_y+bar_h], radius=10, fill=level_color)

    label = f"{int(progress*100)}% menuju level berikutnya" if next_xp else "🏆 Level Tertinggi!"
    draw.text((bar_x, bar_y+bar_h+5), label, fill=(160, 160, 180), font=font_small)
    draw.text((W-170, H-22), "Asisten Lurah BFL", fill=(80, 80, 100), font=font_small)

    buf = io.BytesIO()
    card.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ─────────────────────────────────────────────
#  EVENTS
# ─────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ {bot.user} online sebagai Asisten Lurah BFL!")
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="Desa BFL 🏘️")
    )
    check_tiktok.start()

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    data = load_data()
    uid  = str(message.author.id)
    if uid not in data:
        data[uid] = {"xp": 0, "level": 1}
    old_level          = data[uid]["level"]
    data[uid]["xp"]   += XP_PER_MESSAGE
    new_level          = get_level(data[uid]["xp"])
    data[uid]["level"] = new_level
    save_data(data)
    if new_level > old_level:
        embed = discord.Embed(
            title="🎉 LEVEL UP!",
            description=f"{message.author.mention} naik ke **Level {new_level} — {LEVEL_CONFIG[new_level]['name']}**!",
            color=discord.Color.from_rgb(*LEVEL_CONFIG[new_level]["color"])
        )
        await message.channel.send(embed=embed)
    await bot.process_commands(message)

# ─────────────────────────────────────────────
#  COMMANDS
# ─────────────────────────────────────────────
@bot.command(name="rank")
async def rank(ctx, member: discord.Member = None):
    if ctx.channel.id != SPAM_CHANNEL_ID:
        await ctx.send(f"⚠️ Command ini hanya bisa digunakan di <#{SPAM_CHANNEL_ID}>!", delete_after=5)
        return
    member = member or ctx.author
    data   = load_data()
    uid    = str(member.id)
    if uid not in data:
        data[uid] = {"xp": 0, "level": 1}
        save_data(data)
    xp    = data[uid]["xp"]
    level = data[uid]["level"]
    try:
        avatar_bytes = requests.get(member.display_avatar.url).content
    except Exception:
        avatar_bytes = b""
    card_buf = create_rank_card(str(member.display_name), avatar_bytes, xp, level)
    await ctx.send(file=discord.File(fp=card_buf, filename="rank.png"))

@bot.command(name="leaderboard", aliases=["lb", "top"])
async def leaderboard(ctx):
    if ctx.channel.id != SPAM_CHANNEL_ID:
        await ctx.send(f"⚠️ Command ini hanya bisa digunakan di <#{SPAM_CHANNEL_ID}>!", delete_after=5)
        return
    data         = load_data()
    sorted_users = sorted(data.items(), key=lambda x: x[1]["xp"], reverse=True)[:10]
    medals       = ["🥇", "🥈", "🥉"]
    embed = discord.Embed(title="🏆 Leaderboard XP — Asisten Lurah BFL", color=discord.Color.gold())
    for i, (uid, info) in enumerate(sorted_users):
        try:
            user = await bot.fetch_user(int(uid))
            name = user.display_name
        except Exception:
            name = f"User#{uid}"
        lvl   = info["level"]
        medal = medals[i] if i < 3 else f"#{i+1}"
        embed.add_field(
            name=f"{medal} {name}",
            value=f"Level {lvl} ({LEVEL_CONFIG[lvl]['name']}) · {info['xp']} XP",
            inline=False
        )
    await ctx.send(embed=embed)

@bot.command(name="pengumuman")
async def pengumuman(ctx, channel: discord.TextChannel, *, pesan: str):
    if not isinstance(ctx.channel, discord.DMChannel):
        return
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ Kamu tidak punya izin untuk menggunakan perintah ini.")
        return
    embed = discord.Embed(
        title="📢 PENGUMUMAN",
        description=pesan,
        color=discord.Color.blue(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text="Asisten Lurah BFL")
    await channel.send("@everyone", embed=embed)
    await ctx.send(f"✅ Pengumuman berhasil dikirim ke #{channel.name}!")

@bot.command(name="timeout")
@commands.has_permissions(moderate_members=True)
async def timeout_member(ctx, member: discord.Member, durasi: int, *, alasan="Tidak ada alasan"):
    until = discord.utils.utcnow() + datetime.timedelta(minutes=durasi)
    await member.timeout(until, reason=alasan)
    embed = discord.Embed(title="⏱️ Member di-Timeout", color=discord.Color.orange())
    embed.add_field(name="Member", value=member.mention, inline=True)
    embed.add_field(name="Durasi", value=f"{durasi} menit", inline=True)
    embed.add_field(name="Alasan", value=alasan, inline=False)
    embed.set_footer(text=f"Oleh: {ctx.author}")
    await ctx.send(embed=embed)

@timeout_member.error
async def timeout_error(ctx, error):
    await ctx.send(f"❌ Error: {error}")

@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban_member(ctx, member: discord.Member, *, alasan="Tidak ada alasan"):
    await member.ban(reason=alasan)
    embed = discord.Embed(title="🔨 Member di-Ban", color=discord.Color.red())
    embed.add_field(name="Member", value=f"{member} ({member.id})", inline=False)
    embed.add_field(name="Alasan", value=alasan, inline=False)
    embed.set_footer(text=f"Oleh: {ctx.author}")
    await ctx.send(embed=embed)

@ban_member.error
async def ban_error(ctx, error):
    await ctx.send(f"❌ Error: {error}")

@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban_member(ctx, user_id: int):
    user = await bot.fetch_user(user_id)
    await ctx.guild.unban(user)
    await ctx.send(f"✅ **{user}** berhasil di-unban.")

@bot.command(name="addrole")
@commands.has_permissions(manage_roles=True)
async def add_role(ctx, member: discord.Member, *, role_name: str):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role:
        await ctx.send(f"❌ Role **{role_name}** tidak ditemukan.")
        return
    await member.add_roles(role)
    await ctx.send(f"✅ Role **{role_name}** berhasil diberikan ke {member.mention}.")

@bot.command(name="removerole")
@commands.has_permissions(manage_roles=True)
async def remove_role(ctx, member: discord.Member, *, role_name: str):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role:
        await ctx.send(f"❌ Role **{role_name}** tidak ditemukan.")
        return
    await member.remove_roles(role)
    await ctx.send(f"✅ Role **{role_name}** berhasil dihapus dari {member.mention}.")

@bot.command(name="clear", aliases=["purge", "hapus"])
@commands.has_permissions(manage_messages=True)
async def clear_messages(ctx, jumlah: int = 10):
    await ctx.channel.purge(limit=jumlah + 1)
    await ctx.send(f"✅ **{jumlah}** pesan berhasil dihapus.", delete_after=5)

@clear_messages.error
async def clear_error(ctx, error):
    await ctx.send(f"❌ Error: {error}")

@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(title="📖 Asisten Lurah BFL — Daftar Command", color=discord.Color.blue())
    embed.add_field(name="🏅 Level (Hanya di spam channel)",
                    value="`!rank [@user]`\n`!leaderboard`", inline=False)
    embed.add_field(name="🔇 Moderasi",
                    value="`!timeout @user <menit> [alasan]`\n`!ban @user [alasan]`\n`!unban <id>`\n`!clear [jumlah]`",
                    inline=False)
    embed.add_field(name="🎭 Role",
                    value="`!addrole @user <nama_role>`\n`!removerole @user <nama_role>`", inline=False)
    embed.add_field(name="📢 Pengumuman (Owner — via DM bot)",
                    value="`!pengumuman #channel <pesan>`", inline=False)
    embed.set_footer(text="Asisten Lurah BFL • Desa BFL")
    await ctx.send(embed=embed)

# ─────────────────────────────────────────────
#  TIKTOK TRACKER
# ─────────────────────────────────────────────
@tasks.loop(minutes=5)
async def check_tiktok():
    channel = bot.get_channel(TIKTOK_CHECK_CHANNEL_ID)
    if not channel:
        return
    try:
        last_data = load_last_tiktok()
        url       = f"https://www.tiktok.com/@{TIKTOK_USERNAME}"
        headers   = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                html = await resp.text()
        matches = re.findall(r'"id":"(\d+)"', html)
        if not matches:
            return
        latest_id = matches[0]
        if last_data.get("last_id") == latest_id:
            return
        save_last_tiktok({"last_id": latest_id})
        tiktok_url = f"https://www.tiktok.com/@{TIKTOK_USERNAME}/video/{latest_id}"
        embed = discord.Embed(
            title=f"🎵 @{TIKTOK_USERNAME} baru saja posting di TikTok!",
            description=f"Lihat video terbaru sekarang 👇\n{tiktok_url}",
            color=discord.Color.from_rgb(254, 44, 85),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Asisten Lurah BFL • TikTok Tracker")
        await channel.send(embed=embed)
    except Exception as e:
        print(f"[TikTok Check Error] {e}")

@check_tiktok.before_loop
async def before_check():
    await bot.wait_until_ready()

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
keep_alive()
bot.run(TOKEN)
