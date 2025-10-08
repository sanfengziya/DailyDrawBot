import discord
from src.utils.cache import UserCache
from src.utils.draw_limiter import DrawLimiter
from src.config.config import MAX_PAID_DRAWS_PER_DAY

async def check(ctx, member=None):
    """查询用户积分和抽奖状态"""
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

        # 使用Redis检查今日是否已抽奖（异步）
        free_draw_available = await DrawLimiter.check_free_draw_available(guild_id, discord_user_id)

        # 使用Redis获取付费抽奖次数（异步）
        paid_draws_today = await DrawLimiter.get_paid_draw_count(guild_id, discord_user_id)

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
