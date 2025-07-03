# Daily Draw Bot

import discord
from discord.ext import commands
import sqlite3
import random
import datetime
import pytz
import os
from discord import File

TOKEN = "MTM5MDEzMjA5MzY2NDg4NjkxNQ.GIY9jP.vMxw86z4VK1Okug94Crx9Zx6WFvT00ip01RO6Y"
PREFIX = "!"
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# 初始化数据库
conn = sqlite3.connect("database.db")
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        points INTEGER DEFAULT 0,
        last_draw TEXT
    )
''')
c.execute('''
    CREATE TABLE IF NOT EXISTS tags (
        role_id INTEGER PRIMARY KEY,
        price INTEGER NOT NULL
    )
''')
conn.commit()
conn.close()

# 转换 UTC 到 UTC-4 时间
def now_est():
    utc_now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
    est = pytz.timezone("Etc/GMT+4")
    return utc_now.astimezone(est)

@bot.event
async def on_ready():
    print(f"已登录为 {bot.user}")

@bot.command(name="draw")
async def draw(ctx):
    user_id = ctx.author.id
    now = now_est()
    today = now.date()

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT points, last_draw FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()

    if row:
        last_draw_str = row[1]
        last_draw_date = datetime.datetime.strptime(last_draw_str, "%Y-%m-%d").date()
        if last_draw_date == today:
            await ctx.send(f"{ctx.author.mention} 你今天已经抽过奖啦，请明天再来。")
            conn.close()
            return
    else:
        c.execute("INSERT INTO users (user_id, points, last_draw) VALUES (?, ?, ?)", (user_id, 0, "1970-01-01"))
        conn.commit()

    earned = random.randint(10, 100)
    c.execute("UPDATE users SET points = points + ?, last_draw = ? WHERE user_id = ?", (earned, str(today), user_id))
    conn.commit()
    conn.close()

    await ctx.send(f"{ctx.author.mention} 你抽到了 **{earned}** 分！明天 UTC-4 凌晨 0 点后可以再抽。")

@bot.command(name="check")
async def check(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    user_id = member.id
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()

    if row:
        await ctx.send(f"{member.mention} 当前有 **{row[0]}** 分。")
    else:
        await ctx.send(f"{member.mention} 还没有参与过抽奖~")

@bot.command(name="resetdraw")
@commands.has_permissions(administrator=True)
async def reset_draw(ctx, member: discord.Member):
    user_id = member.id
    yesterday = (now_est().date() - datetime.timedelta(days=1)).isoformat()

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    if c.fetchone():
        c.execute("UPDATE users SET last_draw = ? WHERE user_id = ?", (yesterday, user_id))
        conn.commit()
        await ctx.send(f"{ctx.author.mention} 已成功重置 {member.mention} 的抽奖状态 ✅")
    else:
        await ctx.send(f"{ctx.author.mention} 该用户还没有抽奖记录，无法重置。")
    conn.close()

@bot.command(name="resetall")
@commands.has_permissions(administrator=True)
async def reset_all(ctx, confirm: str = None):
    if confirm != "--confirm":
        await ctx.send(
            f"{ctx.author.mention} ⚠️ 此操作将永久清空所有用户数据！\n"
            "如确定请使用：`!resetall --confirm`"
        )
        return

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("DELETE FROM users")
    conn.commit()
    conn.close()

    await ctx.send(f"{ctx.author.mention} ✅ 所有用户数据已被清除。")

@bot.command(name="backup")
@commands.has_permissions(administrator=True)
async def backup(ctx):
    await ctx.send(file=File("database.db"))

@bot.command(name="importdb")
@commands.has_permissions(administrator=True)
async def importdb(ctx):
    if not ctx.message.attachments:
        await ctx.send("请附加数据库文件（例如 database.db）")
        return

    attachment = ctx.message.attachments[0]
    await attachment.save("database.db")
    await ctx.send("✅ 数据库已导入。")

@bot.command(name="addtag")
@commands.has_permissions(administrator=True)
async def addtag(ctx, price: int, role: discord.Role):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO tags (role_id, price) VALUES (?, ?)", (role.id, price))
    conn.commit()
    conn.close()
    await ctx.send(f"已添加身份组 `{role.name}`，价格为 {price} 分。")

@bot.command(name="buy")
async def buy(ctx, *, role_name: str):
    guild = ctx.guild
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        await ctx.send("未找到该身份组。")
        return

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT price FROM tags WHERE role_id = ?", (role.id,))
    row = c.fetchone()
    if not row:
        await ctx.send("该身份组不可购买。")
        conn.close()
        return
    price = row[0]

    c.execute("SELECT points FROM users WHERE user_id = ?", (ctx.author.id,))
    user = c.fetchone()
    if not user or user[0] < price:
        await ctx.send("你的分数不足。")
        conn.close()
        return

    await ctx.send(f"你确定要购买 `{role.name}` 吗？请在 10 秒内回复 `确认`。")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        reply = await bot.wait_for("message", check=check, timeout=10.0)
        if reply.content != "确认":
            await ctx.send("已取消购买。")
            conn.close()
            return
    except:
        await ctx.send("超时，已取消购买。")
        conn.close()
        return

    c.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (price, ctx.author.id))
    conn.commit()
    conn.close()

    await ctx.author.add_roles(role)
    await ctx.send(f"✅ 你已购买并获得 `{role.name}` 身份组。")

@bot.command(name="give")
@commands.has_permissions(administrator=True)
async def give(ctx, member: discord.Member, amount: int):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("INSERT INTO users (user_id, points, last_draw) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET points = points + ?", (member.id, 0, "1970-01-01", amount))
    conn.commit()
    conn.close()
    await ctx.send(f"{ctx.author.mention} 已给予 {member.mention} {amount} 分。")

@bot.command(name="ranking")
async def ranking(ctx):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT user_id, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()

    msg = "🏆 前十排行榜：\n"
    for i, (user_id, points) in enumerate(rows, start=1):
        user = await bot.fetch_user(user_id)
        msg += f"{i}. {user.name}: {points} 分\n"
    await ctx.send(msg)

bot.run(TOKEN)