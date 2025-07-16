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

    await ctx.send(f"你确定要购买 `{role.name}` 吗？请在 10 秒内回复 `Y`。")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        reply = await ctx.bot.wait_for("message", check=check, timeout=10.0)
        if reply.content.upper() != "Y":
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

async def giftpoints(ctx, member: discord.Member, amount: int):
    """允许用户将自己的积分赠送给其他用户"""
    # 检查是否赠送给自己
    if member.id == ctx.author.id:
        await ctx.send("❌ 你不能给自己赠送积分哦！")
        return
        
    # 检查赠送数量是否为正数
    if amount <= 0:
        await ctx.send("❌ 赠送的积分必须是正数！")
        return
        
    conn = get_connection()
    c = conn.cursor()
    
    # 检查赠送者是否有足够积分
    c.execute("SELECT points FROM users WHERE user_id = %s", (ctx.author.id,))
    sender_row = c.fetchone()
    
    if not sender_row:
        await ctx.send("❌ 你还没有积分记录，无法赠送积分。")
        conn.close()
        return
        
    sender_points = sender_row[0]
    
    if sender_points < amount:
        await ctx.send(f"❌ 你的积分不足！当前积分: {sender_points}")
        conn.close()
        return
    
    # 确认赠送
    embed = discord.Embed(
        title="🎁 积分赠送确认",
        description=f"你确定要赠送 **{amount}** 积分给 {member.mention} 吗？\n\n发送 `Y` 继续，或任意其他内容取消。",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        reply = await ctx.bot.wait_for("message", check=check, timeout=15.0)
        if reply.content.upper() != "Y":
            await ctx.send("❌ 已取消赠送。")
            conn.close()
            return
    except asyncio.TimeoutError:
        await ctx.send("⏰ 确认超时，已取消赠送。")
        conn.close()
        return
    
    # 执行积分转移
    c.execute("UPDATE users SET points = points - %s WHERE user_id = %s", (amount, ctx.author.id))
    
    # 为接收者添加积分（如果不存在则创建记录）
    c.execute(
        "INSERT INTO users (user_id, points, last_draw) VALUES (%s, %s, %s) "
        "ON DUPLICATE KEY UPDATE points = points + %s",
        (member.id, amount, "1970-01-01", amount)
    )
    
    conn.commit()
    conn.close()
    
    # 发送成功消息
    embed = discord.Embed(
        title="✅ 积分赠送成功",
        description=f"{ctx.author.mention} 成功赠送了 **{amount}** 积分给 {member.mention}！",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

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

async def setpoints(ctx, member: discord.Member, points: int):
    """将成员的积分精确设置为指定值。"""
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