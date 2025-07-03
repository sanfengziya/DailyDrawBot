# bot.py
import discord
from discord.ext import commands, tasks
import sqlite3
import random
import datetime
import pytz
import shutil
import os

TOKEN = "MTM5MDEzMjA5MzY2NDg4NjkxNQ.GFqro4.9xo_yJ9cJSsIskjuZJkwIC-5h93pICO_CAqzR0"  # 请替换成你自己的 bot token
PREFIX = "!"
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# 可购买身份组信息（数据库管理）
def load_tags():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS tags (role_id INTEGER PRIMARY KEY, price INTEGER)")
    c.execute("SELECT role_id, price FROM tags")
    rows = c.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

BUYABLE_TAGS = load_tags()

# 数据库备份
def backup_db(source_file="database.db", backup_folder="backups"):
    os.makedirs(backup_folder, exist_ok=True)
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    backup_path = os.path.join(backup_folder, f"backup_{now}.db")
    shutil.copy(source_file, backup_path)
    return backup_path

# 数据库导入
def import_db_from_file(attachment_path):
    if not os.path.exists(attachment_path):
        return False
    shutil.copy(attachment_path, "database.db")
    return True

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
        price INTEGER
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
    global BUYABLE_TAGS
    BUYABLE_TAGS = load_tags()
    print(f"已登录为 {bot.user}")
    daily_reminder.start()

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

    await ctx.send(f"{ctx.author.mention} 你抽到了 **{earned}** 分！明天下午美东12点后可以再抽。")

@bot.command(name="check")
async def check(ctx, member: discord.Member = None):
    target = member or ctx.author
    user_id = target.id
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()

    if row:
        await ctx.send(f"{target.mention} 当前有 **{row[0]}** 分。")
    else:
        await ctx.send(f"{target.mention} 还没有参与过抽奖~")

@bot.command(name="ranking")
async def ranking(ctx):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT user_id, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()

    if not rows:
        await ctx.send("暂无积分记录。")
        return

    msg = "**🏆 积分排行榜：**\n"
    for i, (user_id, points) in enumerate(rows, 1):
        user = await bot.fetch_user(user_id)
        msg += f"{i}. {user.name}: {points} 分\n"
    await ctx.send(msg)

@tasks.loop(time=datetime.time(hour=12, tzinfo=pytz.timezone("US/Eastern")))
async def daily_reminder():
    for guild in bot.guilds:
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                await channel.send("🎯 每日抽奖时间到啦！输入 `!draw` 抽取今天的积分吧！")
                break

# ... 其余代码保持不变 ...

bot.run(TOKEN)
