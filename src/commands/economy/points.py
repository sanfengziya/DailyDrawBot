import discord
import asyncio
from src.utils.cache import UserCache
from src.utils.i18n import get_guild_locale, t

async def giftpoints(ctx, member: discord.Member, amount: int):
    """允许用户将自己的积分赠送给其他用户"""
    locale = get_guild_locale(ctx.guild.id)
    # 检查是否赠送给自己
    if member.id == ctx.author.id:
        await ctx.send(t("economy.gift.self_transfer", locale=locale))
        return

    # 检查赠送数量是否为正数
    if amount <= 0:
        await ctx.send(t("economy.gift.positive_only", locale=locale))
        return

    try:
        # 获取赠送者内部ID和积分
        sender_internal_id = await UserCache.get_user_id(ctx.guild.id, ctx.author.id)
        if not sender_internal_id:
            await ctx.send(t("economy.gift.sender_missing", locale=locale))
            return

        # 检查赠送者是否有足够积分
        sender_points = await UserCache.get_points(ctx.guild.id, ctx.author.id)

        if sender_points < amount:
            await ctx.send(t("economy.gift.insufficient", locale=locale, points=sender_points))
            return

        # 确认赠送
        embed = discord.Embed(
            title=t("economy.gift.confirm_title", locale=locale),
            description=t("economy.gift.confirm_desc", locale=locale, amount=amount, mention=member.mention),
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            reply = await ctx.bot.wait_for("message", check=check, timeout=15.0)
            if reply.content.upper() != "Y":
                await ctx.send(t("economy.gift.cancelled", locale=locale))
                return
        except asyncio.TimeoutError:
            await ctx.send(t("economy.gift.timeout", locale=locale))
            return

        # 获取接收者内部ID
        receiver_internal_id = await UserCache.get_user_id(ctx.guild.id, member.id)
        if not receiver_internal_id:
            await ctx.send(t("economy.gift.receiver_missing", locale=locale))
            return

        # 执行积分转移
        await UserCache.update_points(ctx.guild.id, ctx.author.id, sender_internal_id, -amount)
        await UserCache.update_points(ctx.guild.id, member.id, receiver_internal_id, amount)

        # 发送成功消息
        embed = discord.Embed(
            title=t("economy.gift.success_title", locale=locale),
            description=t(
                "economy.gift.success_desc",
                locale=locale,
                sender=ctx.author.mention,
                amount=amount,
                receiver=member.mention
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    except Exception as e:
        print(f"积分赠送失败: {e}")
        await ctx.send(t("economy.gift.failure", locale=locale))

async def givepoints(ctx, member: discord.Member, amount: int):
    """管理员命令：给予用户积分"""
    locale = get_guild_locale(ctx.guild.id)
    try:
        # 获取用户内部ID
        user_internal_id = await UserCache.get_user_id(ctx.guild.id, member.id)
        if not user_internal_id:
            await ctx.send(t("economy.give.user_missing", locale=locale))
            return

        # 增加用户积分
        await UserCache.update_points(ctx.guild.id, member.id, user_internal_id, amount)

        await ctx.send(t("economy.give.success", locale=locale, staff=ctx.author.mention, member=member.mention, amount=amount))

    except Exception as e:
        print(f"给予积分失败: {e}")
        await ctx.send(t("economy.give.failure", locale=locale))

async def setpoints(ctx, member: discord.Member, points: int):
    """管理员命令：将成员的积分精确设置为指定值。"""
    locale = get_guild_locale(ctx.guild.id)
    try:
        # 获取用户内部ID
        user_internal_id = await UserCache.get_user_id(ctx.guild.id, member.id)
        if not user_internal_id:
            await ctx.send(t("economy.set.user_missing", locale=locale))
            return

        # 获取当前积分并计算差值
        current_points = await UserCache.get_points(ctx.guild.id, member.id)
        delta = points - current_points

        # 使用差值更新积分
        await UserCache.update_points(ctx.guild.id, member.id, user_internal_id, delta)

        await ctx.send(t("economy.set.success", locale=locale, staff=ctx.author.mention, member=member.mention, points=points))

    except Exception as e:
        print(f"设置积分失败: {e}")
        await ctx.send(t("economy.set.failure", locale=locale))
