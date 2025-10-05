import discord
import datetime
from src.db.database import get_connection, is_guild_subscribed
from src.utils.helpers import now_est, get_user_internal_id_with_guild_and_discord_id

async def rewardinfo(ctx):
    """显示奖品信息"""
    supabase = get_connection()
    
    try:
        # 获取所有奖品信息
        result = supabase.table("rewards").select("name, rarity, probability").order("rarity", "name").execute()
        
        if not result.data:
            await ctx.send("❌ 没有找到任何奖品信息。")
            return
        
        # 按稀有度分组
        rarity_groups = {}
        for reward in result.data:
            name = reward["name"]
            rarity = reward["rarity"]
            probability = reward["probability"]
            
            if rarity not in rarity_groups:
                rarity_groups[rarity] = []
            rarity_groups[rarity].append((name, probability))
        
        embed = discord.Embed(title="🎁 奖品信息", color=0x00ff00)
        
        for rarity in sorted(rarity_groups.keys()):
            items = rarity_groups[rarity]
            item_list = "\n".join([f"{name} ({probability}%)" for name, probability in items])
            embed.add_field(name=f"{rarity}级奖品", value=item_list, inline=False)
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        print(f"获取奖品信息失败: {e}")
        await ctx.send("获取奖品信息失败，请稍后重试。")

async def testdraw(ctx, times=100):
    """测试抽奖概率分布"""
    import random
    supabase = get_connection()
    
    try:
        # 获取所有奖品及其概率
        result = supabase.table("rewards").select("name, probability").execute()
        
        if not result.data:
            await ctx.send("❌ 没有找到任何奖品。")
            return
        
        rewards = [(reward["name"], reward["probability"]) for reward in result.data]
        
        # 模拟抽奖
        results = {}
        for _ in range(times):
            # 简单的概率模拟
            rand = random.random() * 100
            cumulative = 0
            for name, probability in rewards:
                cumulative += probability
                if rand <= cumulative:
                    results[name] = results.get(name, 0) + 1
                    break
        
        # 生成结果
        embed = discord.Embed(title=f"🎲 抽奖测试结果 ({times}次)", color=0x00ff00)
        
        for name, count in sorted(results.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / times) * 100
            embed.add_field(name=name, value=f"{count}次 ({percentage:.1f}%)", inline=True)
        
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