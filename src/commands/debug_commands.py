import discord
import datetime
from src.db.database import get_connection, is_guild_subscribed
from src.utils.helpers import now_est, get_user_internal_id_with_guild_and_discord_id

async def rewardinfo(ctx):
    """显示奖品信息"""
    from src.config.config import REWARD_SYSTEM

    try:
        embed = discord.Embed(title="🎁 奖品信息", color=0x00ff00)

        # 按积分排序并显示
        sorted_rewards = sorted(REWARD_SYSTEM, key=lambda x: x["points"], reverse=True)

        reward_list = []
        for reward in sorted_rewards:
            reward_list.append(
                f"{reward['emoji']} **{reward['points']}分** - {reward['message']} ({reward['probability']}%)"
            )

        embed.description = "\n".join(reward_list)
        embed.set_footer(text=f"共 {len(REWARD_SYSTEM)} 种奖励")

        await ctx.send(embed=embed)

    except Exception as e:
        print(f"获取奖品信息失败: {e}")
        await ctx.send("获取奖品信息失败，请稍后重试。")

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
        embed = discord.Embed(title=f"🎲 抽奖测试结果 ({times}次)", color=0x00ff00)

        # 按积分从高到低排序
        for points in sorted(results.keys(), reverse=True):
            count = results[points]
            percentage = (count / times) * 100

            # 查找对应的奖励信息
            reward_info = next((r for r in REWARD_SYSTEM if r["points"] == points), None)
            if reward_info:
                name = f"{reward_info['emoji']} {points}分 ({reward_info['message']})"
                expected_prob = reward_info["probability"]
                embed.add_field(
                    name=name,
                    value=f"实际: {count}次 ({percentage:.1f}%)\n预期: {expected_prob}%",
                    inline=True
                )

        await ctx.send(embed=embed)

    except Exception as e:
        print(f"测试抽奖失败: {e}")
        await ctx.send("测试抽奖失败，请稍后重试。")

async def check_subscription(ctx):
    """检查当前服务器的订阅状态"""
    supabase = get_connection()

    try:
        # 检查订阅状态
        is_active = is_guild_subscribed(ctx.guild.id)

        # 获取详细信息
        result = supabase.table("guild_subscriptions").select("*").eq("guild_id", ctx.guild.id).execute()

        embed = discord.Embed(
            title=f"📋 服务器订阅状态",
            color=discord.Color.green() if is_active else discord.Color.red()
        )

        embed.add_field(name="服务器ID", value=str(ctx.guild.id), inline=True)
        embed.add_field(name="服务器名称", value=ctx.guild.name, inline=True)

        if result.data:
            subscription = result.data[0]
            embed.add_field(name="订阅状态", value="✅ 已订阅" if subscription.get('is_active') else "❌ 未订阅", inline=False)

            if subscription.get('subscription_start'):
                embed.add_field(name="订阅开始", value=subscription['subscription_start'], inline=True)
            if subscription.get('subscription_end'):
                embed.add_field(name="订阅结束", value=subscription['subscription_end'], inline=True)
            if subscription.get('subscription_type'):
                embed.add_field(name="订阅类型", value=subscription['subscription_type'], inline=True)
            if subscription.get('auto_renewal') is not None:
                embed.add_field(name="自动续费", value="是" if subscription['auto_renewal'] else "否", inline=True)
        else:
            embed.add_field(name="订阅状态", value="❌ 未找到订阅记录", inline=False)
            embed.add_field(name="说明", value="此服务器未在订阅列表中", inline=False)

        await ctx.send(embed=embed)

    except Exception as e:
        print(f"检查订阅状态失败: {e}")
        await ctx.send(f"❌ 检查订阅状态失败: {e}")