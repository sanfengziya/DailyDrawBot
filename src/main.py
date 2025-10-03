#!/usr/bin/env python3
# 每日抽奖机器人 - 主入口点

import discord
from discord.ext import commands
import os

from src.config.config import TOKEN, PREFIX, YOUR_GUILD_ID
from src.commands import draw_commands, debug_commands, role_commands, quiz_commands, ranking_commands, help_commands, egg_commands, pet_commands, shop_commands, forge_commands

# 设置机器人
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f"已登录为 {bot.user}")

    # 注册斜杠命令（避免重复注册）
    setup_functions = [
        ('egg_commands', egg_commands.setup),
        ('pet_commands', pet_commands.setup),
        ('shop_commands', shop_commands.setup),
        ('forge_commands', forge_commands.setup),
        ('role_commands', role_commands.setup)
    ]

    for module_name, setup_func in setup_functions:
        try:
            # 检查命令是否已经注册，避免重复
            existing_commands = [cmd.name for cmd in bot.tree.get_commands()]
            setup_func(bot)
            print(f"已注册 {module_name} 斜杠命令")
        except Exception as e:
            # 如果是重复注册错误，跳过并继续
            if "already registered" in str(e):
                print(f"{module_name} 命令已存在，跳过重复注册")
            else:
                print(f"注册 {module_name} 斜杠命令时出错: {e}")

    try:
        synced = await bot.tree.sync()
        print(f"同步了 {len(synced)} 个斜杠命令")
    except Exception as e:
        print(f"同步斜杠命令时出错: {e}")

    # 启动喂食系统定时任务
    try:
        from src.utils.scheduler import start_feeding_scheduler
        await start_feeding_scheduler(bot)
        print("已启动喂食系统定时任务")
    except Exception as e:
        print(f"启动定时任务时出错: {e}")

@bot.event
async def on_guild_join(guild):
    if guild.id != YOUR_GUILD_ID:
        await guild.leave()

# 注册抽奖命令
@bot.command(name="draw")
async def draw(ctx):
    await draw_commands.draw(ctx)

@bot.command(name="check")
async def check(ctx, member: discord.Member = None):
    await draw_commands.check(ctx, member)

# 注册调试命令
@bot.command(name="debuguser")
@commands.has_permissions(administrator=True)
async def debug_user(ctx, member: discord.Member):
    await debug_commands.debug_user(ctx, member)

@bot.command(name="testupdate")
@commands.has_permissions(administrator=True)
async def test_update(ctx, member: discord.Member):
    await debug_commands.test_update(ctx, member)

@bot.command(name="checkdb")
@commands.has_permissions(administrator=True)
async def check_database(ctx):
    await debug_commands.check_database(ctx)

@bot.command(name="detailedebug")
@commands.has_permissions(administrator=True)
async def detailed_debug(ctx, member: discord.Member):
    await debug_commands.detailed_debug(ctx, member)

@bot.command(name="rewardinfo")
@commands.has_permissions(administrator=True)
async def rewardinfo(ctx):
    await debug_commands.rewardinfo(ctx)

@bot.command(name="testdraw")
@commands.has_permissions(administrator=True)
async def testdraw(ctx, times: int = 100):
    await debug_commands.testdraw(ctx, times)

# 添加喂食系统管理命令
@bot.command(name="resetsatiety")
@commands.has_permissions(administrator=True)
async def reset_satiety(ctx):
    """手动重置所有宠物饱食度"""
    try:
        from src.utils.scheduler import admin_reset_satiety
        await admin_reset_satiety()
        await ctx.send("✅ 已手动重置所有宠物饱食度！")
    except Exception as e:
        await ctx.send(f"❌ 重置饱食度时出错: {e}")

@bot.command(name="refreshshop")
@commands.has_permissions(administrator=True)
async def refresh_shop(ctx):
    """手动刷新杂货铺"""
    try:
        from src.utils.scheduler import admin_refresh_shop
        await admin_refresh_shop()
        await ctx.send("✅ 已手动刷新杂货铺商品！")
    except Exception as e:
        await ctx.send(f"❌ 刷新杂货铺时出错: {e}")

@bot.command(name="resetshop")
@commands.has_permissions(administrator=True)
async def reset_shop(ctx):
    """重置杂货铺商品（refreshshop的别名）"""
    try:
        from src.utils.scheduler import admin_refresh_shop
        await admin_refresh_shop()
        await ctx.send("🏪 已重置杂货铺商品！今日商品已更新。")
    except Exception as e:
        await ctx.send(f"❌ 重置杂货铺时出错: {e}")

@bot.command(name="testshop")
@commands.has_permissions(administrator=True)
async def test_shop(ctx):
    """测试杂货铺刷新功能（调试用）"""
    try:
        from src.utils.feeding_system import FoodShopManager

        # 运行测试
        test_result = FoodShopManager.test_shop_refresh()

        if test_result:
            await ctx.send("✅ 杂货铺刷新功能测试通过！所有功能正常。")
        else:
            await ctx.send("⚠️ 杂货铺刷新功能测试未完全通过，请检查日志。")

    except Exception as e:
        await ctx.send(f"❌ 测试杂货铺功能时出错: {e}")

@bot.command(name="schedulerstatus")
@commands.has_permissions(administrator=True)
async def scheduler_status(ctx):
    """查看定时任务状态"""
    try:
        from src.utils.scheduler import get_scheduler, get_next_reset_times
        scheduler = get_scheduler()
        reset_times = get_next_reset_times()

        status = "🟢 运行中" if scheduler.running else "🔴 已停止"

        embed = discord.Embed(
            title="🕐 定时任务状态",
            description=f"**状态：** {status}",
            color=discord.Color.green() if scheduler.running else discord.Color.red()
        )

        embed.add_field(
            name="⏰ 下次饱食度重置",
            value=reset_times['next_satiety_reset'].strftime('%Y-%m-%d %H:%M EST'),
            inline=False
        )

        embed.add_field(
            name="🏪 下次杂货铺刷新",
            value=reset_times['next_shop_refresh'].strftime('%Y-%m-%d %H:%M EST'),
            inline=False
        )

        embed.add_field(
            name="🌍 当前美东时间",
            value=reset_times['current_est_time'].strftime('%Y-%m-%d %H:%M:%S EST'),
            inline=False
        )

        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ 获取定时任务状态时出错: {e}")

# 注册角色和积分管理命令
@bot.command(name="addtag")
@commands.has_permissions(administrator=True)
async def addtag(ctx, price: int, role: discord.Role):
    await role_commands.addtag(ctx, price, role)

@bot.command(name="removetag")
@commands.has_permissions(administrator=True)
async def removetag(ctx, role: discord.Role):
    await role_commands.removetag(ctx, role)

@bot.command(name="updatetagprice")
@commands.has_permissions(administrator=True)
async def updatetagprice(ctx, role: discord.Role, new_price: int):
    await role_commands.updatetagprice(ctx, role, new_price)

@bot.command(name="listtags")
@commands.has_permissions(administrator=True)
async def listtags(ctx):
    await role_commands.listtags(ctx)

@bot.command(name="giftpoints")
async def giftpoints(ctx, member: discord.Member, amount: int):
    await role_commands.giftpoints(ctx, member, amount)

@bot.command(name="givepoints")
@commands.has_permissions(administrator=True)
async def givepoints(ctx, member: discord.Member, amount: int):
    await role_commands.givepoints(ctx, member, amount)

@bot.command(name="setpoints")
@commands.has_permissions(administrator=True)
async def setpoints(ctx, member: discord.Member, points: int):
    await role_commands.setpoints(ctx, member, points)

# 注册答题命令
@bot.command(name="quizlist")
async def quizlist(ctx):
    await quiz_commands.quizlist(ctx)

@bot.command(name="importquiz")
@commands.has_permissions(administrator=True)
async def importquiz(ctx):
    await quiz_commands.importquiz(ctx)

@bot.command(name="deletequiz")
@commands.has_permissions(administrator=True)
async def deletequiz(ctx, category: str):
    await quiz_commands.deletequiz(ctx, category)

@bot.command(name="quiz")
@commands.has_permissions(administrator=True)
async def quiz(ctx, category: str, number: int):
    await quiz_commands.quiz(ctx, category, number)

# 注册排行榜命令
@bot.command(name="ranking")
async def ranking(ctx):
    await ranking_commands.ranking(ctx)

# 注册帮助命令
@bot.tree.command(name="help", description="显示所有可用命令的帮助信息")
async def help_command(interaction: discord.Interaction):
    await help_commands.help_command(interaction)

def main():
    # 运行机器人
    bot.run(TOKEN)

if __name__ == "__main__":
    main()