#!/usr/bin/env python3
# 每日抽奖机器人 - 主入口点

import discord
from discord.ext import commands
import os

from src.config.config import TOKEN, PREFIX
from src.commands import draw_commands, debug_commands, role_commands, quiz_commands, ranking_commands, help_commands, egg_commands, pet_commands, shop_commands, forge_commands
from src.db.database import is_guild_subscribed

# 设置机器人
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

@bot.check
async def check_guild_subscription(ctx):
    """
    全局检查：验证服务器是否有有效订阅
    如果没有订阅或订阅已失效，拒绝执行命令
    """
    # 检查订阅状态的命令不受限制
    if ctx.command and ctx.command.name == 'checksubscription':
        return True

    # 如果是DM（私信）中的命令，直接拒绝
    if ctx.guild is None:
        await ctx.send("❌ 此机器人只能在服务器中使用")
        return False

    # 检查服务器订阅状态
    if not is_guild_subscribed(ctx.guild.id):
        await ctx.send("❌ 此服务器未订阅或订阅已失效，无法使用机器人功能")
        return False

    return True

async def check_interaction_guild_subscription(interaction: discord.Interaction) -> bool:
    """
    检查交互命令的服务器订阅状态
    """
    # 如果不在服务器中，拒绝
    if interaction.guild is None:
        await interaction.response.send_message("❌ 此机器人只能在服务器中使用", ephemeral=True)
        return False

    # 检查服务器订阅状态
    if not is_guild_subscribed(interaction.guild.id):
        await interaction.response.send_message("❌ 此服务器未订阅或订阅已失效，无法使用机器人功能", ephemeral=True)
        return False

    return True

# 为所有斜杠命令添加全局检查
bot.tree.interaction_check = check_interaction_guild_subscription

@bot.event
async def on_command_error(ctx, error):
    """
    处理命令错误，特别是订阅检查失败的情况
    """
    if isinstance(error, commands.CheckFailure):
        # 订阅检查已经在check函数中发送了消息，这里不需要额外处理
        pass
    elif isinstance(error, commands.MemberNotFound):
        # 处理成员未找到错误
        await ctx.send(f"❌ 找不到成员：{error.argument}\n请使用 @mention 提及用户，或确保输入正确的用户名。")
    else:
        # 处理其他错误
        print(f"命令错误: {error}")

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


# 注册抽奖命令
@bot.command(name="draw")
async def draw(ctx):
    await draw_commands.draw(ctx)

@bot.command(name="check")
async def check(ctx, member: discord.Member = None):
    await draw_commands.check(ctx, member)

# 注册调试命令
@bot.command(name="rewardinfo")
@commands.has_permissions(administrator=True)
async def rewardinfo(ctx):
    await debug_commands.rewardinfo(ctx)

@bot.command(name="testdraw")
@commands.has_permissions(administrator=True)
async def testdraw(ctx, times: int = 100):
    await debug_commands.testdraw(ctx, times)

@bot.command(name="checksubscription")
@commands.has_permissions(administrator=True)
async def check_subscription(ctx):
    await debug_commands.check_subscription(ctx)

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