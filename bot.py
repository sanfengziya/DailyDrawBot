# Daily Draw Bot

import discord
from discord.ext import commands
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
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

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
            last_draw DATE
        )
        """
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
    conn.commit()
    c.close()
    conn.close()


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
            title=f"{name}",
            description=f"价格：{price} 分\n\n第 {index + 1} / {len(self.rows)} 个",
            color=color,
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
    c.execute("SELECT points, last_draw FROM users WHERE user_id = %s", (user_id,))
    row = c.fetchone()

    if row:
        last_draw_date = row[1]
        if isinstance(last_draw_date, str):
            last_draw_date = datetime.datetime.strptime(last_draw_date, "%Y-%m-%d").date()
        elif isinstance(last_draw_date, datetime.datetime):
            last_draw_date = last_draw_date.date()
        if last_draw_date == today:
            await ctx.send(f"{ctx.author.mention} 你今天已经抽过奖啦，请明天再来。")
            conn.close()
            return
    else:
        c.execute("INSERT INTO users (user_id, points, last_draw) VALUES (%s, %s, %s)", (user_id, 0, "1970-01-01"))
        conn.commit()

    earned = random.randint(1, 100)
    c.execute("UPDATE users SET points = points + %s, last_draw = %s WHERE user_id = %s", (earned, str(today), user_id))
    conn.commit()
    conn.close()

    await ctx.send(f"{ctx.author.mention} 你抽到了 **{earned}** 分！明天（UTC-4）时间凌晨 0 点后可再次参与。")

@bot.command(name="check")
async def check(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    user_id = member.id
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT points FROM users WHERE user_id = %s", (user_id,))
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
    c.execute("SELECT role_id, price FROM tags")
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

@bot.command(name="give")
@commands.has_permissions(administrator=True)
async def give(ctx, member: discord.Member, amount: int):
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


@bot.command(name="setpoint")
@commands.has_permissions(administrator=True)
async def setpoint(ctx, member: discord.Member, points: int):
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
