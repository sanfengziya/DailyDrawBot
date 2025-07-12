# Daily Draw Bot

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import mysql.connector
from urllib.parse import urlparse
import random
import datetime
import pytz
import os
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from discord import File

TOKEN = os.getenv("TOKEN")
if TOKEN is None:
    raise RuntimeError("TOKEN environment variable not set")
YOUR_GUILD_ID = 1389456172897009775
PREFIX = "!"
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)
WHEEL_COST = 100
MAX_PAID_DRAWS_PER_DAY = 10

MYSQL_URL = os.getenv("MYSQL_URL")
if MYSQL_URL is None:
    raise RuntimeError("MYSQL_URL environment variable not set")
url = urlparse(MYSQL_URL)
DB_CONFIG = {
    "host": url.hostname,
    "port": url.port,
    "user": url.username,
    "password": url.password,
    "database": url.path[1:],
}

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)

# 初始化数据库，如果表不存在就创建
def init_db() -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            points INT DEFAULT 0,
            last_draw DATE,
            last_wheel DATE DEFAULT '1970-01-01',
            paid_draws_today INT DEFAULT 0,
            last_paid_draw_date DATE DEFAULT '1970-01-01'
        )
        """
    )
    c.execute("SHOW COLUMNS FROM users LIKE 'last_wheel'")
    if not c.fetchone():
        c.execute(
            "ALTER TABLE users ADD COLUMN last_wheel DATE DEFAULT '1970-01-01'"
        )
    
    c.execute("SHOW COLUMNS FROM users LIKE 'paid_draws_today'")
    if not c.fetchone():
        c.execute(
            "ALTER TABLE users ADD COLUMN paid_draws_today INT DEFAULT 0"
        )
    
    c.execute("SHOW COLUMNS FROM users LIKE 'last_paid_draw_date'")
    if not c.fetchone():
        c.execute(
            "ALTER TABLE users ADD COLUMN last_paid_draw_date DATE DEFAULT '1970-01-01'"
        )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS tags (
            role_id BIGINT PRIMARY KEY,
            price INT NOT NULL
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS quiz_questions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            category VARCHAR(255) NOT NULL,
            question TEXT NOT NULL,
            option1 TEXT NOT NULL,
            option2 TEXT NOT NULL,
            option3 TEXT NOT NULL,
            option4 TEXT NOT NULL,
            answer TINYINT NOT NULL
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS wheel_rewards (
            id INT AUTO_INCREMENT PRIMARY KEY,
            points INT NOT NULL,
            description VARCHAR(255) NOT NULL
        )
        """
    )
    conn.commit()
    c.close()
    conn.close()

# 优化的抽奖奖励系统
REWARD_SYSTEM = [
    {"points": 10, "probability": 22.0, "message": "小小心意", "emoji": "🍬"},
    {"points": 20, "probability": 17.0, "message": "普通奖励", "emoji": "🎁"},
    {"points": 75, "probability": 13.0, "message": "不错哦", "emoji": "🎯"},
    {"points": 100, "probability": 12.0, "message": "运气不错", "emoji": "🎪"},
    {"points": 125, "probability": 5.0, "message": "有点开心", "emoji": "🎨"},
    {"points": 175, "probability": 4.5, "message": "较稀有", "emoji": "🌟"},
    {"points": 200, "probability": 4.0, "message": "稀有奖励", "emoji": "💫"},
    {"points": 250, "probability": 3.5, "message": "传说级运气", "emoji": "👑"},
    {"points": 300, "probability": 2.5, "message": "极低概率大奖", "emoji": "🔥"},
    {"points": 500, "probability": 2.0, "message": "超级大奖", "emoji": "💎"},
    {"points": 666, "probability": 1.5, "message": "恶魔奖励", "emoji": "😈"},
    {"points": 777, "probability": 0.9, "message": "幸运之神奖", "emoji": "✨"},
    {"points": 1000, "probability": 0.1, "message": "终极大奖", "emoji": "🏆"},
]

def get_weighted_reward():
    """Get a random reward based on weighted probabilities"""
    # Create a list where each reward appears according to its probability
    reward_pool = []
    for reward in REWARD_SYSTEM:
        # Convert percentage to number of entries (multiply by 10 for precision)
        count = int(reward["probability"] * 10)
        for _ in range(count):
            reward_pool.append(reward)
    
    # Randomly select from the pool
    return random.choice(reward_pool)

init_db()

# View for paginated role shop display
class RolePageView(discord.ui.View):
    def __init__(self, ctx, rows):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.rows = rows
        self.index = 0
        self.message = None

    async def send_initial(self):
        embed = self.get_embed(self.index)
        self.message = await self.ctx.send(embed=embed, view=self)

    def get_embed(self, index: int) -> discord.Embed:
        role_id, price = self.rows[index]
        role = self.ctx.guild.get_role(role_id)
        name = role.name if role else f"（未知角色）ID:{role_id}"
        color = role.color if role and role.color.value != 0 else discord.Color.default()

        embed = discord.Embed(
            title=name,
            description=f"价格：{price} 分\n\n第 {index + 1} / {len(self.rows)} 个",
            color=color
        )
        return embed

    @discord.ui.button(label="◀️ 上一页", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("你无法控制这个分页！", ephemeral=True)
        self.index = (self.index - 1) % len(self.rows)
        await interaction.response.edit_message(embed=self.get_embed(self.index), view=self)

    @discord.ui.button(label="▶️ 下一页", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("你无法控制这个分页！", ephemeral=True)
        self.index = (self.index + 1) % len(self.rows)
        await interaction.response.edit_message(embed=self.get_embed(self.index), view=self)

# 转换 UTC 到 UTC-4 时间
def now_est():
    utc_now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
    est = pytz.timezone("Etc/GMT+4")
    return utc_now.astimezone(est)

@bot.event
async def on_ready():
    print(f"已登录为 {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"同步了 {len(synced)} 个斜杠命令")
    except Exception as e:
        print(f"同步斜杠命令时出错: {e}")

@bot.event
async def on_guild_join(guild):
    if guild.id != YOUR_GUILD_ID:
        await guild.leave()

@bot.command(name="draw")
async def draw(ctx):
    user_id = ctx.author.id
    now = now_est()
    today = now.date()

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT points, last_draw, paid_draws_today, last_paid_draw_date FROM users WHERE user_id = %s", (user_id,))
    row = c.fetchone()

    if row:
        points, last_draw_date, paid_draws_today, last_paid_draw_date = row
        if isinstance(last_draw_date, str):
            last_draw_date = datetime.datetime.strptime(last_draw_date, "%Y-%m-%d").date()
        elif isinstance(last_draw_date, datetime.datetime):
            last_draw_date = last_draw_date.date()
        
        if isinstance(last_paid_draw_date, str):
            last_paid_draw_date = datetime.datetime.strptime(last_paid_draw_date, "%Y-%m-%d").date()
        elif isinstance(last_paid_draw_date, datetime.datetime):
            last_paid_draw_date = last_paid_draw_date.date()
        else:
            last_paid_draw_date = datetime.date(1970, 1, 1)
        
        # Debug: Print the values to console
        print(f"DEBUG: User {user_id} - paid_draws_today: {paid_draws_today}, last_paid_draw_date: {last_paid_draw_date}, today: {today}")
    else:
        c.execute("INSERT INTO users (user_id, points, last_draw, paid_draws_today, last_paid_draw_date) VALUES (%s, %s, %s, %s, %s)", 
                 (user_id, 0, "1970-01-01", 0, "1970-01-01"))
        conn.commit()
        points, last_draw_date, paid_draws_today, last_paid_draw_date = 0, datetime.date(1970, 1, 1), 0, datetime.date(1970, 1, 1)
        print(f"DEBUG: New user {user_id} created with paid_draws_today: {paid_draws_today}")

    first_draw = last_draw_date != today
    
    # Reset paid draws counter if it's a new day
    if last_paid_draw_date != today:
        print(f"DEBUG: Resetting paid_draws_today from {paid_draws_today} to 0 (new day)")
        paid_draws_today = 0

    if first_draw:
        # First draw of the day - free!
        await ctx.send(f"🎉 {ctx.author.mention} 开始今天的抽奖吧！")
    else:
        # Check if user has reached daily paid draw limit
        if paid_draws_today >= MAX_PAID_DRAWS_PER_DAY:
            conn.close()
            embed = discord.Embed(
                title="❌ 今日付费抽奖次数已达上限",
                description=f"你今日已付费抽奖 **{paid_draws_today}** 次\n每日最多可付费抽奖 **{MAX_PAID_DRAWS_PER_DAY}** 次\n\n明天再来吧！",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        if points < WHEEL_COST:
            conn.close()
            embed = discord.Embed(
                title="❌ 积分不足",
                description=f"你需要 {WHEEL_COST} 积分才能再次抽奖\n当前积分: {points}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        remaining_draws = MAX_PAID_DRAWS_PER_DAY - paid_draws_today
        embed = discord.Embed(
            title="🎰 额外抽奖",
            description=f"本次抽奖将消耗 **{WHEEL_COST}** 积分\n当前积分: **{points}**\n今日已付费抽奖: **{paid_draws_today}** 次\n剩余付费抽奖次数: **{remaining_draws}** 次\n\n发送 `Y` 确认抽奖",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

        def check(m: discord.Message) -> bool:
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await bot.wait_for("message", check=check, timeout=15)
        except asyncio.TimeoutError:
            conn.close()
            await ctx.send("⏰ 已取消抽奖。")
            return

        if msg.content.lower() not in ("y", "yes"):
            conn.close()
            await ctx.send("❌ 已取消抽奖。")
            return

        c.execute("UPDATE users SET points = points - %s WHERE user_id = %s", (WHEEL_COST, user_id))

    reward = get_weighted_reward()
    
    if first_draw:
        # Free draw - only update points and last_draw
        c.execute(
            "UPDATE users SET points = points + %s, last_draw = %s WHERE user_id = %s",
            (reward["points"], str(today), user_id),
        )
    else:
        # Paid draw - update points, last_draw, paid_draws_today, and last_paid_draw_date
        new_paid_draws = paid_draws_today + 1
        print(f"DEBUG: Updating paid_draws_today from {paid_draws_today} to {new_paid_draws}")
        c.execute(
            "UPDATE users SET points = points + %s, last_draw = %s, paid_draws_today = %s, last_paid_draw_date = %s WHERE user_id = %s",
            (reward["points"], str(today), new_paid_draws, str(today), user_id),
        )
    conn.commit()
    conn.close()

    # Create a beautiful embed for the reward
    embed = discord.Embed(
        title=f"{reward['emoji']} 抽奖结果",
        description=f"**{reward['message']}**\n获得 **{reward['points']}** 分！",
        color=discord.Color.gold() if reward['points'] >= 300 else discord.Color.blue() if reward['points'] >= 100 else discord.Color.green()
    )
    
    # Add special effects for high-value rewards
    if reward['points'] >= 1000:
        embed.description += "\n\n🏆 **恭喜你抽中了终极大奖！** 🏆"
        embed.color = discord.Color.purple()
    elif reward['points'] >= 777:
        embed.description += "\n\n🎉 **恭喜你抽中了幸运之神奖！** 🎉"
        embed.color = discord.Color.purple()
    elif reward['points'] >= 666:
        embed.description += "\n\n😈 **哇！你抽中了恶魔奖励！** 😈"
        embed.color = discord.Color.dark_red()
    elif reward['points'] >= 500:
        embed.description += "\n\n🔥 **太棒了！你抽中了超级大奖！** 🔥"
        embed.color = discord.Color.orange()
    elif reward['points'] >= 250:
        embed.description += "\n\n⭐ **哇！你抽中了稀有奖励！** ⭐"
        embed.color = discord.Color.gold()
    
    await ctx.send(embed=embed)

@bot.command(name="check")
async def check(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    user_id = member.id
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT points, last_draw, paid_draws_today, last_paid_draw_date FROM users WHERE user_id = %s", (user_id,))
    row = c.fetchone()
    conn.close()

    if row:
        points, last_draw, paid_draws_today, last_paid_draw_date = row
        embed = discord.Embed(
            title=f"💰 {member.display_name} 的积分信息",
            color=discord.Color.blue()
        )
        embed.add_field(name="当前积分", value=f"**{points}** 分", inline=True)
        
        if last_draw and last_draw != "1970-01-01":
            if isinstance(last_draw, str):
                last_draw_date = datetime.datetime.strptime(last_draw, "%Y-%m-%d").date()
            else:
                last_draw_date = last_draw.date() if hasattr(last_draw, 'date') else last_draw
            
            today = now_est().date()
            if last_draw_date == today:
                embed.add_field(name="今日抽奖", value="✅ 已完成", inline=True)
            else:
                embed.add_field(name="今日抽奖", value="❌ 未完成", inline=True)
        else:
            embed.add_field(name="今日抽奖", value="❌ 未完成", inline=True)
        
        # Check if paid draws should be reset for today
        if isinstance(last_paid_draw_date, str):
            last_paid_draw_date_obj = datetime.datetime.strptime(last_paid_draw_date, "%Y-%m-%d").date()
        elif isinstance(last_paid_draw_date, datetime.datetime):
            last_paid_draw_date_obj = last_paid_draw_date.date()
        else:
            last_paid_draw_date_obj = datetime.date(1970, 1, 1)
        
        today = now_est().date()
        if last_paid_draw_date_obj != today:
            paid_draws_today = 0
        
        remaining_draws = MAX_PAID_DRAWS_PER_DAY - paid_draws_today
        embed.add_field(name="付费抽奖", value=f"**{paid_draws_today}/{MAX_PAID_DRAWS_PER_DAY}** 次\n剩余: **{remaining_draws}** 次", inline=True)
        
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ 用户信息",
            description=f"{member.mention} 还没有参与过抽奖~",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

@bot.command(name="resetdraw")
@commands.has_permissions(administrator=True)
async def reset_draw(ctx, member: discord.Member):
    user_id = member.id
    yesterday = (now_est().date() - datetime.timedelta(days=1)).isoformat()

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    if c.fetchone():
        c.execute("UPDATE users SET last_draw = %s WHERE user_id = %s", (yesterday, user_id))
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

    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM users")
    conn.commit()
    conn.close()

    await ctx.send(f"{ctx.author.mention} ✅ 所有用户数据已被清除。")

@bot.command(name="fixdb")
@commands.has_permissions(administrator=True)
async def fix_database(ctx):
    """Force update database schema for paid draws tracking"""
    conn = get_connection()
    c = conn.cursor()
    
    # Check and add missing columns
    c.execute("SHOW COLUMNS FROM users LIKE 'paid_draws_today'")
    if not c.fetchone():
        c.execute("ALTER TABLE users ADD COLUMN paid_draws_today INT DEFAULT 0")
        print("Added paid_draws_today column")
    
    c.execute("SHOW COLUMNS FROM users LIKE 'last_paid_draw_date'")
    if not c.fetchone():
        c.execute("ALTER TABLE users ADD COLUMN last_paid_draw_date DATE DEFAULT '1970-01-01'")
        print("Added last_paid_draw_date column")
    
    # Update existing users to have proper default values
    c.execute("UPDATE users SET paid_draws_today = 0 WHERE paid_draws_today IS NULL")
    c.execute("UPDATE users SET last_paid_draw_date = '1970-01-01' WHERE last_paid_draw_date IS NULL")
    
    conn.commit()
    conn.close()
    
    await ctx.send(f"{ctx.author.mention} ✅ 数据库结构已修复，付费抽奖追踪功能已启用。")

@bot.command(name="backup")
@commands.has_permissions(administrator=True)
async def backup(ctx):
    await ctx.send("备份功能仅适用于 SQLite 数据库。")

@bot.command(name="importdb")
@commands.has_permissions(administrator=True)
async def importdb(ctx):
    if not ctx.message.attachments:
        await ctx.send("该功能仅适用于 SQLite 数据库。")
        return

@bot.command(name="addtag")
@commands.has_permissions(administrator=True)
async def addtag(ctx, price: int, role: discord.Role):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO tags (role_id, price) VALUES (%s, %s) "
        "ON DUPLICATE KEY UPDATE price = VALUES(price)",
        (role.id, price),
    )
    conn.commit()
    conn.close()
    await ctx.send(f"已添加身份组 `{role.name}`，价格为 {price} 分。")

@bot.command(name="roleshop")
async def roleshop(ctx):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT role_id, price FROM tags ORDER BY price")
    rows = c.fetchall()
    conn.close()

    if not rows:
        await ctx.send("当前没有可购买的身份组。")
        return

    view = RolePageView(ctx, rows)
    await view.send_initial()


@bot.command(name="buy")
async def buy(ctx, *, role_name: str):
    guild = ctx.guild
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        await ctx.send("未找到该身份组。")
        return

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT price FROM tags WHERE role_id = %s", (role.id,))
    row = c.fetchone()
    if not row:
        await ctx.send("该身份组不可购买。")
        conn.close()
        return
    price = row[0]

    c.execute("SELECT points FROM users WHERE user_id = %s", (ctx.author.id,))
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

    c.execute("UPDATE users SET points = points - %s WHERE user_id = %s", (price, ctx.author.id))
    conn.commit()
    conn.close()

    await ctx.author.add_roles(role)
    await ctx.send(f"✅ 你已购买并获得 `{role.name}` 身份组。")

@bot.command(name="givepoints")
@commands.has_permissions(administrator=True)
async def givepoints(ctx, member: discord.Member, amount: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO users (user_id, points, last_draw) VALUES (%s, %s, %s) "
        "ON DUPLICATE KEY UPDATE points = points + %s",
        (member.id, 0, "1970-01-01", amount),
    )
    conn.commit()
    conn.close()
    await ctx.send(f"{ctx.author.mention} 已给予 {member.mention} {amount} 分。")


@bot.command(name="setpoints")
@commands.has_permissions(administrator=True)
async def setpoints(ctx, member: discord.Member, points: int):
    """Set a member's points exactly to the specified value."""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO users (user_id, points, last_draw) VALUES (%s, %s, %s) "
        "ON DUPLICATE KEY UPDATE points = VALUES(points)",
        (member.id, points, "1970-01-01"),
    )
    conn.commit()
    conn.close()
    await ctx.send(f"{ctx.author.mention} 已将 {member.mention} 的分数设为 {points} 分。")


@bot.command(name="rewardinfo")
@commands.has_permissions(administrator=True)
async def rewardinfo(ctx):
    """Display current reward system information"""
    embed = discord.Embed(
        title="🎰 抽奖奖励系统",
        description="当前抽奖概率分布：",
        color=discord.Color.blue()
    )
    
    total_prob = sum(reward["probability"] for reward in REWARD_SYSTEM)
    
    for reward in REWARD_SYSTEM:
        embed.add_field(
            name=f"{reward['emoji']} {reward['points']}分 - {reward['message']}",
            value=f"概率: {reward['probability']}%",
            inline=True
        )
    
    embed.add_field(
        name="📊 统计信息",
        value=f"总概率: {total_prob}%\n奖励种类: {len(REWARD_SYSTEM)}种\n平均奖励: {sum(r['points'] * r['probability'] / 100 for r in REWARD_SYSTEM):.1f}分",
        inline=False
    )
    
    await ctx.send(embed=embed)


@bot.command(name="testdraw")
@commands.has_permissions(administrator=True)
async def testdraw(ctx, times: int = 100):
    """Test the reward system with multiple draws"""
    if times > 1000:
        await ctx.send("测试次数不能超过1000次！")
        return
    
    results = {}
    total_points = 0
    
    for _ in range(times):
        reward = get_weighted_reward()
        points = reward["points"]
        results[points] = results.get(points, 0) + 1
        total_points += points
    
    embed = discord.Embed(
        title=f"🎲 抽奖测试结果 ({times}次)",
        description=f"总获得积分: {total_points}\n平均每次: {total_points/times:.1f}分",
        color=discord.Color.green()
    )
    
    for points in sorted(results.keys()):
        count = results[points]
        percentage = (count / times) * 100
        embed.add_field(
            name=f"{points}分",
            value=f"出现{count}次 ({percentage:.1f}%)",
            inline=True
        )
    
    await ctx.send(embed=embed)


@bot.command(name="quizlist")
async def quizlist(ctx):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT DISTINCT category FROM quiz_questions")
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    if rows:
        await ctx.send("📋 题库类别：" + ", ".join(rows))
    else:
        await ctx.send("暂无题库。")


@bot.command(name="importquiz")
@commands.has_permissions(administrator=True)
async def importquiz(ctx):
    if not ctx.message.attachments:
        await ctx.send("请附加题库文件。")
        return

    attachment = ctx.message.attachments[0]
    data = await attachment.read()
    lines = data.decode("utf-8").splitlines()

    conn = get_connection()
    c = conn.cursor()
    count = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 7:
            continue
        category, question, o1, o2, o3, o4, ans = parts
        ans = ans.upper()
        if ans not in ["A", "B", "C", "D"]:
            continue
        ans_idx = ["A", "B", "C", "D"].index(ans) + 1
        c.execute(
            "INSERT INTO quiz_questions (category, question, option1, option2, option3, option4, answer) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (category, question, o1, o2, o3, o4, ans_idx),
        )
        count += 1
    conn.commit()
    conn.close()
    await ctx.send(f"✅ 已导入 {count} 道题目。")


@bot.command(name="deletequiz")
@commands.has_permissions(administrator=True)
async def deletequiz(ctx, category: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, question FROM quiz_questions WHERE category = %s", (category,))
    rows = c.fetchall()
    if not rows:
        conn.close()
        await ctx.send("该类别没有题目。")
        return

    msg_lines = [f"{i + 1}. {q}" for i, (qid, q) in enumerate(rows)]
    await ctx.send("**题目列表：**\n" + "\n".join(msg_lines))
    await ctx.send("请输入要删除的题号，以空格分隔，或输入 `取消` 终止。")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        reply = await bot.wait_for("message", check=check, timeout=300.0)
    except asyncio.TimeoutError:
        await ctx.send("操作超时，已取消。")
        conn.close()
        return

    if reply.content.strip().lower() == "取消":
        await ctx.send("已取消。")
        conn.close()
        return

    try:
        numbers = [int(n) for n in reply.content.strip().split()]
    except ValueError:
        await ctx.send("输入格式错误。")
        conn.close()
        return

    ids = []
    for num in numbers:
        if 1 <= num <= len(rows):
            ids.append(rows[num - 1][0])

    if not ids:
        await ctx.send("没有有效的题号可删除。")
        conn.close()
        return

    format_strings = ",".join(["%s"] * len(ids))
    c.execute(f"DELETE FROM quiz_questions WHERE id IN ({format_strings})", ids)
    conn.commit()
    conn.close()
    await ctx.send(f"已删除 {len(ids)} 道题目。")


@bot.command(name="quiz")
@commands.has_permissions(administrator=True)
async def quiz(ctx, category: str, number: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT question, option1, option2, option3, option4, answer FROM quiz_questions WHERE category = %s",
        (category,),
    )
    rows = c.fetchall()
    conn.close()

    if not rows:
        await ctx.send("该类别没有题目。")
        return

    random.shuffle(rows)
    if number > len(rows):
        number = len(rows)
    rows = rows[:number]

    for q, o1, o2, o3, o4, ans in rows:
        await ctx.send(f"**{q}**\nA. {o1}\nB. {o2}\nC. {o3}\nD. {o4}")
        await ctx.send("🎮 游戏开始，你只有 60 秒的时间作答！")

        start = asyncio.get_event_loop().time()
        answered = False
        attempted_users = set()

        async def warn_after_delay():
            await asyncio.sleep(50)
            if not answered:
                await ctx.send("⏰ 仅剩下 10 秒！")

        warning_task = asyncio.create_task(warn_after_delay())

        while True:
            remaining = 60 - (asyncio.get_event_loop().time() - start)
            if remaining <= 0:
                break

            def check(m):
                return (
                    not m.author.bot
                    and m.channel == ctx.channel
                    and m.content.upper() in ["A", "B", "C", "D", "1", "2", "3", "4"]
                    and m.author.id not in attempted_users
                )

            try:
                reply = await bot.wait_for("message", check=check, timeout=remaining)
            except asyncio.TimeoutError:
                break

            attempted_users.add(reply.author.id)
            txt = reply.content.upper()
            if txt in ["1", "2", "3", "4"]:
                choice = int(txt)
            else:
                choice = ["A", "B", "C", "D"].index(txt) + 1

            if choice == ans:
                letter = ["A", "B", "C", "D"][ans - 1]
                await ctx.send(f"✅ {reply.author.mention} 答对了！正确答案是 {letter}，奖励 10 分")
                conn = get_connection()
                c = conn.cursor()
                c.execute(
                    "INSERT INTO users (user_id, points, last_draw) VALUES (%s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE points = points + VALUES(points)",
                    (reply.author.id, 10, "1970-01-01"),
                )
                conn.commit()
                conn.close()
                answered = True
                break
            else:
                await ctx.send(f"❌ {reply.author.mention} 答错了！你已经没有再答的机会啦")

        if not warning_task.done():
            warning_task.cancel()

        if not answered:
            letter = ["A", "B", "C", "D"][ans - 1]
            await ctx.send(f"⏰ 时间到，正确答案是 {letter}")

    await ctx.send("答题结束！")

@bot.tree.command(name="help", description="显示所有可用命令的帮助信息")
async def help_command(interaction: discord.Interaction):
    """Show help information for all commands"""
    embed = discord.Embed(
        title="🎰 Daily Draw Bot 帮助",
        description="欢迎使用每日抽奖机器人！",
        color=discord.Color.blue()
    )
    
    # Draw rules
    embed.add_field(
        name="📋 抽奖规则",
        value="""🎉 **免费抽奖**：每天1次，完全免费
🎰 **付费抽奖**：每天最多10次，每次消耗100积分
⏰ **重置时间**：每天0点自动重置抽奖次数
💰 **奖励范围**：10-1000积分，平均回报率103.8%""",
        inline=False
    )
    
    # User commands (always visible)
    embed.add_field(
        name="🎲 用户命令",
        value="""`!draw` - 每日抽奖（免费1次，付费最多10次/天）
`!check [用户]` - 查看积分和抽奖状态
`!ranking` - 查看积分排行榜
`!roleshop` - 查看身份组商店
`!buy <身份组名>` - 购买身份组""",
        inline=False
    )
    
    # Quiz commands (always visible)
    embed.add_field(
        name="🎮 答题系统",
        value="""`!quizlist` - 查看题库类别
`!quiz <类别> <题目数>` - 开始答题游戏""",
        inline=False
    )
    
    # Check if user has administrator permissions
    if interaction.user.guild_permissions.administrator:
        embed.add_field(
            name="⚙️ 管理员命令",
            value="""`!givepoints <用户> <积分>` - 给予用户积分
`!setpoints <用户> <积分>` - 设置用户积分
`!resetdraw <用户>` - 重置用户抽奖状态
`!resetall --confirm` - 清空所有用户数据
`!fixdb` - 修复数据库结构
`!addtag <价格> <身份组>` - 添加可购买身份组
`!rewardinfo` - 查看抽奖概率系统
`!testdraw [次数]` - 测试抽奖系统
`!importquiz` - 导入题库文件
`!deletequiz <类别>` - 删除题库题目""",
            inline=False
        )
    
    embed.set_footer(text="每日免费抽奖1次，付费抽奖最多10次/天，每次消耗100积分")
    await interaction.response.send_message(embed=embed)


@bot.command(name="ranking")
async def ranking(ctx):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()

    if not rows:
        await ctx.send("没有排名数据。")
        return

    entries = []
    for i, (user_id, points) in enumerate(rows, start=1):
        user = await bot.fetch_user(user_id)
        avatar_bytes = await user.display_avatar.replace(size=64).read()
        avatar = Image.open(BytesIO(avatar_bytes)).convert("RGBA").resize((64, 64))
        entries.append((avatar, f"{i}. {user.name}: {points} points"))

    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    
    if os.path.exists(font_path):
        font = ImageFont.truetype(font_path, 20)
    else:
        font = ImageFont.load_default()

    padding = 20
    line_height = 85
    draw_dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    def text_width(text: str) -> int:
        box = draw_dummy.textbbox((0, 0), text, font=font)
        return box[2] - box[0]

    max_text_width = max(text_width(t) for _, t in entries)
    width = max_text_width + 140

    height = line_height * len(entries) + padding * 2
    img = Image.new("RGBA", (width, height), (245, 245, 245, 255))
    draw = ImageDraw.Draw(img)

    y = padding
    for avatar, text in entries:
        img.paste(avatar, (padding, y + 3), avatar)
        draw.text((padding + 70, y + 20), text, fill=(0, 0, 0), font=font)
        draw.line((padding, y, width - padding, y), fill=(220, 220, 220), width=1)
        y += line_height
    draw.line((padding, y, width - padding, y), fill=(220, 220, 220), width=1)

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    await ctx.send(file=File(fp=buffer, filename="ranking.png"))

bot.run(TOKEN)
