import discord
from discord.ext import commands
import asyncio
import datetime
from src.db.database import get_connection, get_missing_user_id, create_user_with_specific_id
from src.utils.helpers import now_est, get_weighted_reward, get_user_id_with_validation_ctx
from src.config.config import WHEEL_COST, MAX_PAID_DRAWS_PER_DAY
from src.utils.cache import UserCache
from src.utils.draw_limiter import DrawLimiter

async def draw(ctx):
    discord_user_id = ctx.author.id
    guild_id = ctx.guild.id

    try:
        supabase = get_connection()

        # 使用Redis缓存获取用户ID
        user_id = await UserCache.get_user_id(guild_id, discord_user_id)

        if user_id is None:
            # 创建新用户 - 优先使用缺失的ID（1-6）
            missing_id = get_missing_user_id()

            if missing_id is not None:
                create_response = create_user_with_specific_id(missing_id, ctx.guild.id, ctx.author.id)
                if create_response:
                    user_id = create_response['id']
                else:
                    await ctx.send("创建用户时出错，请稍后重试。")
                    return
            else:
                create_response = supabase.table('users').insert({
                    'guild_id': ctx.guild.id,
                    'discord_user_id': ctx.author.id,
                    'points': 0,
                    'last_draw_date': '1970-01-01',
                    'paid_draws_today': 0,
                    'last_paid_draw_date': '1970-01-01'
                }).execute()
                user_id = create_response.data[0]['id']

        # 使用Redis检查免费抽奖
        first_draw = DrawLimiter.check_free_draw_available(guild_id, discord_user_id)

        # 使用Redis获取用户积分
        points = await UserCache.get_points(guild_id, discord_user_id)

    except Exception as e:
        await ctx.send(f"查询用户数据时出错：{str(e)}")
        return

    if first_draw:
        # 当天第一次抽奖 - 免费！
        await ctx.send(f"🎉 {ctx.author.mention} 开始今天的抽奖吧！")
    else:
        # 使用Redis获取付费抽奖次数
        paid_draws_today = DrawLimiter.get_paid_draw_count(guild_id, discord_user_id)

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

        # 先尝试增加付费抽奖计数 (使用Lua脚本原子性检查)
        increment_success = DrawLimiter.increment_paid_draw(guild_id, discord_user_id, MAX_PAID_DRAWS_PER_DAY)
        if not increment_success:
            # 虽然前面检查通过了，但在用户确认期间可能其他地方也在抽奖，导致超限
            await ctx.send("❌ 抽奖失败：已达到每日付费抽奖上限（可能有其他操作占用了名额）")
            return

        # 扣除积分 (使用UserCache更新)
        try:
            await UserCache.update_points(guild_id, discord_user_id, user_id, -WHEEL_COST)
        except Exception as e:
            # 扣除积分失败，需要回滚计数
            from src.db.redis_client import redis_client
            today_str = now_est().date()
            paid_key = f'draw:paid:{guild_id}:{discord_user_id}:{today_str}'
            redis_client.decr(paid_key)  # 回滚计数
            await ctx.send(f"扣除积分时出错：{str(e)}")
            return

    reward = get_weighted_reward()
    today = now_est().date()

    if first_draw:
        # 免费抽奖 - 更新积分并标记今日免费抽奖已使用
        try:
            # 更新积分到数据库和缓存
            await UserCache.update_points(guild_id, discord_user_id, user_id, reward["points"])

            # 更新数据库中的last_draw_date
            supabase.table('users').update({
                'last_draw_date': str(today)
            }).eq('id', user_id).execute()

            # 标记免费抽奖已使用 (Redis自动过期)
            DrawLimiter.mark_free_draw_used(guild_id, discord_user_id)
        except Exception as e:
            await ctx.send(f"更新用户数据时出错：{str(e)}")
            return
    else:
        # 付费抽奖 - 增加积分
        try:
            # 更新积分 (已经扣除了WHEEL_COST，现在加上奖励积分)
            await UserCache.update_points(guild_id, discord_user_id, user_id, reward["points"])

            # 更新数据库中的抽奖记录 (计数已在Redis中增加)
            paid_draws_today = DrawLimiter.get_paid_draw_count(guild_id, discord_user_id)
            supabase.table('users').update({
                'last_draw_date': str(today),
                'paid_draws_today': paid_draws_today,  # 使用Redis中的当前值
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
        # 使用Redis缓存获取用户ID
        user_id = await UserCache.get_user_id(guild_id, discord_user_id)

        if user_id is None:
            # 用户不存在
            embed = discord.Embed(
                title="❌ 用户信息",
                description=f"{target_user.mention} 还没有参与过抽奖~",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        # 使用Redis获取积分
        points = await UserCache.get_points(guild_id, discord_user_id)

        # 使用Redis检查今日是否已抽奖
        free_draw_available = DrawLimiter.check_free_draw_available(guild_id, discord_user_id)

        # 使用Redis获取付费抽奖次数
        paid_draws_today = DrawLimiter.get_paid_draw_count(guild_id, discord_user_id)

    except Exception as e:
        await ctx.send(f"查询用户数据时出错：{str(e)}")
        return

    # 显示用户积分信息
    embed = discord.Embed(
        title=f"💰 {member.display_name if member else ctx.author.display_name} 的积分信息",
        color=discord.Color.blue()
    )
    embed.add_field(name="当前积分", value=f"**{points}** 分", inline=True)

    # 显示今日免费抽奖状态
    if free_draw_available:
        embed.add_field(name="今日抽奖", value="❌ 未完成", inline=True)
    else:
        embed.add_field(name="今日抽奖", value="✅ 已完成", inline=True)

    # 显示付费抽奖次数
    remaining_draws = MAX_PAID_DRAWS_PER_DAY - paid_draws_today
    embed.add_field(name="付费抽奖", value=f"**{paid_draws_today}/{MAX_PAID_DRAWS_PER_DAY}** 次\n剩余: **{remaining_draws}** 次", inline=True)

    await ctx.send(embed=embed)