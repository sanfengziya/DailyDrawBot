#!/usr/bin/env python3
# 每日抽奖机器人 - 主入口点

import discord
from discord.ext import commands
import os

from src.config.config import TOKEN, PREFIX
from src.commands.economy import draw, check, giftpoints, givepoints, setpoints
from src.commands.pets import eggs as egg_commands, management as pet_commands, forge as forge_commands
from src.commands.shop import roles as shop_roles, items as shop_commands
from src.commands.games import quiz as quiz_commands, blackjack as blackjack_commands, texas_holdem as texas_commands
from src.commands.rankings import leaderboard as ranking_commands
from src.commands.system import help_module as help_commands, admin as debug_commands, language as language_commands
from src.db.database import is_guild_subscribed
from src.utils.i18n import get_guild_locale, t

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
    # 检查订阅状态与语言设置命令不受限制
    if ctx.command and ctx.command.name in {'checksubscription', 'setlanguage'}:
        return True

    # 如果是DM（私信）中的命令，直接拒绝
    if ctx.guild is None:
        await ctx.send(t("common.guild_only"))
        return False

    # 检查服务器订阅状态
    locale = get_guild_locale(ctx.guild.id)
    if not is_guild_subscribed(ctx.guild.id):
        await ctx.send(t("common.subscription_required", locale=locale))
        return False

    return True

async def check_interaction_guild_subscription(interaction: discord.Interaction) -> bool:
    """
    检查交互命令的服务器订阅状态
    """
    # 允许设置语言命令绕过订阅检查
    command_name = None
    if interaction.command:
        command_name = getattr(interaction.command, "qualified_name", interaction.command.name)

    if interaction.guild is None:
        await interaction.response.send_message(t("common.guild_only"), ephemeral=True)
        return False

    # 检查服务器订阅状态
    if command_name in {"settings language"}:
        return True

    if not is_guild_subscribed(interaction.guild.id):
        locale = get_guild_locale(interaction.guild.id)
        await interaction.response.send_message(t("common.subscription_required", locale=locale), ephemeral=True)
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
        ('role_commands', shop_roles.setup),
        ('blackjack_commands', blackjack_commands.setup),
        ('texas_commands', texas_commands.setup),
        ('ranking_commands', ranking_commands.setup),
        ('language_commands', language_commands.setup)
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
async def draw_command(ctx, count: int = 1):
    await draw(ctx, count)

@bot.command(name="check")
async def check_command(ctx, member: discord.Member = None):
    await check(ctx, member)

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

# 注册角色和积分管理命令
@bot.command(name="addtag")
@commands.has_permissions(administrator=True)
async def addtag(ctx, price: int, role: discord.Role):
    await shop_roles.addtag(ctx, price, role)

@bot.command(name="removetag")
@commands.has_permissions(administrator=True)
async def removetag(ctx, role: discord.Role):
    await shop_roles.removetag(ctx, role)

@bot.command(name="updatetagprice")
@commands.has_permissions(administrator=True)
async def updatetagprice(ctx, role: discord.Role, new_price: int):
    await shop_roles.updatetagprice(ctx, role, new_price)

@bot.command(name="listtags")
@commands.has_permissions(administrator=True)
async def listtags(ctx):
    await shop_roles.listtags(ctx)

@bot.command(name="giftpoints")
async def giftpoints_command(ctx, member: discord.Member, amount: int):
    await giftpoints(ctx, member, amount)

@bot.command(name="givepoints")
@commands.has_permissions(administrator=True)
async def givepoints_command(ctx, member: discord.Member, amount: int):
    await givepoints(ctx, member, amount)

@bot.command(name="setpoints")
@commands.has_permissions(administrator=True)
async def setpoints_command(ctx, member: discord.Member, points: int):
    await setpoints(ctx, member, points)

# 注册答题命令
@bot.command(name="quizlist")
async def quizlist(ctx, language: str = "all"):
    await quiz_commands.quizlist(ctx, language)

@bot.command(name="quiz")
@commands.has_permissions(administrator=True)
async def quiz(ctx, category: str, number: int):
    await quiz_commands.quiz(ctx, category, number)

# 排行榜命令已改为斜杠命令 /leaderboard


@bot.command(name="setlanguage")
async def setlanguage_command(ctx, locale: str = None):
    await language_commands.set_language_prefix(ctx, locale)

# 注册帮助命令
@bot.tree.command(name="help", description="Display help information for all available commands")
async def help_command(interaction: discord.Interaction):
    await help_commands.help_command(interaction)

def main():
    # 运行机器人
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
