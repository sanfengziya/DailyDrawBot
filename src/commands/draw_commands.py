import discord
from discord.ext import commands
import asyncio
import datetime
from src.db.database import get_connection
from src.utils.helpers import now_est, get_weighted_reward
from src.config.config import WHEEL_COST, MAX_PAID_DRAWS_PER_DAY

async def draw(ctx):
    discord_user_id = ctx.author.id
    guild_id = ctx.guild.id
    today = now_est().date()
    
    try:
        supabase = get_connection()
        
        # 查询用户信息
        user_response = supabase.table('users').select('id, points, last_draw_date, paid_draws_today, last_paid_draw_date').eq('discord_user_id', discord_user_id).eq('guild_id', guild_id).execute()
        
        if user_response.data:
            user_data = user_response.data[0]
            user_id = user_data['id']
            points = user_data['points'] or 0
            last_draw_date = datetime.datetime.strptime(user_data['last_draw_date'], '%Y-%m-%d').date() if user_data['last_draw_date'] else datetime.date(1970, 1, 1)
            paid_draws_today = user_data['paid_draws_today'] or 0
            last_paid_draw_date = datetime.datetime.strptime(user_data['last_paid_draw_date'], '%Y-%m-%d').date() if user_data['last_paid_draw_date'] else datetime.date(1970, 1, 1)
        else:
            # 创建新用户
            create_response = supabase.table('users').insert({
                'guild_id': ctx.guild.id,
                'discord_user_id': ctx.author.id,
                'points': 0,
                'last_draw_date': '1970-01-01',
                'paid_draws_today': 0,
                'last_paid_draw_date': '1970-01-01'
            }).execute()
            user_id = create_response.data[0]['id']
            points, last_draw_date, paid_draws_today, last_paid_draw_date = 0, datetime.date(1970, 1, 1), 0, datetime.date(1970, 1, 1)
            
    except Exception as e:
        await ctx.send(f"查询用户数据时出错：{str(e)}")
        return

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
            embed = discord.Embed(
                title="❌ 今日付费抽奖次数已达上限",
                description=f"你今日已付费抽奖 **{paid_draws_today}** 次\n每日最多可付费抽奖 **{MAX_PAID_DRAWS_PER_DAY}** 次\n\n明天再来吧！",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        if points < WHEEL_COST:
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
            await ctx.send("⏰ 已取消抽奖。")
            return

        if msg.content.upper() != "Y":
            await ctx.send("❌ 已取消抽奖。")
            return

        # 扣除积分
        try:
            supabase.table('users').update({
                'points': points - WHEEL_COST
            }).eq('id', user_id).execute()
        except Exception as e:
            await ctx.send(f"扣除积分时出错：{str(e)}")
            return

    reward = get_weighted_reward()
    
    if first_draw:
        # 免费抽奖 - 只更新积分和最后抽奖日期
        try:
            supabase.table('users').update({
                'points': points + reward["points"],
                'last_draw_date': str(today)
            }).eq('id', user_id).execute()
        except Exception as e:
            await ctx.send(f"更新用户数据时出错：{str(e)}")
            return
    else:
        # 付费抽奖 - 更新积分、最后抽奖日期、今日付费抽奖次数和最后付费抽奖日期
        new_paid_draws = paid_draws_today + 1
        new_points = points - WHEEL_COST + reward["points"]
        try:
            supabase.table('users').update({
                'points': new_points,
                'last_draw_date': str(today),
                'paid_draws_today': new_paid_draws,
                'last_paid_draw_date': str(today)
            }).eq('id', user_id).execute()
        except Exception as e:
            await ctx.send(f"更新用户数据时出错：{str(e)}")
            return

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
    target_user = member if member else ctx.author
    discord_user_id = target_user.id
    guild_id = ctx.guild.id
    
    try:
        supabase = get_connection()
        
        # 查询用户信息
        user_response = supabase.table('users').select('points, last_draw_date, paid_draws_today, last_paid_draw_date').eq('discord_user_id', discord_user_id).eq('guild_id', guild_id).execute()
        
        if user_response.data:
            user_data = user_response.data[0]
            points = user_data['points']
            last_draw = user_data['last_draw_date']
            paid_draws_today = user_data['paid_draws_today'] or 0
            last_paid_draw_date = user_data['last_paid_draw_date']
            
    except Exception as e:
        await ctx.send(f"查询用户数据时出错：{str(e)}")
        return

    if user_response.data: 

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
        target_user = member if member else ctx.author
        embed = discord.Embed(
            title="❌ 用户信息",
            description=f"{target_user.mention} 还没有参与过抽奖~",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

async def reset_draw(ctx, member):
    discord_user_id = member.id
    guild_id = ctx.guild.id
    yesterday = (now_est().date() - datetime.timedelta(days=1)).isoformat()

    try:
        supabase = get_connection()
        
        # 检查用户是否存在
        user_response = supabase.table('users').select('id').eq('discord_user_id', discord_user_id).eq('guild_id', guild_id).execute()
        
        if user_response.data:
            user_id = user_response.data[0]['id']
            # 更新用户的抽奖状态
            supabase.table('users').update({
                'last_draw_date': yesterday
            }).eq('id', user_id).execute()
            await ctx.send(f"{ctx.author.mention} 已成功重置 {member.mention} 的抽奖状态 ✅")
        else:
            await ctx.send(f"{ctx.author.mention} 该用户还没有抽奖记录，无法重置。")
            
    except Exception as e:
        await ctx.send(f"重置抽奖状态时出错：{str(e)}")
        return

async def reset_all(ctx, confirm=None):
    if confirm != "--confirm":
        await ctx.send(
            f"{ctx.author.mention} ⚠️ 此操作将永久清空所有用户数据！\n"
            "如确定请使用：`!resetall --confirm`"
        )
        return

    try:
        supabase = get_connection()
        
        # 删除所有用户数据
        # 注意：Supabase需要先查询所有记录，然后删除
        all_users = supabase.table('users').select('id').execute()
        if all_users.data:
            user_ids = [user['id'] for user in all_users.data]
            for user_id in user_ids:
                supabase.table('users').delete().eq('id', user_id).execute()
        
        await ctx.send(f"{ctx.author.mention} ✅ 所有用户数据已被清除。")
        
    except Exception as e:
        await ctx.send(f"清除用户数据时出错：{str(e)}")
        return

async def fix_database(ctx):
    """
    此函数已禁用 - 原本用于MySQL数据库架构更新
    
    在Supabase中，数据库架构应该通过Supabase控制台或迁移脚本来管理。
    请确保users表包含以下字段：
    - user_id (text)
    - points (integer, default: 0)
    - last_draw (text, default: '1970-01-01')
    - paid_draws_today (integer, default: 0)
    - last_paid_draw_date (text, default: '1970-01-01')
    """
    await ctx.send(
        f"{ctx.author.mention} ❌ 此功能已禁用。\n"
        "数据库架构管理现在通过Supabase控制台进行。\n"
        "请确保users表包含所有必要的字段。"
    )