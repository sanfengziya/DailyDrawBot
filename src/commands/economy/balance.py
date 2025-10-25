import discord
from src.utils.cache import UserCache
from src.utils.draw_limiter import DrawLimiter
from src.config.config import MAX_PAID_DRAWS_PER_DAY
from src.utils.i18n import get_guild_locale, t

async def check(ctx, member=None):
    """查询用户积分和抽奖状态"""
    target_user = member if member else ctx.author
    discord_user_id = target_user.id
    guild_id = ctx.guild.id
    locale = get_guild_locale(guild_id)

    try:
        # 使用Redis缓存获取用户ID
        user_id = await UserCache.get_user_id(guild_id, discord_user_id)

        if user_id is None:
            # 用户不存在
            embed = discord.Embed(
                title=t("economy.check.user_info_title", locale=locale),
                description=t("economy.check.user_info_description", locale=locale, mention=target_user.mention),
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
        await ctx.send(t("economy.common.query_failed", locale=locale, error=str(e)))
        return

    # 显示用户积分信息
    display_name = target_user.display_name
    embed = discord.Embed(
        title=t("economy.check.title", locale=locale, display_name=display_name),
        color=discord.Color.blue()
    )
    embed.add_field(
        name=t("economy.check.current_points_name", locale=locale),
        value=t("economy.check.current_points_value", locale=locale, points=points),
        inline=True
    )

    # 显示今日免费抽奖状态
    free_draw_status = (
        t("economy.check.free_draw_incomplete", locale=locale)
        if free_draw_available
        else t("economy.check.free_draw_complete", locale=locale)
    )
    embed.add_field(
        name=t("economy.check.free_draw_name", locale=locale),
        value=free_draw_status,
        inline=True
    )

    # 显示付费抽奖次数
    remaining_draws = MAX_PAID_DRAWS_PER_DAY - paid_draws_today
    embed.add_field(
        name=t("economy.check.paid_draw_name", locale=locale),
        value=t(
            "economy.check.paid_draw_value",
            locale=locale,
            used=paid_draws_today,
            limit=MAX_PAID_DRAWS_PER_DAY,
            remaining=remaining_draws
        ),
        inline=True
    )

    await ctx.send(embed=embed)
