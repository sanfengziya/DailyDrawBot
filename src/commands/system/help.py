import discord
from src.config.config import MAX_PAID_DRAWS_PER_DAY

async def help_command(interaction: discord.Interaction):
    """Show help information for all commands"""
    

    embed = create_help_embed(interaction)
    
    await interaction.response.send_message(embed=embed)

def create_help_embed(interaction: discord.Interaction):
    """Create help embed in Chinese"""
    embed = discord.Embed(
        title="🎰 Daily Draw Bot 帮助",
        description="欢迎使用每日抽奖机器人！",
        color=discord.Color.blue()
    )

    # 系统提示
    embed.add_field(
        name="ℹ️ 系统提示",
        value="""**斜杠命令:**
`/help` - 显示帮助信息""",
        inline=False
    )
    
    # 抽奖系统
    embed.add_field(
        name="🎲 抽奖系统",
        value="""**传统指令:**
`!draw <次数>` - 每日抽奖（免费1次，付费最多20次/天，每次100积分）（次数不填默认为1次）
`!check [用户]` - 查看积分和抽奖状态
`!giftpoints <用户> <积分>` - 赠送积分给其他用户

**抽奖规则:**
- 🎉 **免费抽奖**：每天1次，完全免费
- 🎰 **付费抽奖**：每天最多20次，每次消耗100积分
- ⏰ **重置时间**：每天0点自动重置抽奖次数
- 💰 **奖励范围**：10-1000积分，平均回报率103.8%""",
        inline=False
    )

    # 蛋系统
    embed.add_field(
        name="🥚 蛋系统",
        value="""**斜杠命令:**
`/egg action:抽蛋` - 抽取宠物蛋（单抽250积分，十连2250积分）
`/egg action:查看蛋列表` - 查看拥有的蛋库存
`/egg action:孵化蛋` - 选择蛋进行孵化
`/egg action:领取宠物` - 领取已完成孵化的宠物""",
        inline=False
    )

    # 宠物系统
    embed.add_field(
        name="🐾 宠物系统",
        value="""**斜杠命令:**
`/pet action:查看列表 [页码]` - 查看宠物列表（分页显示）
`/pet action:查看详情` - 查看指定宠物详细信息
`/pet action:升星` - 升级宠物星级（需要碎片和积分）
`/pet action:分解` - 分解宠物获得碎片和积分
`/pet action:查看碎片` - 查看拥有的宠物碎片库存
`/pet action:装备` - 装备宠物开始自动获取积分
`/pet action:卸下` - 卸下当前装备的宠物
`/pet action:装备状态` - 查看当前装备状态和待领取积分
`/pet action:领取积分` - 领取宠物自动获得的积分
`/pet action:喂食` - 喂食宠物获得经验

**自动喂食:**
`/feed_auto [pet] [mode] [quantity]` - 一键喂食宠物""",
        inline=False
    )

    # 杂货铺系统
    embed.add_field(
        name="🏪 杂货铺系统",
        value="""**斜杠命令:**
`/shop action:查看商品` - 查看今日杂货铺商品
`/shop action:购买 item:<商品名> quantity:<数量>` - 购买指定食粮
`/inventory item_type:food` - 查看食粮库存""",
        inline=False
    )

    # 锻造系统
    embed.add_field(
        name="🔨 锻造系统",
        value="""**斜杠命令:**
`/forge action:查看锻造台` - 查看碎片库存和合成规则
`/forge action:合成碎片 from_rarity:<源稀有度> to_rarity:<目标稀有度> quantity:<数量>` - 合成宠物碎片

**合成规则:**
- C碎片 → R碎片：10:1 + 50积分
- R碎片 → SR碎片：5:1 + 80积分
- SR碎片 → SSR碎片：3:1 + 100积分""",
        inline=False
    )

    # 身份组系统
    embed.add_field(
        name="🏷️ 身份组系统",
        value="""**斜杠命令:**
`/tag action:商店` - 查看身份组商店
`/tag action:购买 role_name:<身份组名>` - 购买指定身份组""",
        inline=False
    )

    # 答题系统
    embed.add_field(
        name="🎮 答题系统",
        value="""**传统指令:**
`!quizlist [语言]` - 查看题库类别
  • `!quizlist` 或 `!quizlist all` - 显示所有语言
  • `!quizlist chinese` - 只显示中文题库
  • `!quizlist english` - 只显示英文题库

**提示:**
- 答对每题可获得20积分
- 等待管理员开启答题！""",
        inline=False
    )

    # 二十一点游戏
    embed.add_field(
        name="🎰 二十一点游戏",
        value="""**斜杠命令:**
`/blackjack <bet>` - 开始二十一点游戏
  • `bet`: 下注金额（数字或 `all`）
  • 示例：`/blackjack 100` 或 `/blackjack all`
`/blackjack_stats` - 查看游戏统计数据

**游戏功能:**
- 🎴✋ **基础操作**：要牌、停牌
- 🎲 **加倍下注**：首次发牌后加倍（Double Down）
- ✂️ **分牌**：对子可以分成两手牌（Split）
- 🎲✂️ **DAS规则**：分牌后可以加倍（降低庄家优势0.14%）
- 🛡️ **保险**：庄家明牌A时可购买保险
- 🏳️ **投降**：手牌极差时止损

**特色:**
- ✅ 标准赌场规则（庄家17点停牌）
- ✅ BlackJack特殊奖励（2.5倍赔率）
- ✅ 完整游戏记录和统计""",
        inline=False
    )

    # 排行榜系统
    embed.add_field(
        name="🏆 排行榜系统",
        value="""**传统指令:**
`!ranking` - 查看积分排行榜（显示前10名，生成图片）""",
        inline=False
    )
    
    # Check if user has administrator permissions
    if interaction.user.guild_permissions.administrator:
        embed.add_field(
            name="⚙️ 管理员命令",
            value="""**系统调试:**
`!rewardinfo` - 显示奖品概率信息
`!checksubscription` - 检查服务器订阅状态

**身份组管理:**
`!addtag <价格> <身份组>` - 添加可购买身份组
`!removetag <身份组>` - 删除身份组商店中的身份组
`!updatetagprice <身份组> <新价格>` - 更新身份组价格
`!listtags` - 查看所有已添加的身份组

**答题管理:**
`!quiz "<类别>" <题目数>` - 开始答题游戏
  • 支持完全匹配：`!quiz 动漫 5`
  • 支持模糊匹配：`!quiz study 5` (匹配所有 study:xxx)
  • 答对每题奖励20积分

**积分管理:**
`!givepoints <用户> <积分>` - 给予用户积分
`!setpoints <用户> <积分>` - 设置用户积分""",
            inline=False
        )
    
    embed.set_footer(text=f"每日免费抽奖1次，付费抽奖最多{MAX_PAID_DRAWS_PER_DAY}次/天，每次消耗100积分")
    return embed 