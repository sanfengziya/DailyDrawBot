import discord
import datetime
from src.db.database import get_connection, is_guild_subscribed
from src.utils.helpers import now_est, get_user_internal_id_with_guild_and_discord_id
from src.utils.i18n import get_guild_locale, get_reward_message, t

async def rewardinfo(ctx):
    """显示奖品信息"""
    from src.config.config import REWARD_SYSTEM

    try:
        locale = get_guild_locale(ctx.guild.id if ctx.guild else None)
        embed = discord.Embed(title=t("admin.rewardinfo.title", locale=locale), color=0x00ff00)

        # 按积分排序并显示
        sorted_rewards = sorted(REWARD_SYSTEM, key=lambda x: x["points"], reverse=True)

        reward_list = []
        for reward in sorted_rewards:
            reward_list.append(
                t(
                    "admin.rewardinfo.line",
                    locale=locale,
                    emoji=reward['emoji'],
                    points=reward['points'],
                    message=get_reward_message(reward, locale),
                    probability=reward['probability']
                )
            )

        embed.description = "\n".join(reward_list)
        embed.set_footer(text=t("admin.rewardinfo.footer", locale=locale, count=len(REWARD_SYSTEM)))

        await ctx.send(embed=embed)

    except Exception as e:
        print(f"获取奖品信息失败: {e}")
        locale = get_guild_locale(ctx.guild.id if ctx.guild else None)
        await ctx.send(t("common.unknown_error", locale=locale))

async def testdraw(ctx, times=100):
    """测试抽奖概率分布"""
    from src.utils.helpers import get_weighted_reward
    from src.config.config import REWARD_SYSTEM

    try:
        # 模拟抽奖，使用与实际抽奖相同的逻辑
        results = {}
        for _ in range(times):
            reward = get_weighted_reward()
            points = reward["points"]
            results[points] = results.get(points, 0) + 1

        # 生成结果
        locale = get_guild_locale(ctx.guild.id if ctx.guild else None)
        embed = discord.Embed(
            title=t("admin.testdraw.title", locale=locale, times=times),
            color=0x00ff00
        )

        # 按积分从高到低排序
        for points in sorted(results.keys(), reverse=True):
            count = results[points]
            percentage = (count / times) * 100

            # 查找对应的奖励信息
            reward_info = next((r for r in REWARD_SYSTEM if r["points"] == points), None)
            if reward_info:
                name = t(
                    "admin.testdraw.field_name",
                    locale=locale,
                    emoji=reward_info['emoji'],
                    points=points,
                    message=get_reward_message(reward_info, locale)
                )
                expected_prob = reward_info["probability"]
                value = t(
                    "admin.testdraw.field_value",
                    locale=locale,
                    count=count,
                    percentage=f"{percentage:.1f}",
                    expected=expected_prob
                )
                embed.add_field(
                    name=name,
                    value=value,
                    inline=True
                )

        await ctx.send(embed=embed)

    except Exception as e:
        print(f"测试抽奖失败: {e}")
        locale = get_guild_locale(ctx.guild.id if ctx.guild else None)
        await ctx.send(t("common.unknown_error", locale=locale))

async def check_subscription(ctx):
    """检查当前服务器的订阅状态"""
    supabase = get_connection()

    try:
        # 检查订阅状态
        is_active = is_guild_subscribed(ctx.guild.id)
        locale = get_guild_locale(ctx.guild.id if ctx.guild else None)

        # 获取详细信息
        result = supabase.table("guild_subscriptions").select("*").eq("guild_id", ctx.guild.id).execute()

        embed = discord.Embed(
            title=t("admin.subscription.title", locale=locale),
            color=discord.Color.green() if is_active else discord.Color.red()
        )

        embed.add_field(name=t("admin.subscription.server_id", locale=locale), value=str(ctx.guild.id), inline=True)
        embed.add_field(name=t("admin.subscription.server_name", locale=locale), value=ctx.guild.name, inline=True)

        if result.data:
            subscription = result.data[0]
            status_value = (
                t("admin.subscription.status_active", locale=locale)
                if subscription.get('is_active')
                else t("admin.subscription.status_inactive", locale=locale)
            )
            embed.add_field(name=t("admin.subscription.status", locale=locale), value=status_value, inline=False)

            if subscription.get('subscription_start'):
                embed.add_field(name=t("admin.subscription.start", locale=locale), value=subscription['subscription_start'], inline=True)
            if subscription.get('subscription_end'):
                embed.add_field(name=t("admin.subscription.end", locale=locale), value=subscription['subscription_end'], inline=True)
            if subscription.get('subscription_type'):
                embed.add_field(name=t("admin.subscription.type", locale=locale), value=subscription['subscription_type'], inline=True)
            if subscription.get('auto_renewal') is not None:
                auto_value = (
                    t("admin.subscription.auto_renew_yes", locale=locale)
                    if subscription['auto_renewal']
                    else t("admin.subscription.auto_renew_no", locale=locale)
                )
                embed.add_field(name=t("admin.subscription.auto_renew", locale=locale), value=auto_value, inline=True)
        else:
            embed.add_field(
                name=t("admin.subscription.status", locale=locale),
                value=t("admin.subscription.status_missing", locale=locale),
                inline=False
            )
            embed.add_field(
                name=t("admin.subscription.note_title", locale=locale),
                value=t("admin.subscription.note_missing", locale=locale),
                inline=False
            )

        await ctx.send(embed=embed)

    except Exception as e:
        print(f"检查订阅状态失败: {e}")
        locale = get_guild_locale(ctx.guild.id if ctx.guild else None)
        await ctx.send(t("admin.subscription.error", locale=locale, error=str(e)))
