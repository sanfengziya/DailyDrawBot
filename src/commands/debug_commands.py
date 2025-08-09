import discord
import datetime
from src.db.database import get_connection
from src.utils.helpers import now_est

async def debug_user(ctx, member):
    """调试用户的付费抽奖信息"""
    user_id = member.id
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT points, last_draw, paid_draws_today, last_paid_draw_date FROM users WHERE user_id = %s", (str(user_id),))
    row = c.fetchone()
    conn.close()
    
    if row:
        points, last_draw, paid_draws_today, last_paid_draw_date = row
        today = now_est().date()
        
        embed = discord.Embed(
            title=f"🔍 {member.display_name} 的调试信息",
            color=discord.Color.blue()
        )
        embed.add_field(name="用户ID", value=str(user_id), inline=True)
        embed.add_field(name="积分", value=str(points), inline=True)
        embed.add_field(name="最后抽奖日期", value=str(last_draw), inline=True)
        embed.add_field(name="付费抽奖次数", value=str(paid_draws_today), inline=True)
        embed.add_field(name="最后付费抽奖日期", value=str(last_paid_draw_date), inline=True)
        embed.add_field(name="今天日期", value=str(today), inline=True)
        embed.add_field(name="是否新的一天", value=str(last_paid_draw_date != today), inline=True)
        
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ 用户 {member.mention} 不存在于数据库中。")

async def test_update(ctx, member):
    """测试付费抽奖的数据库更新"""
    user_id = member.id
    today = now_est().date()
    
    conn = get_connection()
    c = conn.cursor()
    
    # 首先，获取当前值
    c.execute("SELECT points, last_draw, paid_draws_today, last_paid_draw_date FROM users WHERE user_id = %s", (str(user_id),))
    row = c.fetchone()
    
    if row:
        points, last_draw, paid_draws_today, last_paid_draw_date = row
        await ctx.send(f"🔍 更新前的数据：\n积分: {points}\n付费抽奖次数: {paid_draws_today}\n最后付费抽奖日期: {last_paid_draw_date}")
        
        # 测试更新
        new_paid_draws = paid_draws_today + 1
        c.execute(
            "UPDATE users SET points = points + 0, last_draw = %s, paid_draws_today = %s, last_paid_draw_date = %s WHERE user_id = %s",
            (str(today), new_paid_draws, str(today), str(user_id)),
        )
        conn.commit()
        
        # 检查更新是否成功
        c.execute("SELECT points, last_draw, paid_draws_today, last_paid_draw_date FROM users WHERE user_id = %s", (str(user_id),))
        row_after = c.fetchone()
        
        if row_after:
            points_after, last_draw_after, paid_draws_after, last_paid_draw_date_after = row_after
            await ctx.send(f"✅ 更新后的数据：\n积分: {points_after}\n付费抽奖次数: {paid_draws_after}\n最后付费抽奖日期: {last_paid_draw_date_after}")
        else:
            await ctx.send("❌ 更新后无法读取数据")
    else:
        await ctx.send(f"❌ 用户 {member.mention} 不存在于数据库中。")
    
    conn.close()

async def check_database(ctx):
    """检查付费抽奖跟踪的数据库结构"""
    conn = get_connection()
    c = conn.cursor()
    
    # 检查表结构
    c.execute("DESCRIBE users")
    columns = c.fetchall()
    
    embed = discord.Embed(
        title="🔍 数据库结构检查",
        color=discord.Color.blue()
    )
    
    for column in columns:
        field_name, field_type, null, key, default, extra = column
        embed.add_field(
            name=field_name,
            value=f"类型: {field_type}\n默认值: {default}\n允许NULL: {null}",
            inline=True
        )
    
    # 检查付费抽奖列是否存在
    c.execute("SHOW COLUMNS FROM users LIKE 'paid_draws_today'")
    paid_draws_exists = c.fetchone() is not None
    
    c.execute("SHOW COLUMNS FROM users LIKE 'last_paid_draw_date'")
    last_paid_date_exists = c.fetchone() is not None
    
    embed.add_field(
        name="字段检查",
        value=f"paid_draws_today: {'✅' if paid_draws_exists else '❌'}\nlast_paid_draw_date: {'✅' if last_paid_date_exists else '❌'}",
        inline=False
    )
    
    conn.close()
    await ctx.send(embed=embed)

async def detailed_debug(ctx, member):
    """付费抽奖逻辑的详细调试"""
    user_id = member.id
    today = now_est().date()
    
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT points, last_draw, paid_draws_today, last_paid_draw_date FROM users WHERE user_id = %s", (str(user_id),))
    row = c.fetchone()
    conn.close()
    
    if row:
        points, last_draw, paid_draws_today, last_paid_draw_date = row
        
        # 解析日期
        if isinstance(last_paid_draw_date, str):
            last_paid_draw_date_obj = datetime.datetime.strptime(last_paid_draw_date, "%Y-%m-%d").date()
        elif isinstance(last_paid_draw_date, datetime.datetime):
            last_paid_draw_date_obj = last_paid_draw_date.date()
        elif isinstance(last_paid_draw_date, datetime.date):
            last_paid_draw_date_obj = last_paid_draw_date
        else:
            last_paid_draw_date_obj = datetime.date(1970, 1, 1)
        
        # 确保today是日期类型
        if isinstance(today, datetime.datetime):
            today_date = today.date()
        elif isinstance(today, datetime.date):
            today_date = today
        else:
            today_date = datetime.datetime.strptime(str(today), "%Y-%m-%d").date()
        
        # 计算显示值
        display_paid_draws = paid_draws_today
        is_new_day = last_paid_draw_date_obj != today_date
        if is_new_day:
            display_paid_draws = 0
        
        embed = discord.Embed(
            title=f"🔍 {member.display_name} 详细调试信息",
            color=discord.Color.blue()
        )
        embed.add_field(name="数据库中的付费抽奖次数", value=str(paid_draws_today), inline=True)
        embed.add_field(name="最后付费抽奖日期", value=str(last_paid_draw_date), inline=True)
        embed.add_field(name="今天日期", value=str(today_date), inline=True)
        embed.add_field(name="是否新的一天", value=str(is_new_day), inline=True)
        embed.add_field(name="显示用的付费抽奖次数", value=str(display_paid_draws), inline=True)
        embed.add_field(name="剩余付费抽奖次数", value=str(10 - display_paid_draws), inline=True)
        
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ 用户 {member.mention} 不存在于数据库中。")

async def rewardinfo(ctx):
    """显示当前奖励系统信息"""
    from src.config.config import REWARD_SYSTEM
    
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

async def testdraw(ctx, times=100):
    """测试多次抽奖的奖励系统"""
    from src.utils.helpers import get_weighted_reward
    
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