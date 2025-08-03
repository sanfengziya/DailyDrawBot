import discord
from discord import app_commands
from src.config.config import MAX_PAID_DRAWS_PER_DAY
from src.utils.helpers import get_guild_language
from src.config.languages import get_text

async def help_command(interaction: discord.Interaction):
    """Show help information for all commands"""
    # 获取服务器当前语言
    current_lang = get_guild_language(interaction.guild_id)
    
    # 根据当前语言创建帮助嵌入
    if current_lang == "en":
        embed = create_english_help_embed(interaction)
    else:
        embed = create_chinese_help_embed(interaction)
    
    await interaction.response.send_message(embed=embed)

def create_english_help_embed(interaction: discord.Interaction):
    """Create help embed in English"""
    embed = discord.Embed(
        title="🎰 Daily Draw Bot Help",
        description="Welcome to the Daily Draw Bot!",
        color=discord.Color.blue()
    )
    
    # Draw rules
    embed.add_field(
        name="📋 Draw Rules",
        value="""🎉 **Free Draw**: Once per day, completely free
🎰 **Paid Draw**: Up to 10 times per day, costs 100 points each
⏰ **Reset Time**: Draw count resets automatically at midnight
💰 **Reward Range**: 10-1000 points, average return rate 103.8%""",
        inline=False
    )
    
    # User commands (always visible)
    embed.add_field(
        name="🎲 User Commands",
        value="""`!draw` - Daily draw (free once, paid up to 10 times/day)
`!check [user]` - Check points and draw status
`!ranking` - View points leaderboard
`!roleshop` - View role shop
`!buytag <role name>` - Purchase a role
`!giftpoints <user> <points>` - Gift points to another user""",
        inline=False
    )
    
    # Quiz commands (always visible)
    embed.add_field(
        name="🎮 Quiz System",
        value="""`!quizlist` - View quiz categories
`!quiz <category> <number>` - Start a quiz game""",
        inline=False
    )
    
    # Check if user has administrator permissions
    if interaction.user.guild_permissions.administrator:
        embed.add_field(
            name="⚙️ Admin Commands",
            value="""`!givepoints <user> <points>` - Give points to a user
`!setpoints <user> <points>` - Set user points
`!resetdraw <user>` - Reset user's draw status
`!resetall --confirm` - Clear all user data
`!fixdb` - Fix database structure
`!checkdb` - Check database structure
`!debuguser <user>` - Debug user paid draw info
`!detailedebug <user>` - Detailed debug of paid draw logic
`!testupdate <user>` - Test database update function
`!addtag <price> <role>` - Add purchasable role
`!rewardinfo` - View draw probability system
`!testdraw [times]` - Test draw system
`!importquiz` - Import quiz file
`!deletequiz <category>` - Delete quiz questions
`/language` - Change bot language""",
            inline=False
        )
    
    embed.set_footer(text=f"Free draw once daily, paid draw up to {MAX_PAID_DRAWS_PER_DAY} times/day, costs 100 points each")
    return embed

def create_chinese_help_embed(interaction: discord.Interaction):
    """Create help embed in Chinese"""
    embed = discord.Embed(
        title="🎰 Daily Draw Bot 帮助",
        description="欢迎使用每日抽奖机器人！",
        color=discord.Color.blue()
    )
    
    # Draw rules
    embed.add_field(
        name="📋 抽奖规则",
        value="""🎉 **免费抽奖**：每天1次，完全免费
🎰 **付费抽奖**：每天最多10次，每次消耗100积分
⏰ **重置时间**：每天0点自动重置抽奖次数
💰 **奖励范围**：10-1000积分，平均回报率103.8%""",
        inline=False
    )
    
    # User commands (always visible)
    embed.add_field(
        name="🎲 用户命令",
        value="""`!draw` - 每日抽奖（免费1次，付费最多10次/天）
`!check [用户]` - 查看积分和抽奖状态
`!ranking` - 查看积分排行榜
`!roleshop` - 查看身份组商店
`!buytag <身份组名>` - 购买身份组
`!giftpoints <用户> <积分>` - 赠送积分给其他用户""",
        inline=False
    )
    
    # Quiz commands (always visible)
    embed.add_field(
        name="🎮 答题系统",
        value="""`!quizlist` - 查看题库类别
`!quiz <类别> <题目数>` - 开始答题游戏""",
        inline=False
    )
    
    # Check if user has administrator permissions
    if interaction.user.guild_permissions.administrator:
        embed.add_field(
            name="⚙️ 管理员命令",
            value="""`!givepoints <用户> <积分>` - 给予用户积分
`!setpoints <用户> <积分>` - 设置用户积分
`!resetdraw <用户>` - 重置用户抽奖状态
`!resetall --confirm` - 清空所有用户数据
`!fixdb` - 修复数据库结构
`!checkdb` - 检查数据库结构
`!debuguser <用户>` - 调试用户付费抽奖信息
`!detailedebug <用户>` - 详细调试付费抽奖逻辑
`!testupdate <用户>` - 测试数据库更新功能
`!addtag <价格> <身份组>` - 添加可购买身份组
`!rewardinfo` - 查看抽奖概率系统
`!testdraw [次数]` - 测试抽奖系统
`!importquiz` - 导入题库文件
`!deletequiz <类别>` - 删除题库题目
`/language` - 更改机器人语言""",
            inline=False
        )
    
    embed.set_footer(text=f"每日免费抽奖1次，付费抽奖最多{MAX_PAID_DRAWS_PER_DAY}次/天，每次消耗100积分")
    return embed 