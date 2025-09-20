import discord
from discord.ext import commands
from discord import app_commands
import random
import datetime
from src.db.database import get_connection
from src.utils.ui import create_embed

class PetCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    # 升星消耗配置
    UPGRADE_COSTS = {
        0: {'fragments': 10, 'points': 100},   # 0★ → 1★
        1: {'fragments': 20, 'points': 250},   # 1★ → 2★
        2: {'fragments': 30, 'points': 500},   # 2★ → 3★
        3: {'fragments': 40, 'points': 1000},  # 3★ → 4★
        4: {'fragments': 50, 'points': 1500},  # 4★ → 5★
        5: {'fragments': 100, 'points': 2000}, # 5★ → 6★
    }
    
    # 宠物积分获取配置
    PET_POINTS_PER_HOUR = {
        'C': 3,    # 普通宠物
        'R': 5,    # 稀有宠物
        'SR': 8,   # 史诗宠物
        'SSR': 12  # 传说宠物
    }

    def add_fragments(self, player_id, rarity, amount):
        """添加碎片到玩家库存"""
        conn = get_connection()
        c = conn.cursor()
        
        c.execute("""
            INSERT INTO pet_fragments (user_id, rarity, amount)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE amount = amount + %s
        """, (player_id, rarity, amount, amount))
        
        conn.commit()
        c.close()
        conn.close()
    
    def calculate_pet_points(self, rarity, stars, hours):
        """计算宠物积分获取量"""
        base_points = self.PET_POINTS_PER_HOUR.get(rarity, 0)
        multiplier = stars + 1
        return int(base_points * multiplier * hours)
    
    def update_pet_points(self, user_id):
        """更新装备宠物的时间戳（用于积分计算）"""
        conn = get_connection()
        c = conn.cursor()
        
        # 检查用户是否有装备的宠物
        c.execute("""
            SELECT equipped_pet_id
            FROM users
            WHERE user_id = %s AND equipped_pet_id IS NOT NULL
        """, (user_id,))
        
        result = c.fetchone()
        if not result:
            c.close()
            conn.close()
            return
        
        # 更新最后更新时间为当前时间
        now = datetime.datetime.now()
        c.execute("""
            UPDATE users 
            SET last_pet_points_update = %s 
            WHERE user_id = %s
        """, (now, user_id))
        
        conn.commit()
        c.close()
        conn.close()

    def calculate_pending_points(self, user_id):
        """基于时间差计算待领取的宠物积分（最多累积24小时）"""
        conn = get_connection()
        c = conn.cursor()
        
        # 获取用户装备的宠物信息和上次更新时间
        c.execute("""
            SELECT u.equipped_pet_id, u.last_pet_points_update, p.rarity, p.stars
            FROM users u
            LEFT JOIN pets p ON u.equipped_pet_id = p.pet_id
            WHERE u.user_id = %s AND u.equipped_pet_id IS NOT NULL
        """, (user_id,))
        
        result = c.fetchone()
        if not result:
            c.close()
            conn.close()
            return 0
        
        equipped_pet_id, last_update, rarity, stars = result
        
        # 计算时间差（小时）
        now = datetime.datetime.now()
        if last_update:
            time_diff = now - last_update
            hours = time_diff.total_seconds() / 3600
        else:
            # 如果没有记录，说明刚装备，返回0
            c.close()
            conn.close()
            return 0
        
        # 限制最多累积24小时的积分
        max_hours = 24
        actual_hours = min(hours, max_hours)
        
        # 如果时间差小于0.1小时（6分钟），返回0
        if actual_hours < 0.1:
            c.close()
            conn.close()
            return 0
        
        # 计算获得的积分
        pending_points = self.calculate_pet_points(rarity, stars, actual_hours)
        
        c.close()
        conn.close()
        return int(pending_points)

# 宠物选择视图
class PetSelectView(discord.ui.View):
    def __init__(self, user_id: int, action: str):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.action = action
        
    async def setup_select(self):
        """设置宠物选择下拉菜单"""
        conn = get_connection()
        c = conn.cursor()
        
        c.execute("""
            SELECT pet_id, pet_name, rarity, stars
            FROM pets
            WHERE user_id = %s
            ORDER BY rarity DESC, stars DESC, pet_name
            LIMIT 25
        """, (self.user_id,))
        
        pets = c.fetchall()
        c.close()
        conn.close()
        
        if not pets:
            return False
            
        # 稀有度颜色映射
        rarity_emojis = {
            "普通": "⚪",
            "稀有": "🔵", 
            "史诗": "🟣",
            "传说": "🟡",
            "神话": "🔴"
        }
        
        options = []
        for pet_id, pet_name, rarity, stars in pets:
            emoji = rarity_emojis.get(rarity, "⚪")
            star_display = "⭐" * stars if stars > 0 else ""
            label = f"{pet_name} {star_display}".strip()
            description = f"{rarity} | ID: {pet_id}"
            
            options.append(discord.SelectOption(
                label=label[:100],  # Discord限制
                description=description[:100],
                value=str(pet_id),
                emoji=emoji
            ))
        
        select = PetSelect(self.action, options)
        self.add_item(select)
        return True

class PetSelect(discord.ui.Select):
    def __init__(self, action: str, options):
        self.action = action
        super().__init__(
            placeholder=f"选择要{self.get_action_name()}的宠物...",
            options=options
        )
    
    def get_action_name(self):
        action_names = {
            "info": "查看详情",
            "upgrade": "升星", 
            "dismantle": "分解",
            "equip": "装备"
        }
        return action_names.get(self.action, "操作")
    
    async def callback(self, interaction: discord.Interaction):
        pet_id = int(self.values[0])
        
        if self.action == "info":
            await handle_pet_info(interaction, pet_id)
        elif self.action == "upgrade":
            await handle_pet_upgrade(interaction, pet_id)
        elif self.action == "dismantle":
            await handle_pet_dismantle(interaction, pet_id)
        elif self.action == "equip":
            await handle_pet_equip(interaction, pet_id)

# 主宠物命令
@app_commands.command(name="pet", description="🐾 宠物系统 - 查看、升星、分解")
@app_commands.guild_only()
@app_commands.describe(
    action="选择操作类型",
    page="页码（查看列表时使用，默认第1页）"
)
@app_commands.choices(action=[
    app_commands.Choice(name="📋 查看宠物列表", value="list"),
    app_commands.Choice(name="🔍 查看宠物详情", value="info"),
    app_commands.Choice(name="⭐ 升星宠物", value="upgrade"),
    app_commands.Choice(name="💥 分解宠物", value="dismantle"),
    app_commands.Choice(name="🧩 查看碎片库存", value="fragments"),
    app_commands.Choice(name="🎒 装备宠物", value="equip"),
    app_commands.Choice(name="📤 卸下宠物", value="unequip"),
    app_commands.Choice(name="👀 查看装备状态", value="status"),
    app_commands.Choice(name="💰 领取宠物积分", value="claim")
])
async def pet(interaction: discord.Interaction, action: str, page: int = 1):
    """宠物系统主命令"""
    if action == "list":
        await handle_pet_list(interaction, page)
    elif action in ["info", "upgrade", "dismantle", "equip"]:
        # 显示宠物选择界面
        view = PetSelectView(str(interaction.user.id), action)
        has_pets = await view.setup_select()
        
        if not has_pets:
            embed = create_embed(
                "❌ 没有宠物",
                "你还没有任何宠物！使用 `/egg claim` 来领取宠物吧！",
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
            
        action_names = {
            "info": "查看宠物详情",
            "upgrade": "升星宠物", 
            "dismantle": "分解宠物",
            "equip": "装备宠物"
        }
        
        embed = create_embed(
            f"🐾 {action_names[action]}",
            "请从下方选择要操作的宠物：",
            discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    elif action == "fragments":
        await handle_pet_fragments(interaction)
    elif action == "unequip":
        await handle_pet_unequip(interaction)
    elif action == "status":
        await handle_pet_status(interaction)
    elif action == "claim":
        await handle_pet_claim_points(interaction)

async def handle_pet_list(interaction: discord.Interaction, page: int = 1):
    """查看我的宠物"""
    conn = get_connection()
    c = conn.cursor()
    
    # 分页查询
    per_page = 10
    offset = (page - 1) * per_page
    
    c.execute("""
        SELECT pet_id, pet_name, rarity, stars, max_stars, created_at
        FROM pets
        WHERE user_id = %s
        ORDER BY rarity DESC, stars DESC, created_at DESC
        LIMIT %s OFFSET %s
    """, (str(interaction.user.id), per_page, offset))
    
    pets = c.fetchall()
    
    # 获取总数
    c.execute("SELECT COUNT(*) FROM pets WHERE user_id = %s", (str(interaction.user.id),))
    total_pets = c.fetchone()[0]
    
    c.close()
    conn.close()
    
    if not pets:
        embed = create_embed(
            "🐾 我的宠物",
            f"{interaction.user.mention} 你还没有任何宠物呢！快去抽蛋孵化吧！",
            discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        return
    
    rarity_colors = {
        'C': '🤍',
        'R': '💙',
        'SR': '💜',
        'SSR': '💛'
    }
    
    description = ""
    for pet_id, pet_name, rarity, stars, max_stars, created_at in pets:
        star_display = '⭐' * stars if stars > 0 else '无星'
        description += f"{rarity_colors[rarity]} **{pet_name}** (ID: {pet_id})\n"
        description += f"   星级: {star_display} ({stars}/{max_stars})\n\n"
    
    total_pages = (total_pets + per_page - 1) // per_page
    
    embed = create_embed(
        f"🐾 {interaction.user.mention} 的宠物 (第 {page}/{total_pages} 页)",
        description,
        discord.Color.blue()
    )
    embed.set_footer(text=f"总共 {total_pets} 只宠物")
    await interaction.response.send_message(embed=embed)

async def handle_pet_info(interaction: discord.Interaction, pet_id: int):
    """查看宠物详情"""
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("""
        SELECT pet_name, rarity, stars, max_stars, created_at
        FROM pets
        WHERE pet_id = %s AND user_id = %s
    """, (pet_id, str(interaction.user.id)))
    
    result = c.fetchone()
    c.close()
    conn.close()
    
    if not result:
        embed = create_embed(
            "❌ 错误",
            f"{interaction.user.mention} 找不到这只宠物或者它不属于你！",
            discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        c.close()
        conn.close()
        return

    pet_name, rarity, stars, max_stars = result
    
    if stars >= max_stars:
        embed = create_embed(
            "⭐ 已满星",
            f"{interaction.user.mention} 你的 {pet_name} 已经达到最大星级了！",
            discord.Color.yellow()
        )
        await interaction.response.send_message(embed=embed)
        c.close()
        conn.close()
        return
    
    rarity_colors = {
        'C': '🤍',
        'R': '💙',
        'SR': '💜',
        'SSR': '💛'
    }
    
    star_display = '⭐' * stars if stars > 0 else '无星'
    
    # 计算升星费用（如果还能升星）
    upgrade_info = ""
    if stars < max_stars:
        cost = PetCommands.UPGRADE_COSTS[stars]
        upgrade_info = f"\n**升星费用：**\n{cost['fragments']} 个 {rarity} 碎片 + {cost['points']} 积分"
    else:
        upgrade_info = "\n**已达到最大星级！**"
    
    embed = create_embed(
        f"{rarity_colors[rarity]} {interaction.user.mention} 的 {pet_name}",
        f"**宠物ID：** {pet_id}\n"
        f"**稀有度：** {rarity}\n"
        f"**星级：** {star_display} ({stars}/{max_stars})\n"
        f"**获得时间：** {created_at.strftime('%Y-%m-%d %H:%M:%S')}"
        f"{upgrade_info}",
        discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

async def handle_pet_upgrade(interaction: discord.Interaction, pet_id: int):
    """升星宠物"""
    conn = get_connection()
    c = conn.cursor()
    
    # 获取宠物信息
    c.execute("""
        SELECT pet_name, rarity, stars, max_stars
        FROM pets
        WHERE pet_id = %s AND user_id = %s
    """, (pet_id, str(interaction.user.id)))
    
    result = c.fetchone()
    if not result:
        embed = create_embed(
            "❌ 错误",
            f"{interaction.user.mention} 找不到这只宠物或者它不属于你！",
            discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        c.close()
        conn.close()
        return
    
    pet_name, rarity, stars, max_stars = result
    
    if stars >= max_stars:
        embed = create_embed(
            "⭐ 已满星",
            f"{interaction.user.mention} 你的 {pet_name} 已经达到最大星级了！",
            discord.Color.yellow()
        )
        await interaction.response.send_message(embed=embed)
        c.close()
        conn.close()
        return
    
    # 获取升星费用
    cost = PetCommands.UPGRADE_COSTS[stars]
    required_fragments = cost['fragments']
    required_points = cost['points']
    
    # 检查用户资源
    c.execute("""
        SELECT u.points, COALESCE(pf.amount, 0) as fragments
        FROM users u
        LEFT JOIN pet_fragments pf ON u.user_id = pf.user_id AND pf.rarity = %s
        WHERE u.user_id = %s
    """, (rarity, str(interaction.user.id)))
    
    resource_result = c.fetchone()
    if not resource_result:
        embed = create_embed(
            "❌ 错误",
            f"{interaction.user.mention} 无法获取你的资源信息！",
            discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        c.close()
        conn.close()
        return
    
    points, fragments = resource_result
    
    if points < required_points:
        embed = create_embed(
            "💰 积分不足",
            f"{interaction.user.mention} 升星需要 {required_points} 积分，你只有 {points} 积分！",
            discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        c.close()
        conn.close()
        return
    
    if fragments < required_fragments:
        embed = create_embed(
            "🧩 碎片不足",
            f"{interaction.user.mention} 升星需要 {required_fragments} 个 {rarity} 碎片，你只有 {fragments} 个！",
            discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        c.close()
        conn.close()
        return
    
    # 执行升星
    # 扣除积分
    c.execute("UPDATE users SET points = points - %s WHERE user_id = %s", 
             (required_points, str(interaction.user.id)))
    
    # 扣除碎片
    c.execute("""
        UPDATE pet_fragments 
        SET amount = amount - %s 
        WHERE user_id = %s AND rarity = %s
    """, (required_fragments, str(interaction.user.id), rarity))
    
    # 升星
    c.execute("UPDATE pets SET stars = stars + 1 WHERE pet_id = %s", (pet_id,))
    
    conn.commit()
    c.close()
    conn.close()
    
    new_stars = stars + 1
    star_display = '⭐' * new_stars
    
    embed = create_embed(
        "🌟 升星成功！",
        f"{interaction.user.mention} 你的 **{pet_name}** 成功升星！\n"
        f"星级：{star_display} ({new_stars}/{max_stars})\n"
        f"消耗：{required_fragments} 个 {rarity} 碎片 + {required_points} 积分",
        discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

async def handle_pet_dismantle(interaction: discord.Interaction, pet_id: int):
    """分解宠物"""
    conn = get_connection()
    c = conn.cursor()
    
    # 获取宠物信息
    c.execute("""
        SELECT pet_name, rarity, stars
        FROM pets
        WHERE pet_id = %s AND user_id = %s
    """, (pet_id, str(interaction.user.id)))
    
    result = c.fetchone()
    if not result:
        embed = create_embed(
            "❌ 错误",
            f"{interaction.user.mention} 找不到这只宠物或者它不属于你！",
            discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        c.close()
        conn.close()
        return
    
    pet_name, rarity, stars = result
    
    # 计算分解收益
    base_fragments = 10
    star_bonus_fragments = stars
    star_bonus_points = stars * 200
    
    total_fragments = base_fragments + star_bonus_fragments
    total_points = star_bonus_points
    
    # 创建确认界面
    embed = create_embed(
        "⚠️ 确认分解",
        f"{interaction.user.mention} 你确定要分解 **{pet_name}** 吗？\n\n"
        f"**分解收益：**\n"
        f"🧩 {total_fragments} 个 {rarity} 碎片\n"
        f"💰 {total_points} 积分\n\n"
        f"**注意：分解后无法恢复！**",
        discord.Color.orange()
    )
    
    view = DismantleConfirmView(str(interaction.user.id), pet_id, pet_name, rarity, total_fragments, total_points)
    await interaction.response.send_message(embed=embed, view=view)

async def handle_pet_fragments(interaction: discord.Interaction):
    """查看碎片库存"""
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("""
        SELECT rarity, amount
        FROM pet_fragments
        WHERE user_id = %s AND amount > 0
        ORDER BY 
            CASE rarity 
                WHEN 'SSR' THEN 1 
                WHEN 'SR' THEN 2 
                WHEN 'R' THEN 3 
                WHEN 'C' THEN 4 
            END
    """, (str(interaction.user.id),))
    
    fragments = c.fetchall()
    c.close()
    conn.close()
    
    if not fragments:
        embed = create_embed(
            "🧩 我的碎片",
            f"{interaction.user.mention} 你还没有任何碎片呢！分解宠物可以获得碎片！",
            discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        return
    
    rarity_colors = {
        'C': '🤍',
        'R': '💙',
        'SR': '💜',
        'SSR': '💛'
    }
    
    description = ""
    for rarity, amount in fragments:
        description += f"{rarity_colors[rarity]} **{rarity} 碎片：** {amount} 个\n"
    
    embed = create_embed(
        f"🧩 {interaction.user.mention} 的碎片",
        description,
        discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed)

class DismantleConfirmView(discord.ui.View):
    def __init__(self, user_id, pet_id, pet_name, rarity, fragments, points):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.pet_id = pet_id
        self.pet_name = pet_name
        self.rarity = rarity
        self.fragments = fragments
        self.points = points

    @discord.ui.button(label='确认分解', style=discord.ButtonStyle.danger, emoji='💥')
    async def confirm_dismantle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("这不是你的分解确认界面！", ephemeral=True)
            return
        
        conn = get_connection()
        c = conn.cursor()
        
        # 删除宠物
        c.execute("DELETE FROM pets WHERE pet_id = %s AND user_id = %s", 
                 (self.pet_id, self.user_id))
        
        if c.rowcount == 0:
            embed = create_embed(
                "❌ 错误",
                f"{interaction.user.mention} 宠物不存在或已被分解！",
                discord.Color.red()
            )
            await interaction.response.edit_message(embed=embed, view=None)
            c.close()
            conn.close()
            return
        
        # 添加碎片
        c.execute("""
            INSERT INTO pet_fragments (user_id, rarity, amount)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE amount = amount + %s
        """, (self.user_id, self.rarity, self.fragments, self.fragments))
        
        # 添加积分
        if self.points > 0:
            c.execute("UPDATE users SET points = points + %s WHERE user_id = %s", 
                     (self.points, self.user_id))
        
        conn.commit()
        c.close()
        conn.close()
        
        embed = create_embed(
            "💥 分解成功",
            f"{interaction.user.mention} 你的 **{self.pet_name}** 已被分解！\n\n"
            f"**获得：**\n"
            f"🧩 {self.fragments} 个 {self.rarity} 碎片\n"
            f"💰 {self.points} 积分",
            discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label='取消', style=discord.ButtonStyle.secondary, emoji='❌')
    async def cancel_dismantle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("这不是你的分解确认界面！", ephemeral=True)
            return
        
        embed = create_embed(
            "✅ 已取消",
            f"{interaction.user.mention} 分解操作已取消。",
            discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=None)

async def handle_pet_equip(interaction: discord.Interaction, pet_id: int):
    """装备宠物"""
    conn = get_connection()
    c = conn.cursor()
    
    # 检查宠物是否存在且属于用户
    c.execute("""
        SELECT pet_name, rarity, stars
        FROM pets
        WHERE pet_id = %s AND user_id = %s
    """, (pet_id, str(interaction.user.id)))
    
    result = c.fetchone()
    if not result:
        embed = create_embed(
            "❌ 错误",
            f"{interaction.user.mention} 找不到这只宠物或者它不属于你！",
            discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        c.close()
        conn.close()
        return
    
    pet_name, rarity, stars = result
    
    # 检查是否已经装备了这只宠物
    c.execute("SELECT equipped_pet_id FROM users WHERE user_id = %s", (str(interaction.user.id),))
    current_equipped = c.fetchone()
    
    if current_equipped and current_equipped[0] == pet_id:
        embed = create_embed(
            "⚠️ 已装备",
            f"{interaction.user.mention} 你已经装备了 **{pet_name}**！",
            discord.Color.yellow()
        )
        await interaction.response.send_message(embed=embed)
        c.close()
        conn.close()
        return
    
    # 检查是否有待领取的积分
    pet_commands = PetCommands(None)
    pending_points = pet_commands.calculate_pending_points(str(interaction.user.id))
    if pending_points > 0:
        embed = create_embed(
            "⚠️ 请先领取积分",
            f"{interaction.user.mention} 你有 **{pending_points}** 点待领取的宠物积分！\n\n"
            f"请先使用 `/pet claim` 领取积分，然后再更换宠物。",
            discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        c.close()
        conn.close()
        return
    
    # 如果有其他宠物装备，先更新积分累积
    if current_equipped and current_equipped[0]:
        pet_commands = PetCommands(None)
        pet_commands.update_pet_points(str(interaction.user.id))
    
    # 装备新宠物
    now = datetime.datetime.now()
    c.execute("""
        UPDATE users 
        SET equipped_pet_id = %s, last_pet_points_update = %s 
        WHERE user_id = %s
    """, (pet_id, now, str(interaction.user.id)))
    
    conn.commit()
    c.close()
    conn.close()
    
    # 计算每小时积分和待领取积分
    pet_commands = PetCommands(None)
    hourly_points = pet_commands.calculate_pet_points(rarity, stars, 1)
    pending_points = pet_commands.calculate_pending_points(str(interaction.user.id))
    
    star_display = '⭐' * stars if stars > 0 else '⚪'
    rarity_colors = {'C': '🤍', 'R': '💙', 'SR': '💜', 'SSR': '💛'}
    rarity_color = rarity_colors.get(rarity, '🤍')
    
    embed = create_embed(
        "🎒 装备成功！",
        f"{interaction.user.mention} 成功装备了 **{pet_name}**！\n\n"
        f"{rarity_color} **稀有度：** {rarity}\n"
        f"{star_display} **星级：** {stars}\n"
        f"💰 **每小时积分：** {hourly_points}\n\n"
        f"你的宠物现在会自动为你获取积分！",
        discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

async def handle_pet_unequip(interaction: discord.Interaction):
    """卸下宠物"""
    conn = get_connection()
    c = conn.cursor()
    
    # 检查是否有装备的宠物
    c.execute("""
        SELECT u.equipped_pet_id, p.pet_name, p.rarity, p.stars
        FROM users u
        LEFT JOIN pets p ON u.equipped_pet_id = p.pet_id
        WHERE u.user_id = %s AND u.equipped_pet_id IS NOT NULL
    """, (str(interaction.user.id),))
    
    result = c.fetchone()
    if not result:
        embed = create_embed(
            "❌ 没有装备宠物",
            f"{interaction.user.mention} 你当前没有装备任何宠物！",
            discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        c.close()
        conn.close()
        return
    
    equipped_pet_id, pet_name, rarity, stars = result
    
    # 检查是否有待领取的积分
    pet_commands = PetCommands(None)
    pending_points = pet_commands.calculate_pending_points(str(interaction.user.id))
    if pending_points > 0:
        embed = create_embed(
            "⚠️ 请先领取积分",
            f"{interaction.user.mention} 你有 **{pending_points}** 点待领取的宠物积分！\n\n"
            f"请先使用 `/pet claim` 领取积分，然后再卸下宠物。",
            discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        c.close()
        conn.close()
        return
    
    # 更新积分累积
    pet_commands = PetCommands(None)
    pet_commands.update_pet_points(str(interaction.user.id))
    
    # 卸下宠物
    c.execute("""
        UPDATE users 
        SET equipped_pet_id = NULL, last_pet_points_update = NULL 
        WHERE user_id = %s
    """, (str(interaction.user.id),))
    
    conn.commit()
    c.close()
    conn.close()
    
    embed = create_embed(
        "📤 卸下成功！",
        f"{interaction.user.mention} 成功卸下了 **{pet_name}**！\n\n"
        f"你可以装备其他宠物来继续获取积分。",
        discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)

async def handle_pet_status(interaction: discord.Interaction):
    """查看装备状态"""
    conn = get_connection()
    c = conn.cursor()
    
    # 获取用户装备信息
    c.execute("""
        SELECT u.equipped_pet_id, u.points, p.pet_name, p.rarity, p.stars
        FROM users u
        LEFT JOIN pets p ON u.equipped_pet_id = p.pet_id
        WHERE u.user_id = %s
    """, (str(interaction.user.id),))
    
    result = c.fetchone()
    if not result:
        embed = create_embed(
            "❌ 用户不存在",
            f"{interaction.user.mention} 无法获取你的信息！",
            discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        c.close()
        conn.close()
        return
    
    equipped_pet_id, current_points, pet_name, rarity, stars = result
    
    if not equipped_pet_id:
        embed = create_embed(
            "👀 装备状态",
            f"{interaction.user.mention} 你当前没有装备任何宠物！\n\n"
            f"💰 **当前积分：** {current_points}\n\n"
            f"使用 `/pet equip` 来装备一只宠物开始获取积分吧！",
            discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        c.close()
        conn.close()
        return
    
    # 计算每小时积分和待领取积分
    pet_commands = PetCommands(None)
    hourly_points = pet_commands.calculate_pet_points(rarity, stars, 1)
    pending_points = pet_commands.calculate_pending_points(str(interaction.user.id))
    
    star_display = '⭐' * stars if stars > 0 else '⚪'
    rarity_colors = {'C': '🤍', 'R': '💙', 'SR': '💜', 'SSR': '💛'}
    rarity_color = rarity_colors.get(rarity, '🤍')
    
    embed = create_embed(
        "👀 装备状态",
        f"{interaction.user.mention} 的宠物装备状态：\n\n"
        f"🐾 **装备宠物：** {pet_name}\n"
        f"{rarity_color} **稀有度：** {rarity}\n"
        f"{star_display} **星级：** {stars}\n"
        f"💰 **每小时积分：** {hourly_points}\n"
        f"⏰ **待领取积分：** {pending_points}\n"
        f"💎 **当前总积分：** {current_points}\n\n"
        f"💡 使用 `/pet claim` 来领取你的宠物积分！",
        discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)
    c.close()
    conn.close()

async def handle_pet_claim_points(interaction: discord.Interaction):
    """领取宠物积分"""
    conn = get_connection()
    c = conn.cursor()
    
    # 查询用户的装备宠物信息
    c.execute("""
        SELECT u.equipped_pet_id, u.points, p.pet_name, p.rarity, p.stars
        FROM users u
        LEFT JOIN pets p ON u.equipped_pet_id = p.pet_id
        WHERE u.user_id = %s
    """, (str(interaction.user.id),))
    
    result = c.fetchone()
    
    if not result:
        embed = create_embed(
            "❌ 用户不存在",
            "请先使用任何命令来初始化你的账户！",
            discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        c.close()
        conn.close()
        return
    
    equipped_pet_id, current_points, pet_name, rarity, stars = result
    
    # 使用新方法计算待领取积分
    pet_commands = PetCommands(None)
    pending_points = pet_commands.calculate_pending_points(str(interaction.user.id))
    
    if not equipped_pet_id:
        embed = create_embed(
            "❌ 没有装备宠物",
            f"{interaction.user.mention} 你当前没有装备任何宠物！\n\n"
            f"💰 **当前积分：** {current_points}\n\n"
            f"使用 `/pet equip` 来装备一只宠物开始获取积分吧！",
            discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        c.close()
        conn.close()
        return
    
    if pending_points <= 0:
        star_display = '⭐' * stars if stars > 0 else '⚪'
        rarity_colors = {'C': '🤍', 'R': '💙', 'SR': '💜', 'SSR': '💛'}
        rarity_color = rarity_colors.get(rarity, '🤍')
        
        embed = create_embed(
            "💰 没有可领取的积分",
            f"{interaction.user.mention} 当前没有可领取的积分！\n\n"
            f"🐾 **装备宠物：** {pet_name}\n"
            f"{rarity_color} **稀有度：** {rarity}\n"
            f"{star_display} **星级：** {stars}\n"
            f"💎 **当前积分：** {current_points}\n\n"
            f"💡 宠物会随着时间自动累积积分，请稍后再来领取！",
            discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)
        c.close()
        conn.close()
        return
    
    # 领取积分
    new_total_points = current_points + pending_points
    now = datetime.datetime.now()
    
    c.execute("""
        UPDATE users 
        SET points = %s, last_pet_points_update = %s
        WHERE user_id = %s
    """, (new_total_points, now, str(interaction.user.id)))
    
    conn.commit()
    
    star_display = '⭐' * stars if stars > 0 else '⚪'
    rarity_colors = {'C': '🤍', 'R': '💙', 'SR': '💜', 'SSR': '💛'}
    rarity_color = rarity_colors.get(rarity, '🤍')
    
    embed = create_embed(
        "💰 积分领取成功！",
        f"{interaction.user.mention} 成功领取了宠物积分！\n\n"
        f"🐾 **装备宠物：** {pet_name}\n"
        f"{rarity_color} **稀有度：** {rarity}\n"
        f"{star_display} **星级：** {stars}\n"
        f"✨ **领取积分：** +{pending_points}\n"
        f"💎 **当前总积分：** {new_total_points}\n\n"
        f"🎉 继续让你的宠物为你赚取更多积分吧！",
        discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)
    c.close()
    conn.close()

def setup(bot):
    """注册斜杠命令"""
    bot.tree.add_command(pet)