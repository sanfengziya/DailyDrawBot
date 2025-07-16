#!/usr/bin/env python3
# Daily Draw Bot - Main Entry Point

import discord
from discord.ext import commands
import os

from src.config.config import TOKEN, PREFIX, YOUR_GUILD_ID
from src.db.database import init_db
from src.commands import draw_commands, debug_commands, role_commands, quiz_commands, ranking_commands, help_commands

# 设置机器人
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f"已登录为 {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"同步了 {len(synced)} 个斜杠命令")
    except Exception as e:
        print(f"同步斜杠命令时出错: {e}")

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

@bot.command(name="resetdraw")
@commands.has_permissions(administrator=True)
async def reset_draw(ctx, member: discord.Member):
    await draw_commands.reset_draw(ctx, member)

@bot.command(name="resetall")
@commands.has_permissions(administrator=True)
async def reset_all(ctx, confirm: str = None):
    await draw_commands.reset_all(ctx, confirm)

@bot.command(name="fixdb")
@commands.has_permissions(administrator=True)
async def fix_database(ctx):
    await draw_commands.fix_database(ctx)

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

# 注册角色和积分管理命令
@bot.command(name="addtag")
@commands.has_permissions(administrator=True)
async def addtag(ctx, price: int, role: discord.Role):
    await role_commands.addtag(ctx, price, role)

@bot.command(name="roleshop")
async def roleshop(ctx):
    await role_commands.roleshop(ctx)

@bot.command(name="buytag")
async def buytag(ctx, *, role_name: str):
    await role_commands.buytag(ctx, role_name)

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

# 初始化数据库
init_db()

def main():
    # 运行机器人
    bot.run(TOKEN)

if __name__ == "__main__":
    main() 