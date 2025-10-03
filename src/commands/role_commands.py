import discord
import asyncio
from src.db.database import get_connection
from src.utils.ui import RolePageView
from src.utils.helpers import get_user_internal_id, get_user_internal_id_with_guild_and_discord_id
from src.utils.cache import UserCache

async def addtag(ctx, price, role):
    supabase = get_connection()
    
    try:
        # 使用upsert来实现INSERT ... ON DUPLICATE KEY UPDATE的功能
        supabase.table("tags").upsert({
            "role_id": str(role.id),
            "price": price
        }).execute()
        
        await ctx.send(f"已添加身份组 `{role.name}`，价格为 {price} 分。")
    except Exception as e:
        print(f"添加身份组失败: {e}")
        await ctx.send("添加身份组失败，请稍后重试。")

async def roleshop(ctx):
    supabase = get_connection()
    
    try:
        result = supabase.table("tags").select("role_id, price").order("price").execute()
        rows = [(row["role_id"], row["price"]) for row in result.data]

        if not rows:
            await ctx.send("当前没有可购买的身份组。")
            return

        view = RolePageView(ctx, rows)
        await view.send_initial()
    except Exception as e:
        print(f"获取身份组列表失败: {e}")
        await ctx.send("获取身份组列表失败，请稍后重试。")

async def buytag(ctx, role_name):
    guild = ctx.guild
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        await ctx.send("未找到该身份组。")
        return

    supabase = get_connection()
    
    try:
        # 获取身份组价格
        tag_result = supabase.table("tags").select("price").eq("role_id", str(role.id)).execute()
        if not tag_result.data:
            await ctx.send("该身份组不可购买。")
            return
        price = tag_result.data[0]["price"]

        # 获取用户内部ID和积分
        user_internal_id = await UserCache.get_user_id(ctx.guild.id, ctx.author.id)
        if not user_internal_id:
            await ctx.send("用户信息获取失败，请稍后重试。")
            return

        current_points = await UserCache.get_points(ctx.guild.id, ctx.author.id)
        if current_points < price:
            await ctx.send("你的分数不足。")
            return

        await ctx.send(f"你确定要购买 `{role.name}` 吗？请在 10 秒内回复 `Y`。")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            reply = await ctx.bot.wait_for("message", check=check, timeout=10.0)
            if reply.content.upper() != "Y":
                await ctx.send("已取消购买。")
                return
        except:
            await ctx.send("超时，已取消购买。")
            return

        # 扣除积分
        await UserCache.update_points(ctx.guild.id, ctx.author.id, user_internal_id, -price)

        await ctx.author.add_roles(role)
        await ctx.send(f"✅ 你已购买并获得 `{role.name}` 身份组。")
        
    except Exception as e:
        print(f"购买身份组失败: {e}")
        await ctx.send("购买身份组失败，请稍后重试。")

async def giftpoints(ctx, member: discord.Member, amount: int):
    """允许用户将自己的积分赠送给其他用户"""
    # 检查是否赠送给自己
    if member.id == ctx.author.id:
        await ctx.send("❌ 你不能给自己赠送积分哦！")
        return
        
    # 检查赠送数量是否为正数
    if amount <= 0:
        await ctx.send("❌ 赠送的积分必须是正数！")
        return
        
    supabase = get_connection()
    
    try:
        # 获取赠送者内部ID和积分
        sender_internal_id = await UserCache.get_user_id(ctx.guild.id, ctx.author.id)
        if not sender_internal_id:
            await ctx.send("❌ 用户信息获取失败，请稍后重试。")
            return

        # 检查赠送者是否有足够积分
        sender_points = await UserCache.get_points(ctx.guild.id, ctx.author.id)

        if sender_points < amount:
            await ctx.send(f"❌ 你的积分不足！当前积分: {sender_points}")
            return
    
        # 确认赠送
        embed = discord.Embed(
            title="🎁 积分赠送确认",
            description=f"你确定要赠送 **{amount}** 积分给 {member.mention} 吗？\n\n发送 `Y` 继续，或任意其他内容取消。",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        
        try:
            reply = await ctx.bot.wait_for("message", check=check, timeout=15.0)
            if reply.content.upper() != "Y":
                await ctx.send("❌ 已取消赠送。")
                return
        except asyncio.TimeoutError:
            await ctx.send("⏰ 确认超时，已取消赠送。")
            return
        
        # 获取接收者内部ID
        receiver_internal_id = await UserCache.get_user_id(ctx.guild.id, member.id)
        if not receiver_internal_id:
            await ctx.send("❌ 接收者信息获取失败，请稍后重试。")
            return

        # 执行积分转移
        await UserCache.update_points(ctx.guild.id, ctx.author.id, sender_internal_id, -amount)
        await UserCache.update_points(ctx.guild.id, member.id, receiver_internal_id, amount)
        
        # 发送成功消息
        embed = discord.Embed(
            title="✅ 积分赠送成功",
            description=f"{ctx.author.mention} 成功赠送了 **{amount}** 积分给 {member.mention}！",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
    except Exception as e:
        print(f"积分赠送失败: {e}")
        await ctx.send("积分赠送失败，请稍后重试。")

async def givepoints(ctx, member: discord.Member, amount: int):
    try:
        # 获取用户内部ID
        user_internal_id = await UserCache.get_user_id(ctx.guild.id, member.id)
        if not user_internal_id:
            await ctx.send("用户信息获取失败，请稍后重试。")
            return

        # 增加用户积分
        await UserCache.update_points(ctx.guild.id, member.id, user_internal_id, amount)

        await ctx.send(f"{ctx.author.mention} 已给予 {member.mention} {amount} 分。")

    except Exception as e:
        print(f"给予积分失败: {e}")
        await ctx.send("给予积分失败，请稍后重试。")

async def setpoints(ctx, member: discord.Member, points: int):
    """将成员的积分精确设置为指定值。"""
    try:
        # 获取用户内部ID
        user_internal_id = await UserCache.get_user_id(ctx.guild.id, member.id)
        if not user_internal_id:
            await ctx.send("用户信息获取失败，请稍后重试。")
            return

        # 获取当前积分并计算差值
        current_points = await UserCache.get_points(ctx.guild.id, member.id)
        delta = points - current_points

        # 使用差值更新积分
        await UserCache.update_points(ctx.guild.id, member.id, user_internal_id, delta)

        await ctx.send(f"{ctx.author.mention} 已将 {member.mention} 的分数设为 {points} 分。")

    except Exception as e:
        print(f"设置积分失败: {e}")
        await ctx.send("设置积分失败，请稍后重试。")