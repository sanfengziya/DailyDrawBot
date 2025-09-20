import discord
from discord.ext import commands
import asyncio
import datetime
from src.db.database import get_connection
from src.utils.helpers import now_est, get_weighted_reward
from src.config.config import WHEEL_COST, MAX_PAID_DRAWS_PER_DAY

async def draw(ctx):
    user_id = str(ctx.author.id)
    now = now_est()
    today = now.date()

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT points, last_draw, paid_draws_today, last_paid_draw_date FROM users WHERE user_id = %s", (user_id,))
    row = c.fetchone()

    if row:
        points, last_draw_date, paid_draws_today, last_paid_draw_date = row
    else:
        c.execute("INSERT INTO users (user_id, points, last_draw, paid_draws_today, last_paid_draw_date) VALUES (%s, %s, %s, %s, %s)", 
                 (user_id, 0, "1970-01-01", 0, "1970-01-01"))
        conn.commit()
        points, last_draw_date, paid_draws_today, last_paid_draw_date = 0, datetime.date(1970, 1, 1), 0, datetime.date(1970, 1, 1)

    first_draw = last_draw_date != today
    
    # 如果是新的一天，重置付费抽奖计数器
    if last_paid_draw_date != today:
        paid_draws_today = 0

    if first_draw:
        # 当天第一次抽奖 - 免费！
        await ctx.send(f"🎉 {ctx.author.mention} 开始今天的抽奖吧！")
    else:
        # 检查用户是否已达到每日付费抽奖上限
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
            msg = await ctx.bot.wait_for("message", check=check, timeout=15)
        except asyncio.TimeoutError:
            conn.close()
            await ctx.send("⏰ 已取消抽奖。")
            return

        if msg.content.upper() != "Y":
            conn.close()
            await ctx.send("❌ 已取消抽奖。")
            return

        c.execute("UPDATE users SET points = points - %s WHERE user_id = %s", (WHEEL_COST, user_id))

    reward = get_weighted_reward()
    
    if first_draw:
        # 免费抽奖 - 只更新积分和最后抽奖日期
        c.execute(
            "UPDATE users SET points = points + %s, last_draw = %s WHERE user_id = %s",
            (reward["points"], str(today), user_id),
        )
    else:
        # 付费抽奖 - 更新积分、最后抽奖日期、今日付费抽奖次数和最后付费抽奖日期
        new_paid_draws = paid_draws_today + 1
        c.execute(
            "UPDATE users SET points = points + %s, last_draw = %s, paid_draws_today = %s, last_paid_draw_date = %s WHERE user_id = %s",
            (reward["points"], str(today), new_paid_draws, str(today), user_id),
        )
    conn.commit()
    conn.close()

    # 为奖励创建精美的嵌入消息
    embed = discord.Embed(
        title=f"{reward['emoji']} 抽奖结果",
        description=f"**{reward['message']}**\n获得 **{reward['points']}** 分！",
        color=discord.Color.gold() if reward['points'] >= 300 else discord.Color.blue() if reward['points'] >= 100 else discord.Color.green()
    )
    
    # 为高价值奖励添加特殊效果
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

async def check(ctx, member=None):
    user_id = str(member.id) if member else str(ctx.author.id)
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT points, last_draw, paid_draws_today, last_paid_draw_date FROM users WHERE user_id = %s", (user_id,))
    row = c.fetchone()
    conn.close()

    if row:
        points, last_draw, paid_draws_today, last_paid_draw_date = row 

        embed = discord.Embed(
            title=f"💰 {member.display_name if member else ctx.author.display_name} 的积分信息",
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
        
        today = now_est().date()
        # 只有在确实是新的一天且需要显示重置值时才重置
        # 出于显示目的，我们将显示实际的数据库值
        display_paid_draws = paid_draws_today
        if last_paid_draw_date != today:
            # 这只是用于显示计算，不修改实际值
            display_paid_draws = 0
        
        remaining_draws = MAX_PAID_DRAWS_PER_DAY - display_paid_draws
        embed.add_field(name="付费抽奖", value=f"**{display_paid_draws}/{MAX_PAID_DRAWS_PER_DAY}** 次\n剩余: **{remaining_draws}** 次", inline=True)
        
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ 用户信息",
            description=f"{member.mention} 还没有参与过抽奖~",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

async def reset_draw(ctx, member):
    user_id = str(member.id)
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

async def reset_all(ctx, confirm=None):
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

async def fix_database(ctx):
    """强制更新数据库架构以支持付费抽奖跟踪"""
    conn = get_connection()
    c = conn.cursor()
    
    # 检查并添加缺失的列
    c.execute("SHOW COLUMNS FROM users LIKE 'paid_draws_today'")
    if not c.fetchone():
        c.execute("ALTER TABLE users ADD COLUMN paid_draws_today INT DEFAULT 0")
        print("Added paid_draws_today column")
        await ctx.send("✅ 已添加 paid_draws_today 字段")
    else:
        await ctx.send("✅ paid_draws_today 字段已存在")
    
    c.execute("SHOW COLUMNS FROM users LIKE 'last_paid_draw_date'")
    if not c.fetchone():
        c.execute("ALTER TABLE users ADD COLUMN last_paid_draw_date DATE DEFAULT '1970-01-01'")
        print("Added last_paid_draw_date column")
        await ctx.send("✅ 已添加 last_paid_draw_date 字段")
    else:
        await ctx.send("✅ last_paid_draw_date 字段已存在")
    
    # 更新现有用户以具有适当的默认值
    c.execute("UPDATE users SET paid_draws_today = 0 WHERE paid_draws_today IS NULL")
    c.execute("UPDATE users SET last_paid_draw_date = '1970-01-01' WHERE last_paid_draw_date IS NULL")
    
    # 强制将所有用户更新为今天的日期以进行测试
    today = now_est().date()
    c.execute("UPDATE users SET last_paid_draw_date = %s WHERE last_paid_draw_date = '1970-01-01'", (str(today),))
    
    conn.commit()
    conn.close()
    
    await ctx.send(f"{ctx.author.mention} ✅ 数据库结构已修复，付费抽奖追踪功能已启用。所有用户的 last_paid_draw_date 已更新为今天。")