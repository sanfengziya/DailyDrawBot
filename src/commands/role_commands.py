import discord
import asyncio
from src.db.database import get_connection
from src.utils.ui import RolePageView

async def addtag(ctx, price, role):
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

async def buytag(ctx, role_name):
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
        reply = await ctx.bot.wait_for("message", check=check, timeout=10.0)
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

async def givepoints(ctx, member, amount):
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

async def setpoints(ctx, member, points):
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