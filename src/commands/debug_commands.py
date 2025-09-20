import discord
import datetime
from src.db.database import get_connection
from src.utils.helpers import now_est, get_user_internal_id

async def debug_user(ctx, member):
    """调试用户的付费抽奖信息"""
    user_internal_id = get_user_internal_id(ctx.guild.id, member.id)
    if user_internal_id is None:
        await ctx.send(f"❌ 用户 {member.mention} 不存在于数据库中。")
        return
    
    supabase = get_connection()
    
    try:
        result = supabase.table("users").select("points, last_draw_date, paid_draws_today, last_paid_draw_date").eq("id", user_internal_id).execute()
        
        if result.data:
            user_data = result.data[0]
            points = user_data["points"]
            last_draw = user_data["last_draw_date"]
            paid_draws_today = user_data["paid_draws_today"]
            last_paid_draw_date = user_data["last_paid_draw_date"]
            today = now_est().date()
            
            embed = discord.Embed(
                title=f"🔍 {member.display_name} 的调试信息",
                color=discord.Color.blue()
            )
            embed.add_field(name="用户ID", value=str(user_internal_id), inline=True)
            embed.add_field(name="积分", value=str(points), inline=True)
            embed.add_field(name="最后抽奖日期", value=str(last_draw), inline=True)
            embed.add_field(name="付费抽奖次数", value=str(paid_draws_today), inline=True)
            embed.add_field(name="最后付费抽奖日期", value=str(last_paid_draw_date), inline=True)
            embed.add_field(name="今天日期", value=str(today), inline=True)
            embed.add_field(name="是否新的一天", value=str(last_paid_draw_date != today), inline=True)
            
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ 用户 {member.mention} 不存在于数据库中。")
            
    except Exception as e:
        print(f"调试用户信息失败: {e}")
        await ctx.send("调试用户信息失败，请稍后重试。")

async def test_update(ctx, member):
    """测试付费抽奖的数据库更新"""
    user_internal_id = get_user_internal_id(ctx.guild.id, member.id)
    if user_internal_id is None:
        await ctx.send(f"❌ 用户 {member.mention} 不存在于数据库中。")
        return
    
    today = now_est().date()
    
    supabase = get_connection()
    
    try:
        # 首先，获取当前值
        result = supabase.table("users").select("points, last_draw_date, paid_draws_today, last_paid_draw_date").eq("id", user_internal_id).execute()
        
        if result.data:
            user_data = result.data[0]
            points = user_data["points"]
            last_draw = user_data["last_draw_date"]
            paid_draws_today = user_data["paid_draws_today"]
            last_paid_draw_date = user_data["last_paid_draw_date"]
            
            await ctx.send(f"🔍 更新前的数据：\n积分: {points}\n付费抽奖次数: {paid_draws_today}\n最后付费抽奖日期: {last_paid_draw_date}")
            
            # 测试更新
            new_paid_draws = paid_draws_today + 1
            supabase.table("users").update({
                "last_draw_date": str(today),
                "paid_draws_today": new_paid_draws,
                "last_paid_draw_date": str(today)
            }).eq("id", user_internal_id).execute()
            
            # 检查更新是否成功
            result_after = supabase.table("users").select("points, last_draw_date, paid_draws_today, last_paid_draw_date").eq("id", user_internal_id).execute()
            
            if result_after.data:
                user_data_after = result_after.data[0]
                points_after = user_data_after["points"]
                last_draw_after = user_data_after["last_draw_date"]
                paid_draws_after = user_data_after["paid_draws_today"]
                last_paid_draw_date_after = user_data_after["last_paid_draw_date"]
                
                await ctx.send(f"✅ 更新后的数据：\n积分: {points_after}\n付费抽奖次数: {paid_draws_after}\n最后付费抽奖日期: {last_paid_draw_date_after}")
            else:
                await ctx.send("❌ 更新后无法读取数据")
        else:
            await ctx.send(f"❌ 用户 {member.mention} 不存在于数据库中。")
            
    except Exception as e:
        print(f"测试更新失败: {e}")
        await ctx.send("测试更新失败，请稍后重试。")

async def check_database(ctx):
    """检查数据库连接和表结构"""
    try:
        supabase = get_connection()
        
        embed = discord.Embed(title="数据库状态检查", color=0x00ff00)
        embed.add_field(name="连接状态", value="✅ 成功", inline=False)
        
        # 检查用户数量
        users_result = supabase.table("users").select("*", count="exact").execute()
        user_count = users_result.count
        embed.add_field(name="用户数量", value=str(user_count), inline=True)
        
        # 检查奖品数量
        rewards_result = supabase.table("rewards").select("*", count="exact").execute()
        reward_count = rewards_result.count
        embed.add_field(name="奖品数量", value=str(reward_count), inline=True)
        
        # 检查其他表
        try:
            quiz_result = supabase.table("quiz").select("*", count="exact").execute()
            quiz_count = quiz_result.count
            embed.add_field(name="题目数量", value=str(quiz_count), inline=True)
        except:
            embed.add_field(name="题目数量", value="无法获取", inline=True)
        
        try:
            roles_result = supabase.table("roles").select("*", count="exact").execute()
            roles_count = roles_result.count
            embed.add_field(name="角色数量", value=str(roles_count), inline=True)
        except:
            embed.add_field(name="角色数量", value="无法获取", inline=True)
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        embed = discord.Embed(title="数据库状态检查", color=0xff0000)
        embed.add_field(name="连接状态", value=f"❌ 失败: {str(e)}", inline=False)
        await ctx.send(embed=embed)

async def detailed_debug(ctx, member):
    """详细调试用户数据"""
    user_internal_id = get_user_internal_id(ctx.guild.id, member.id)
    if user_internal_id is None:
        await ctx.send(f"❌ 用户 {member.mention} 不存在于数据库中。")
        return
    
    supabase = get_connection()
    
    try:
        # 获取用户的所有数据
        result = supabase.table("users").select("*").eq("id", user_internal_id).execute()
        
        if result.data:
            user_data = result.data[0]
            
            embed = discord.Embed(
                title=f"🔍 详细调试信息 - {member.display_name}",
                color=discord.Color.blue()
            )
            
            # 显示所有字段
            for column, value in user_data.items():
                display_value = str(value) if value is not None else "NULL"
                embed.add_field(name=column, value=display_value, inline=True)
            
            # 添加时间信息
            now = now_est()
            embed.add_field(name="当前时间", value=now.strftime("%Y-%m-%d %H:%M:%S"), inline=False)
            embed.add_field(name="当前日期", value=str(now.date()), inline=True)
            
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ 用户 {member.mention} 不存在于数据库中。")
            
    except Exception as e:
        print(f"详细调试失败: {e}")
        await ctx.send("详细调试失败，请稍后重试。")

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