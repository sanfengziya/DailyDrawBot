import discord
from discord.ext import commands
from discord import app_commands
import random
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

# 主宠物命令
@app_commands.command(name="pet", description="🐾 宠物系统 - 查看、升星、分解")
@app_commands.guild_only()
@app_commands.describe(
    action="选择操作类型",
    pet_id="宠物ID（查看详情、升星、分解时需要）",
    page="页码（查看列表时使用，默认第1页）"
)
@app_commands.choices(action=[
    app_commands.Choice(name="📋 查看宠物列表", value="list"),
    app_commands.Choice(name="🔍 查看宠物详情", value="info"),
    app_commands.Choice(name="⭐ 升星宠物", value="upgrade"),
    app_commands.Choice(name="💥 分解宠物", value="dismantle"),
    app_commands.Choice(name="🧩 查看碎片库存", value="fragments")
])
async def pet(interaction: discord.Interaction, action: str, pet_id: int = None, page: int = 1):
    """宠物系统主命令"""
    if action == "list":
        await handle_pet_list(interaction, page)
    elif action == "info":
        if pet_id is None:
            embed = create_embed(
                "❌ 参数错误",
                "查看宠物详情需要提供宠物ID！",
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await handle_pet_info(interaction, pet_id)
    elif action == "upgrade":
        if pet_id is None:
            embed = create_embed(
                "❌ 参数错误",
                "升星宠物需要提供宠物ID！",
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await handle_pet_upgrade(interaction, pet_id)
    elif action == "dismantle":
        if pet_id is None:
            embed = create_embed(
                "❌ 参数错误",
                "分解宠物需要提供宠物ID！",
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await handle_pet_dismantle(interaction, pet_id)
    elif action == "fragments":
        await handle_pet_fragments(interaction)

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
    """, (interaction.user.id, per_page, offset))
    
    pets = c.fetchall()
    
    # 获取总数
    c.execute("SELECT COUNT(*) FROM pets WHERE user_id = %s", (interaction.user.id,))
    total_pets = c.fetchone()[0]
    
    c.close()
    conn.close()
    
    if not pets:
        embed = create_embed(
            "🐾 我的宠物",
            "你还没有任何宠物呢！快去抽蛋孵化吧！",
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
        f"🐾 我的宠物 (第 {page}/{total_pages} 页)",
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
    """, (pet_id, interaction.user.id))
    
    result = c.fetchone()
    c.close()
    conn.close()
    
    if not result:
        embed = create_embed(
            "❌ 错误",
            "找不到这只宠物或者它不属于你！",
            discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        return
    
    pet_name, rarity, stars, max_stars, created_at = result
    
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
        f"{rarity_colors[rarity]} {pet_name}",
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
    """, (pet_id, interaction.user.id))
    
    result = c.fetchone()
    if not result:
        embed = create_embed(
            "❌ 错误",
            "找不到这只宠物或者它不属于你！",
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
            f"{pet_name} 已经达到最大星级了！",
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
    """, (rarity, interaction.user.id))
    
    resource_result = c.fetchone()
    if not resource_result:
        embed = create_embed(
            "❌ 错误",
            "无法获取你的资源信息！",
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
            f"升星需要 {required_points} 积分，你只有 {points} 积分！",
            discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        c.close()
        conn.close()
        return
    
    if fragments < required_fragments:
        embed = create_embed(
            "🧩 碎片不足",
            f"升星需要 {required_fragments} 个 {rarity} 碎片，你只有 {fragments} 个！",
            discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        c.close()
        conn.close()
        return
    
    # 执行升星
    # 扣除积分
    c.execute("UPDATE users SET points = points - %s WHERE user_id = %s", 
             (required_points, interaction.user.id))
    
    # 扣除碎片
    c.execute("""
        UPDATE pet_fragments 
        SET amount = amount - %s 
        WHERE user_id = %s AND rarity = %s
    """, (required_fragments, interaction.user.id, rarity))
    
    # 升星
    c.execute("UPDATE pets SET stars = stars + 1 WHERE pet_id = %s", (pet_id,))
    
    conn.commit()
    c.close()
    conn.close()
    
    new_stars = stars + 1
    star_display = '⭐' * new_stars
    
    embed = create_embed(
        "🌟 升星成功！",
        f"**{pet_name}** 成功升星！\n"
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
    """, (pet_id, interaction.user.id))
    
    result = c.fetchone()
    if not result:
        embed = create_embed(
            "❌ 错误",
            "找不到这只宠物或者它不属于你！",
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
        f"你确定要分解 **{pet_name}** 吗？\n\n"
        f"**分解收益：**\n"
        f"🧩 {total_fragments} 个 {rarity} 碎片\n"
        f"💰 {total_points} 积分\n\n"
        f"**注意：分解后无法恢复！**",
        discord.Color.orange()
    )
    
    view = DismantleConfirmView(interaction.user.id, pet_id, pet_name, rarity, total_fragments, total_points)
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
    """, (interaction.user.id,))
    
    fragments = c.fetchall()
    c.close()
    conn.close()
    
    if not fragments:
        embed = create_embed(
            "🧩 我的碎片",
            "你还没有任何碎片呢！分解宠物可以获得碎片！",
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
        "🧩 我的碎片",
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
        if interaction.user.id != self.user_id:
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
                "宠物不存在或已被分解！",
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
            f"**{self.pet_name}** 已被分解！\n\n"
            f"**获得：**\n"
            f"🧩 {self.fragments} 个 {self.rarity} 碎片\n"
            f"💰 {self.points} 积分",
            discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label='取消', style=discord.ButtonStyle.secondary, emoji='❌')
    async def cancel_dismantle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("这不是你的分解确认界面！", ephemeral=True)
            return
        
        embed = create_embed(
            "✅ 已取消",
            "分解操作已取消。",
            discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=None)

def setup(bot):
    """注册斜杠命令"""
    bot.tree.add_command(pet)
    bot.add_cog(PetCommands(bot))