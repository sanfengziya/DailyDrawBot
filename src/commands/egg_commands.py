import discord
from discord.ext import commands
from discord import app_commands
import random
import datetime
from src.db.database import get_connection
from src.utils.ui import create_embed
from src.config.languages import get_text

class EggCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 抽蛋成本配置
    SINGLE_DRAW_COST = 500
    TEN_DRAW_COST = 4500
    
    # 星级配置
    MAX_STARS = {
        'C': 2,
        'R': 3,
        'SR': 4,
        'SSR': 6
    }
    
    # 初始星级范围
    INITIAL_STARS = {
        'C': (0, 1),
        'R': (0, 2),
        'SR': (1, 2),
        'SSR': (1, 3)
    }
    
    @staticmethod
    def get_pet_names():
        """从数据库获取宠物名称"""
        conn = get_connection()
        c = conn.cursor()
        
        c.execute("""
            SELECT pet_name, rarity 
            FROM pet_templates
        """)
        templates = c.fetchall()
        
        c.close()
        conn.close()
        
        # 组织数据为字典格式
        pet_names = {}
        for pet_name, rarity in templates:
            if rarity not in pet_names:
                pet_names[rarity] = []
            pet_names[rarity].append(pet_name)
        
        return pet_names
    
    @staticmethod
    def get_draw_probabilities():
        """从数据库获取抽蛋概率配置"""
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT rarity, probability FROM egg_draw_probabilities ORDER BY FIELD(rarity, 'SSR', 'SR', 'R', 'C')")
        probabilities = c.fetchall()
        c.close()
        conn.close()
        return probabilities
    
    @staticmethod
    def get_hatch_probabilities(egg_rarity):
        """从数据库获取指定蛋稀有度的孵化概率配置"""
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT pet_rarity, probability FROM egg_hatch_probabilities WHERE egg_rarity = %s ORDER BY FIELD(pet_rarity, 'SSR', 'SR', 'R', 'C')", (egg_rarity,))
        probabilities = c.fetchall()
        c.close()
        conn.close()
        return probabilities

# 斜杠命令定义
@app_commands.command(name="egg", description="🥚 蛋系统 - 抽蛋、孵化、查看")
@app_commands.describe(action="选择操作类型")
@app_commands.choices(action=[
    app_commands.Choice(name="🎰 抽蛋", value="draw"),
    app_commands.Choice(name="📋 查看蛋列表", value="list"),
    app_commands.Choice(name="🐣 孵化蛋", value="hatch"),
    app_commands.Choice(name="🎁 领取宠物", value="claim")
])
@app_commands.guild_only()
async def egg(interaction: discord.Interaction, action: str):
    """蛋系统主命令"""
    if action == "draw":
        await handle_egg_draw(interaction)
    elif action == "list":
        await handle_egg_list(interaction)
    elif action == "hatch":
        await handle_egg_hatch(interaction)
    elif action == "claim":
        await handle_egg_claim(interaction)

async def handle_egg_draw(interaction: discord.Interaction):
    """处理抽蛋功能"""
    # 检查用户积分
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT points FROM users WHERE user_id = %s", (str(interaction.user.id),))
    result = c.fetchone()
    
    if not result:
        # 创建新用户
        c.execute("INSERT INTO users (user_id, points) VALUES (%s, 0)", (str(interaction.user.id),))
        conn.commit()
        points = 0
    else:
        points = result[0]
    
    # 获取实际的抽蛋概率
    draw_probabilities = EggCommands.get_draw_probabilities()
    
    c.close()
    conn.close()
    
    # 构建概率显示文本
    rarity_names = {'SSR': '💛 传说蛋', 'SR': '💜 史诗蛋', 'R': '💙 稀有蛋', 'C': '🤍 普通蛋'}
    probability_text = "**蛋稀有度概率：**\n"
    for rarity, probability in draw_probabilities:
        probability_text += f"{rarity_names[rarity]}：{float(probability)}%\n"
    
    embed = create_embed(
        "🎰 抽蛋界面",
        f"你当前有 **{points}** 积分\n\n"
        f"**单抽：** {EggCommands.SINGLE_DRAW_COST} 积分\n"
        f"**十连：** {EggCommands.TEN_DRAW_COST} 积分（9折优惠！）\n\n"
        f"{probability_text}",
        discord.Color.gold()
    )
    
    view = EggDrawView(interaction.user)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def handle_egg_list(interaction: discord.Interaction):
    """处理查看蛋列表功能"""
    await egg_list(interaction)

async def handle_egg_hatch(interaction: discord.Interaction):
    """处理孵化蛋功能"""
    conn = get_connection()
    c = conn.cursor()
    
    # 首先检查是否已经有蛋在孵化中
    c.execute("""
        SELECT egg_id, egg_code, start_time, end_time FROM player_eggs 
        WHERE user_id = %s AND status = '孵化中'
    """, (str(interaction.user.id),))
    incubating_egg = c.fetchone()
    
    if incubating_egg:
        egg_id, egg_code, start_time, end_time = incubating_egg
        rarity_names = {'C': '普通', 'R': '稀有', 'SR': '史诗', 'SSR': '传说'}
        rarity_emojis = {'C': '🤍', 'R': '💙', 'SR': '💜', 'SSR': '💛'}
        
        rarity_name = rarity_names[egg_code]
        emoji = rarity_emojis[egg_code]
        
        current_time = datetime.datetime.now()
        if current_time >= end_time:
            status_text = "✅ 已完成，可以领取！"
            action_text = "使用 `/egg claim` 来领取你的宠物！"
        else:
            remaining = end_time - current_time
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            if hours > 0:
                time_text = f"{hours}小时{minutes}分钟"
            else:
                time_text = f"{minutes}分钟"
            status_text = f"⏰ 还需要 {time_text}"
            action_text = "请耐心等待孵化完成！"
        
        embed = create_embed(
            "🚫 无法开始新的孵化",
            f"你已经有一颗蛋正在孵化中！\n\n"
            f"{emoji} **{rarity_name}蛋**\n"
            f"状态：{status_text}\n\n"
            f"{action_text}",
            discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        c.close()
        conn.close()
        return
    
    # 查询用户的待孵化蛋
    c.execute("""
        SELECT egg_id, egg_code, created_at FROM player_eggs 
        WHERE user_id = %s AND status = '待孵化'
        ORDER BY created_at DESC
        LIMIT 25
    """, (str(interaction.user.id),))
    eggs = c.fetchall()
    
    if not eggs:
        await interaction.response.send_message("你没有可以孵化的蛋！先去抽一些蛋吧！", ephemeral=True)
        c.close()
        conn.close()
        return
    
    # 创建选择界面
    embed = create_embed(
        "🐣 选择要孵化的蛋",
        f"你有 {len(eggs)} 个待孵化的蛋，请选择一个开始孵化：",
        discord.Color.orange()
    )
    
    view = EggHatchView(eggs)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    c.close()
    conn.close()

async def handle_egg_claim(interaction: discord.Interaction):
    """处理领取宠物功能"""
    conn = get_connection()
    c = conn.cursor()
    
    # 查询已完成孵化的蛋
    current_time = datetime.datetime.now()
    c.execute("""
        SELECT egg_id, egg_code, end_time FROM player_eggs 
        WHERE user_id = %s AND status = '孵化中' AND end_time <= %s
        ORDER BY end_time ASC
        LIMIT 10
    """, (str(interaction.user.id), current_time))
    ready_eggs = c.fetchall()
    
    if not ready_eggs:
        await interaction.response.send_message("没有可以领取的宠物！请先孵化一些蛋，或者等待孵化完成。", ephemeral=True)
        c.close()
        conn.close()
        return
    
    # 批量领取所有完成的蛋
    claimed_pets = []
    
    # 获取宠物名称数据
    pet_names = EggCommands.get_pet_names()
    
    for egg_id, egg_code, end_time in ready_eggs:
        # 根据蛋的稀有度和孵化概率决定宠物稀有度
        hatch_probabilities = EggCommands.get_hatch_probabilities(egg_code)
        
        # 使用概率决定宠物稀有度
        rand = random.random() * 100
        cumulative_prob = 0
        pet_rarity = egg_code  # 默认值，如果没有配置概率就使用蛋的稀有度
        
        for rarity, probability in hatch_probabilities:
            cumulative_prob += float(probability)
            if rand < cumulative_prob:
                pet_rarity = rarity
                break
        
        # 生成宠物
        pet_names_for_rarity = pet_names.get(pet_rarity, [])
        if not pet_names_for_rarity:
            # 如果没有该稀有度的宠物，回退到蛋的稀有度
            pet_rarity = egg_code
            pet_names_for_rarity = pet_names.get(pet_rarity, [])
        
        pet_name = random.choice(pet_names_for_rarity)
        initial_stars = random.randint(*EggCommands.INITIAL_STARS[pet_rarity])
        
        # 添加到宠物库存
        c.execute("""
            INSERT INTO pets (user_id, pet_name, rarity, stars, max_stars, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (str(interaction.user.id), pet_name, pet_rarity, initial_stars, EggCommands.MAX_STARS[pet_rarity], datetime.datetime.now()))
        
        # 更新蛋状态
        c.execute("""
            UPDATE player_eggs SET status = '已领取' WHERE egg_id = %s
        """, (egg_id,))
        
        rarity_names = {'C': '普通', 'R': '稀有', 'SR': '史诗', 'SSR': '传说'}
        rarity_emojis = {'C': '🤍', 'R': '💙', 'SR': '💜', 'SSR': '💛'}
        
        claimed_pets.append({
            'name': pet_name,
            'rarity': pet_rarity,
            'rarity_name': rarity_names[pet_rarity],
            'emoji': rarity_emojis[pet_rarity],
            'stars': initial_stars,
            'egg_rarity': egg_code  # 记录原始蛋的稀有度
        })
    
    conn.commit()
    c.close()
    conn.close()
    
    # 创建结果展示
    result_text = ""
    for pet in claimed_pets:
        stars_text = "⭐" * pet['stars']
        result_text += f"{pet['emoji']} **{pet['name']}** ({pet['rarity_name']}) {stars_text}\n"
    
    embed = create_embed(
        "🎉 宠物领取成功！",
        f"恭喜 {interaction.user.mention} 获得了以下宠物：\n\n{result_text}\n"
        f"总共领取了 **{len(claimed_pets)}** 只宠物！",
        discord.Color.gold()
    )
    
    await interaction.response.send_message(embed=embed)

async def egg_list(interaction: discord.Interaction):
    """查看蛋和孵化状态"""
    conn = get_connection()
    c = conn.cursor()
    
    # 查询用户的蛋
    c.execute("""
        SELECT egg_id, egg_code, created_at FROM player_eggs 
        WHERE user_id = %s AND status = '待孵化'
        ORDER BY created_at DESC
    """, (str(interaction.user.id),))
    eggs = c.fetchall()
    
    # 查询孵化中的蛋
    c.execute("""
        SELECT egg_id, egg_code, start_time, end_time FROM player_eggs
        WHERE user_id = %s AND status = '孵化中'
        ORDER BY end_time ASC
    """, (str(interaction.user.id),))
    incubating = c.fetchall()
    
    # 查询可领取的蛋
    current_time = datetime.datetime.now()
    c.execute("""
        SELECT COUNT(*) FROM player_eggs 
        WHERE user_id = %s AND status = '孵化中' AND end_time <= %s
    """, (str(interaction.user.id), current_time))
    ready_count = c.fetchone()[0]
    
    c.close()
    conn.close()
    
    if not eggs and not incubating:
        embed = create_embed(
            "📋 我的蛋库存",
            "你还没有任何蛋！\n使用 `/egg draw` 来抽取你的第一个蛋吧！",
            discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)
        return
    
    # 构建显示内容
    description = ""
    
    # 显示可领取提示
    if ready_count > 0:
        description += f"🎉 **你有 {ready_count} 只宠物可以领取！**\n使用 `/egg claim` 来领取它们！\n\n"
    
    if incubating:
        description += "**🔥 孵化中：**\n"
        for egg_id, egg_code, start_time, end_time in incubating:
            rarity_emoji = {'C': '🤍', 'R': '💙', 'SR': '💜', 'SSR': '💛'}[egg_code]
            rarity_name = {'C': '普通', 'R': '稀有', 'SR': '史诗', 'SSR': '传说'}[egg_code]
            now = datetime.datetime.now()
            
            if now >= end_time:
                status = "✅ 可领取"
            else:
                remaining = end_time - now
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                if hours > 0:
                    status = f"⏰ {hours}小时{minutes}分钟"
                else:
                    status = f"⏰ {minutes}分钟"
            
            description += f"{rarity_emoji} {rarity_name}蛋 - {status}\n"
        description += "\n"
    
    if eggs:
        description += "**📦 库存中：**\n"
        egg_count = {}
        for egg_id, rarity, created_at in eggs:
            if egg_id not in [inc[0] for inc in incubating]:  # 排除孵化中的蛋
                if rarity not in egg_count:
                    egg_count[rarity] = []
                egg_count[rarity].append(egg_id)
        
        for rarity in ['SSR', 'SR', 'R', 'C']:
            if rarity in egg_count:
                rarity_emoji = {'C': '🤍', 'R': '💙', 'SR': '💜', 'SSR': '💛'}[rarity]
                rarity_name = {'C': '普通', 'R': '稀有', 'SR': '史诗', 'SSR': '传说'}[rarity]
                description += f"{rarity_emoji} {rarity_name}蛋 x{len(egg_count[rarity])}\n"
    
    embed = create_embed(
        "📋 我的蛋库存",
        description,
        discord.Color.blue()
    )
    
    await interaction.response.send_message(embed=embed)

# 抽蛋视图类
class EggDrawView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=300)
        self.user = user

    @discord.ui.button(label="单抽 (500积分)", style=discord.ButtonStyle.primary, emoji="🎲")
    async def single_draw(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("你无法使用别人的抽蛋界面！", ephemeral=True)
            return
        
        await self.perform_draw(interaction, 1, EggCommands.SINGLE_DRAW_COST)

    @discord.ui.button(label="十连抽 (4500积分)", style=discord.ButtonStyle.success, emoji="🎰")
    async def ten_draw(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("你无法使用别人的抽蛋界面！", ephemeral=True)
            return
        
        await self.perform_draw(interaction, 10, EggCommands.TEN_DRAW_COST)

    async def perform_draw(self, interaction, count, cost):
        """执行抽蛋"""
        conn = get_connection()
        c = conn.cursor()
        
        # 检查积分
        c.execute("SELECT points FROM users WHERE user_id = %s", (str(interaction.user.id),))
        result = c.fetchone()
        
        if not result or result[0] < cost:
            await interaction.response.send_message(
                f"积分不足！需要 {cost} 积分，你只有 {result[0] if result else 0} 积分。",
                ephemeral=True
            )
            c.close()
            conn.close()
            return
        
        # 先发送初始响应，避免交互超时
        await interaction.response.send_message("🎰 正在抽蛋中...", ephemeral=True)
        
        # 扣除积分
        c.execute("UPDATE users SET points = points - %s WHERE user_id = %s", (cost, str(interaction.user.id)))
        
        # 纯概率抽蛋
        results = self.draw_eggs(count)
        
        # 添加蛋到玩家库存
        for rarity in results:
            # 直接使用稀有度作为蛋代码，与egg_types表匹配
            egg_code = rarity  # C, R, SR, SSR
            c.execute("""
                INSERT INTO player_eggs (user_id, egg_code, status, created_at)
                VALUES (%s, %s, '待孵化', %s)
            """, (str(interaction.user.id), egg_code, datetime.datetime.now()))
        
        # 不再需要抽蛋统计（已删除保底机制）
        
        conn.commit()
        c.close()
        conn.close()
        
        # 显示结果
        result_text = ""
        rarity_count = {}
        for rarity in results:
            rarity_count[rarity] = rarity_count.get(rarity, 0) + 1
        
        for rarity in ['SSR', 'SR', 'R', 'C']:
            if rarity in rarity_count:
                emoji = {'C': '🤍', 'R': '💙', 'SR': '💜', 'SSR': '💛'}[rarity]
                name = {'C': '普通', 'R': '稀有', 'SR': '史诗', 'SSR': '传说'}[rarity]
                result_text += f"{emoji} {name}蛋 x{rarity_count[rarity]}\n"
        
        embed = create_embed(
            f"🎉 抽蛋结果 - {count}抽",
            f"**{interaction.user.mention} 获得：**\n{result_text}\n"
            f"**消耗：** {cost} 积分",
            discord.Color.green()
        )
        
        # 先编辑原始私有消息
        await interaction.edit_original_response(content="✅ 抽蛋完成！", embed=None, view=None)
        # 然后发送公开的结果消息
        await interaction.followup.send(embed=embed)

    def draw_eggs(self, count):
        """纯概率抽蛋，无保底机制"""
        # 获取抽蛋概率配置
        draw_probabilities = EggCommands.get_draw_probabilities()
        
        results = []
        
        for i in range(count):
            # 使用数据库配置的概率进行抽取
            rand = random.random() * 100
            cumulative_prob = 0
            
            # 按概率从高到低排序，累积概率判断
            for rarity, probability in draw_probabilities:
                cumulative_prob += float(probability)
                if rand < cumulative_prob:
                    results.append(rarity)
                    break
            else:
                # 如果没有匹配到任何概率（理论上不应该发生），默认给C
                results.append('C')
        
        return results


class EggHatchView(discord.ui.View):
    def __init__(self, eggs):
        super().__init__(timeout=300)
        self.eggs = eggs
        
        # 创建选择菜单
        options = []
        for egg in eggs[:25]:  # Discord限制最多25个选项
            egg_id, egg_code, created_at = egg
            rarity_names = {'C': '普通', 'R': '稀有', 'SR': '史诗', 'SSR': '传说'}
            rarity_emojis = {'C': '🤍', 'R': '💙', 'SR': '💜', 'SSR': '💛'}
            
            rarity_name = rarity_names.get(egg_code, '未知')
            emoji = rarity_emojis.get(egg_code, '❓')
            
            # 格式化创建时间
            time_str = created_at.strftime("%m-%d %H:%M")
            
            options.append(discord.SelectOption(
                label=f"{emoji} {rarity_name}蛋",
                description=f"获得时间: {time_str}",
                value=str(egg_id),
                emoji=emoji
            ))
        
        if options:
            select = EggSelect(options, self.eggs)
            self.add_item(select)


class EggSelect(discord.ui.Select):
    def __init__(self, options, eggs):
        super().__init__(placeholder="选择要孵化的蛋...", options=options)
        self.eggs = eggs
    
    async def callback(self, interaction: discord.Interaction):
        selected_egg_id = int(self.values[0])
        
        # 找到选中的蛋
        selected_egg = None
        for egg in self.eggs:
            if egg[0] == selected_egg_id:
                selected_egg = egg
                break
        
        if not selected_egg:
            await interaction.response.send_message("蛋不存在！", ephemeral=True)
            return
        
        egg_id, egg_code, created_at = selected_egg
        
        # 计算孵化时间（根据稀有度）
        hatch_times = {'C': 1, 'R': 2, 'SR': 4, 'SSR': 8}  # 小时
        hatch_hours = hatch_times.get(egg_code, 1)
        
        # 开始孵化
        conn = get_connection()
        c = conn.cursor()
        
        start_time = datetime.datetime.now()
        end_time = start_time + datetime.timedelta(hours=hatch_hours)
        
        c.execute("""
            UPDATE player_eggs 
            SET status = '孵化中', start_time = %s, end_time = %s
            WHERE egg_id = %s AND user_id = %s
        """, (start_time, end_time, egg_id, str(interaction.user.id)))
        
        conn.commit()
        c.close()
        conn.close()
        
        rarity_names = {'C': '普通', 'R': '稀有', 'SR': '史诗', 'SSR': '传说'}
        rarity_name = rarity_names.get(egg_code, '未知')
        
        embed = create_embed(
            "🐣 开始孵化！",
            f"**{interaction.user.mention}** 的 **{rarity_name}蛋** 开始孵化了！\n\n"
            f"⏰ 孵化时间：{hatch_hours} 小时\n\n"
            f"请耐心等待，到时间后使用 `/egg claim` 来领取你的宠物！",
            discord.Color.green()
        )
        
        # 先编辑原始私有消息
        await interaction.response.edit_message(content="✅ 孵化开始！", embed=None, view=None)
        # 然后发送公开的孵化消息
        await interaction.followup.send(embed=embed)


def setup(bot):
    """注册斜杠命令"""
    bot.tree.add_command(egg)