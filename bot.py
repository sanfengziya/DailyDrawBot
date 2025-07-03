# bot.py
import discord
from discord.ext import commands, tasks
import sqlite3
import random
import datetime
import pytz

TOKEN = "MTM5MDEzMjA5MzY2NDg4NjkxNQ.GFqro4.9xo_yJ9cJSsIskjuZJkwIC-5h93pICO_CAqzR0"  # 请替换成你自己的 bot token
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
conn.commit()
conn.close()

# 转换 UTC 到美东时间
def now_est():
    utc_now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
    est = pytz.timezone("US/Eastern")
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
            # 新日期，允许抽奖
            pass
    else:
        # 新用户
        c.execute("INSERT INTO users (user_id, points, last_draw) VALUES (?, ?, ?)", (user_id, 0, "1970-01-01"))
        conn.commit()

    earned = random.randint(10, 100)
    c.execute("UPDATE users SET points = points + ?, last_draw = ? WHERE user_id = ?", (earned, str(today), user_id))
    conn.commit()
    conn.close()

    await ctx.send(f"{ctx.author.mention} 你抽到了 **{earned}** 分！明天下午美东12点后可以再抽。")

@bot.command(name="check")
async def check(ctx):
    user_id = ctx.author.id
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()

    if row:
        await ctx.send(f"{ctx.author.mention} 你当前有 **{row[0]}** 分。")
    else:
        await ctx.send(f"{ctx.author.mention} 你还没有参与过抽奖~")

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


bot.run(TOKEN)
