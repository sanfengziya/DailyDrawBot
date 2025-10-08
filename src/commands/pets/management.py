import discord
from discord.ext import commands
from discord import app_commands
import datetime
from src.utils.ui import create_embed
from src.utils.helpers import get_user_internal_id
from src.utils.cache import UserCache

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
        try:
            from src.db.database import get_supabase_client
            supabase = get_supabase_client()
            
            # 先查询是否存在
            existing = supabase.table('user_pet_fragments').select('amount').eq('user_id', player_id).eq('rarity', rarity).execute()
            
            if existing.data:
                # 更新现有记录
                new_amount = existing.data[0]['amount'] + amount
                supabase.table('user_pet_fragments').update({'amount': new_amount}).eq('user_id', player_id).eq('rarity', rarity).execute()
            else:
                # 插入新记录
                supabase.table('user_pet_fragments').insert({'user_id': player_id, 'rarity': rarity, 'amount': amount}).execute()
                
        except Exception as e:
            print(f"添加碎片时出错：{str(e)}")
    
    def calculate_pet_points(self, rarity, stars, hours, level=1):
        """计算宠物积分获取量（包含等级里程碑奖励）"""
        base_points = self.PET_POINTS_PER_HOUR.get(rarity, 0)

        # 等级里程碑奖励：每到3的倍数等级，基础积分+1
        level_bonus = level // 3  # 3级+1，6级+2，9级+3，等等
        adjusted_base_points = base_points + level_bonus

        multiplier = stars + 1
        return int(adjusted_base_points * multiplier * hours)
    
    def update_pet_points(self, user_id):
        """更新装备宠物的时间戳（用于积分计算）"""
        try:
            from src.db.database import get_supabase_client
            supabase = get_supabase_client()
            
            # 检查用户是否有装备的宠物
            user_response = supabase.table('users').select('equipped_pet_id').eq('id', user_id).not_.is_('equipped_pet_id', None).execute()
            
            if not user_response.data:
                return
            
            # 更新最后更新时间为当前时间
            now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
            supabase.table('users').update({'last_pet_points_update': now}).eq('id', user_id).execute()
            
        except Exception as e:
            print(f"更新宠物积分时间戳时出错：{str(e)}")

    def calculate_pending_points(self, user_id):
        """基于时间差计算待领取的宠物积分（最多累积24小时）"""
        try:
            from src.db.database import get_supabase_client
            supabase = get_supabase_client()
            
            # 获取用户装备的宠物信息和上次更新时间
            user_pet_response = supabase.table('users').select('equipped_pet_id, last_pet_points_update').eq('id', user_id).not_.is_('equipped_pet_id', None).execute()
            
            if not user_pet_response.data:
                return 0
            
            user_data = user_pet_response.data[0]
            equipped_pet_id = user_data['equipped_pet_id']
            last_update = user_data['last_pet_points_update']
            
            # 获取宠物信息
            pet_response = supabase.table('user_pets').select('pet_template_id, stars, level').eq('id', equipped_pet_id).execute()
            
            if not pet_response.data:
                return 0
            
            pet_data = pet_response.data[0]
            pet_template_id = pet_data['pet_template_id']
            stars = pet_data['stars']
            level = pet_data['level']
            
            # 获取宠物模板信息
            template_response = supabase.table('pet_templates').select('rarity').eq('id', pet_template_id).execute()
            if not template_response.data:
                return 0
            
            rarity = template_response.data[0]['rarity']
            
            # 计算时间差（小时）
            now = datetime.datetime.now(datetime.timezone.utc)
            if last_update:
                # 解析ISO格式的时间戳
                last_update_dt = datetime.datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                time_diff = now - last_update_dt
                hours = time_diff.total_seconds() / 3600
            else:
                # 如果没有记录，说明刚装备，返回0
                return 0
            
            # 限制最多累积24小时的积分
            max_hours = 24
            actual_hours = min(hours, max_hours)
            
            # 如果时间差小于0.1小时（6分钟），返回0
            if actual_hours < 0.1:
                return 0
            
            # 计算获得的积分
            pending_points = self.calculate_pet_points(rarity, stars, actual_hours, level)
            
            return int(pending_points)
            
        except Exception as e:
            print(f"计算待领取积分时出错：{str(e)}")
            return 0

# 宠物选择视图
class PetSelectView(discord.ui.View):
    def __init__(self, user_id: int, action: str):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.action = action
        
    async def setup_select(self):
        """设置宠物选择下拉菜单"""
        try:
            from src.db.database import get_supabase_client
            supabase = get_supabase_client()
            
            # 查询用户的宠物
            pets_response = supabase.table('user_pets').select('id, pet_template_id, stars').eq('user_id', self.user_id).order('stars', desc=True).limit(25).execute()
            
            if not pets_response.data:
                return False
            
            # 获取所有宠物模板信息
            template_ids = list(set([pet['pet_template_id'] for pet in pets_response.data]))
            templates_response = supabase.table('pet_templates').select('id, name, rarity').in_('id', template_ids).execute()
            
            # 创建模板映射
            template_map = {template['id']: template for template in templates_response.data}
            
            pets = []
            for pet in pets_response.data:
                template = template_map.get(pet['pet_template_id'])
                if template:
                    pets.append((pet['id'], template['name'], template['rarity'], pet['stars']))
            
            # 按稀有度和星级排序
            rarity_order = {'SSR': 4, 'SR': 3, 'R': 2, 'C': 1}
            pets.sort(key=lambda x: (rarity_order.get(x[2], 0), x[3], x[1]), reverse=True)
            
        except Exception as e:
            print(f"设置宠物选择菜单时出错：{str(e)}")
            return False
            
        # 稀有度颜色映射
        rarity_emojis = {
            "C": "⚪",
            "R": "🔵", 
            "SR": "🟣",
            "SSR": "🟡",
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
            "equip": "装备",
            "feed": "喂食"
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
        elif self.action == "feed":
            await handle_pet_feed(interaction, pet_id)

# 主宠物命令
@app_commands.command(name="pet", description="🐾 宠物系统 - 查看、升星、分解")
@app_commands.guild_only()
@app_commands.describe(
    action="选择操作类型",
    page="页码（查看列表时使用，默认第1页）"
)
@app_commands.choices(action=[
    app_commands.Choice(name="查看列表", value="list"),
    app_commands.Choice(name="查看详情", value="info"),
    app_commands.Choice(name="升星", value="upgrade"),
    app_commands.Choice(name="分解", value="dismantle"),
    app_commands.Choice(name="查看碎片", value="fragments"),
    app_commands.Choice(name="装备", value="equip"),
    app_commands.Choice(name="卸下", value="unequip"),
    app_commands.Choice(name="装备状态", value="status"),
    app_commands.Choice(name="领取积分", value="claim"),
    app_commands.Choice(name="喂食", value="feed"),
])
async def pet(interaction: discord.Interaction, action: str, page: int = 1):
    """宠物系统主命令"""
    if action == "list":
        await handle_pet_list(interaction, page)
    elif action in ["info", "upgrade", "dismantle", "equip", "feed"]:
        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed("❌ 错误", "用户不存在，请先使用抽卡功能注册！", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 显示宠物选择界面
        view = PetSelectView(user_internal_id, action)
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
            "equip": "装备宠物",
            "feed": "喂食宠物"
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
    try:
        from src.db.database import get_supabase_client
        supabase = get_supabase_client()
        
        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed("❌ 错误", "用户不存在，请先使用抽卡功能注册！", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # 分页查询
        per_page = 10
        offset = (page - 1) * per_page
        
        # 查询宠物列表 - 先获取用户宠物，然后获取模板和稀有度配置
        pets_response = supabase.table('user_pets').select('id, pet_template_id, stars, created_at').eq('user_id', user_internal_id).order('created_at', desc=True).range(offset, offset + per_page - 1).execute()
        
        # 获取总数
        count_response = supabase.table('user_pets').select('id', count='exact').eq('user_id', user_internal_id).execute()
        total_pets = count_response.count
        
        if not pets_response.data:
            embed = create_embed(
                "🐾 我的宠物",
                f"{interaction.user.mention} 你还没有任何宠物呢！快去抽蛋孵化吧！",
                discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        # 获取所有相关的宠物模板
        template_ids = list(set([pet['pet_template_id'] for pet in pets_response.data]))
        templates_response = supabase.table('pet_templates').select('id, name, rarity').in_('id', template_ids).execute()
        templates_dict = {template['id']: template for template in templates_response.data}
        
        # 获取稀有度配置
        rarities = list(set([template['rarity'] for template in templates_response.data]))
        rarity_configs_response = supabase.table('pet_rarity_configs').select('rarity, max_stars').in_('rarity', rarities).execute()
        rarity_configs_dict = {config['rarity']: config for config in rarity_configs_response.data}
        
        # 组合数据并按稀有度和星级排序
        pets_data = []
        for pet in pets_response.data:
            template = templates_dict.get(pet['pet_template_id'])
            if template:
                rarity_config = rarity_configs_dict.get(template['rarity'])
                max_stars = rarity_config['max_stars'] if rarity_config else 0
                pets_data.append({
                    'id': pet['id'],
                    'name': template['name'],
                    'rarity': template['rarity'],
                    'stars': pet['stars'],
                    'max_stars': max_stars,
                    'created_at': pet['created_at']
                })
        
        # 按稀有度和星级排序
        rarity_order = {'SSR': 1, 'SR': 2, 'R': 3, 'C': 4}
        pets_data.sort(key=lambda x: (rarity_order.get(x['rarity'], 5), -x['stars'], x['created_at']), reverse=False)
        
        pets = [(pet['id'], pet['name'], pet['rarity'], pet['stars'], pet['max_stars'], pet['created_at']) for pet in pets_data]
        
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
        
    except Exception as e:
        embed = create_embed(
            "❌ 错误",
            f"查询宠物列表时出错：{str(e)}",
            discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    embed = create_embed(
        title="宠物查询",
        description=f"{interaction.user.mention} 的宠物 (第 {page}/{total_pages} 页)\n {description}",
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"总共 {total_pets} 只宠物")
    await interaction.response.send_message(embed=embed)

async def handle_pet_info(interaction: discord.Interaction, pet_id: int):
    """查看宠物详情"""
    try:
        from src.db.database import get_supabase_client
        supabase = get_supabase_client()
        
        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed("❌ 错误", "用户不存在，请先使用抽卡功能注册！", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # 查询宠物基本信息
        pet_response = supabase.table('user_pets').select('id, pet_template_id, stars, created_at, level, xp_current, xp_total, satiety, favorite_flavor, dislike_flavor').eq('id', pet_id).eq('user_id', user_internal_id).execute()
        
        if not pet_response.data:
            embed = create_embed(
                "❌ 错误",
                f"{interaction.user.mention} 找不到这只宠物或者它不属于你！",
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return

        pet_data = pet_response.data[0]
        
        # 获取宠物模板信息
        template_response = supabase.table('pet_templates').select('name, rarity').eq('id', pet_data['pet_template_id']).execute()
        if not template_response.data:
            embed = create_embed("❌ 错误", "宠物模板不存在！", discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        template_data = template_response.data[0]
        
        # 获取稀有度配置
        rarity_response = supabase.table('pet_rarity_configs').select('max_stars').eq('rarity', template_data['rarity']).execute()
        if not rarity_response.data:
            embed = create_embed("❌ 错误", "稀有度配置不存在！", discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        pet_name = template_data['name']
        rarity = template_data['rarity']
        stars = pet_data['stars']
        max_stars = rarity_response.data[0]['max_stars']
        created_at = pet_data['created_at']
    
    except Exception as e:
        embed = create_embed(
            "❌ 错误",
            f"查询宠物信息时出错：{str(e)}",
            discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
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
    
    # 获取宠物的等级、经验和饱食度信息
    level = pet_data['level']
    xp_current = pet_data['xp_current']
    xp_total = pet_data['xp_total']
    satiety = pet_data['satiety']
    favorite_flavor = pet_data['favorite_flavor']
    dislike_flavor = pet_data['dislike_flavor']
    
    # 口味表情映射（与喂食界面保持一致）
    flavor_emojis = {
        'SWEET': '🍯 甜味',
        'SALTY': '🧂 咸味',
        'SOUR': '🍋 酸味',
        'SPICY': '🌶️ 辣味',
        'UMAMI': '🍄 鲜味'
    }
    
    # 计算升级所需经验（使用与喂食系统一致的公式）
    from src.utils.feeding_system import FeedingSystem
    xp_needed_for_next_level = FeedingSystem.calculate_level_xp_requirement(level)
    
    # 计算经验进度条
    progress_bar_length = 10
    if xp_needed_for_next_level > 0:
        progress = min(xp_current / xp_needed_for_next_level, 1.0)
        filled_blocks = int(progress * progress_bar_length)
        progress_bar = "█" * filled_blocks + "░" * (progress_bar_length - filled_blocks)
        progress_percent = int(progress * 100)
    else:
        progress_bar = "█" * progress_bar_length
        progress_percent = 100
    
    # 饱食度进度条
    satiety_progress = satiety / 100
    satiety_filled = int(satiety_progress * progress_bar_length)
    satiety_bar = "🟢" * satiety_filled + "⚪" * (progress_bar_length - satiety_filled)
    
    # 口味偏好显示
    favorite_flavor_display = flavor_emojis.get(favorite_flavor, '无偏好')
    dislike_flavor_display = flavor_emojis.get(dislike_flavor, '无')
    
    # 构建描述内容
    description = f"{interaction.user.mention} 的 {rarity_colors[rarity]} **{pet_name}**\n\n"
    
    # 基本信息
    description += f"🆔 **宠物ID：** {pet_id}\n"
    description += f"💎 **稀有度：** {rarity}\n"
    description += f"⭐ **星级：** {star_display} ({stars}/{max_stars})\n\n"
    
    # 等级和经验
    description += f"📊 **等级：** {level}\n"
    description += f"✨ **经验：** {xp_current}/{xp_needed_for_next_level}\n"
    description += f"📈 {progress_bar} {progress_percent}%\n\n"
    
    # 饱食度
    description += f"🍽️ **饱食度：** {satiety}/100\n"
    description += f"📊 {satiety_bar} {satiety}%\n\n"
    
    # 口味偏好
    description += f"💖 **喜欢：** {favorite_flavor_display}\n"
    description += f"💔 **讨厌：** {dislike_flavor_display}\n\n"
    
    # 总经验和获得时间
    description += f"🏆 **总经验：** {xp_total}\n"
    description += f"📅 **获得时间：** {(datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00')) if isinstance(created_at, str) else created_at).strftime('%Y-%m-%d')}\n"
    
    # 升星信息
    description += f"{upgrade_info}"

    embed = create_embed(
        "🐾 宠物信息",
        description,
        discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

async def handle_pet_upgrade(interaction: discord.Interaction, pet_id: int):
    """升星宠物"""
    try:
        from src.db.database import get_supabase_client
        supabase = get_supabase_client()
        
        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed("❌ 错误", "用户不存在，请先使用抽卡功能注册！", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # 获取宠物信息
        pet_response = supabase.table('user_pets').select('id, pet_template_id, stars').eq('id', pet_id).eq('user_id', user_internal_id).execute()
        
        if not pet_response.data:
            embed = create_embed(
                "❌ 错误",
                f"{interaction.user.mention} 找不到这只宠物或者它不属于你！",
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        pet_data = pet_response.data[0]
        
        # 获取宠物模板信息
        template_response = supabase.table('pet_templates').select('name, rarity').eq('id', pet_data['pet_template_id']).execute()
        if not template_response.data:
            embed = create_embed("❌ 错误", "宠物模板不存在！", discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        template_data = template_response.data[0]
        
        # 获取稀有度配置
        rarity_response = supabase.table('pet_rarity_configs').select('max_stars').eq('rarity', template_data['rarity']).execute()
        if not rarity_response.data:
            embed = create_embed("❌ 错误", "稀有度配置不存在！", discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        pet_name = template_data['name']
        rarity = template_data['rarity']
        stars = pet_data['stars']
        max_stars = rarity_response.data[0]['max_stars']
        
        if stars >= max_stars:
            embed = create_embed(
                "⭐ 已满星",
                f"{interaction.user.mention} 你的 {pet_name} 已经达到最大星级了！",
                discord.Color.yellow()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        # 获取升星费用
        cost = PetCommands.UPGRADE_COSTS[stars]
        required_fragments = cost['fragments']
        required_points = cost['points']
        
        # 检查用户积分
        user_response = supabase.table('users').select('points').eq('id', user_internal_id).execute()
        if not user_response.data:
            embed = create_embed(
                "❌ 错误",
                f"{interaction.user.mention} 无法获取你的资源信息！",
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        points = user_response.data[0]['points']
        
        # 检查用户碎片
        fragments_response = supabase.table('user_pet_fragments').select('amount').eq('user_id', user_internal_id).eq('rarity', rarity).execute()
        fragments = fragments_response.data[0]['amount'] if fragments_response.data else 0
        
        if points < required_points:
            embed = create_embed(
                "💰 积分不足",
                f"{interaction.user.mention} 升星需要 {required_points} 积分，你只有 {points} 积分！",
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        if fragments < required_fragments:
            embed = create_embed(
                "🧩 碎片不足",
                f"{interaction.user.mention} 升星需要 {required_fragments} 个 {rarity} 碎片，你只有 {fragments} 个！",
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        # 执行升星
        # 扣除积分
        supabase.table('users').update({'points': points - required_points}).eq('id', user_internal_id).execute()

        # 清除积分缓存，确保check命令显示最新数据
        guild_id = interaction.guild.id
        discord_user_id = interaction.user.id
        await UserCache.invalidate_points_cache(guild_id, discord_user_id)

        # 扣除碎片
        supabase.table('user_pet_fragments').update({'amount': fragments - required_fragments}).eq('user_id', user_internal_id).eq('rarity', rarity).execute()
        
        # 升星
        supabase.table('user_pets').update({'stars': stars + 1}).eq('id', pet_id).execute()
        
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
        
    except Exception as e:
        embed = create_embed(
            "❌ 错误",
            f"升星宠物时出错：{str(e)}",
            discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
        return

async def handle_pet_dismantle(interaction: discord.Interaction, pet_id: int):
    """分解宠物"""
    try:
        from src.db.database import get_supabase_client
        supabase = get_supabase_client()
        
        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed("❌ 错误", "用户不存在，请先使用抽卡功能注册！", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # 检查宠物是否正在装备
        user_response = supabase.table('users').select('equipped_pet_id').eq('id', user_internal_id).execute()
        if user_response.data and user_response.data[0]['equipped_pet_id'] == pet_id:
            embed = create_embed(
                "❌ 错误",
                f"{interaction.user.mention} 不能分解正在装备的宠物！请先卸下宠物再进行分解。",
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return

        # 获取宠物信息
        pet_response = supabase.table('user_pets').select('pet_template_id, stars').eq('id', pet_id).eq('user_id', user_internal_id).execute()
        
        if not pet_response.data:
            embed = create_embed(
                "❌ 错误",
                f"{interaction.user.mention} 找不到这只宠物或者它不属于你！",
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        pet_data = pet_response.data[0]
        pet_template_id = pet_data['pet_template_id']
        stars = pet_data['stars']
        
        # 获取宠物模板信息
        template_response = supabase.table('pet_templates').select('name, rarity').eq('id', pet_template_id).execute()
        if not template_response.data:
            embed = create_embed("❌ 错误", "宠物模板不存在！", discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        template_data = template_response.data[0]
        pet_name = template_data['name']
        rarity = template_data['rarity']
        
    except Exception as e:
        embed = create_embed(
            "❌ 错误",
            f"{interaction.user.mention} 查询宠物信息时出错了！",
            discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
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

    view = DismantleConfirmView(
        interaction.guild.id,
        interaction.user.id,
        user_internal_id,
        pet_id,
        pet_name,
        rarity,
        total_fragments,
        total_points
    )
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def handle_pet_fragments(interaction: discord.Interaction):
    """查看碎片库存"""
    try:
        from src.db.database import get_supabase_client
        supabase = get_supabase_client()
        
        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed("❌ 错误", "用户不存在，请先使用抽卡功能注册！", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # 查询碎片库存
        response = supabase.table('user_pet_fragments').select('rarity, amount').eq('user_id', user_internal_id).gt('amount', 0).execute()
        
        fragments = response.data
        
        # 手动排序（Supabase不支持复杂的CASE排序）
        rarity_order = {'SSR': 1, 'SR': 2, 'R': 3, 'C': 4}
        fragments.sort(key=lambda x: rarity_order.get(x['rarity'], 5))
        
    except Exception as e:
        embed = create_embed(
            "❌ 错误",
            f"{interaction.user.mention} 查询碎片库存时出错了！",
            discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
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
    for fragment in fragments:
        rarity = fragment['rarity']
        amount = fragment['amount']
        description += f"{rarity_colors[rarity]} **{rarity} 碎片：** {amount} 个\n"
    
    embed = create_embed(
        title="🧩 我的碎片",
        description=f"{interaction.user.mention} 的碎片\n {description}",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed)

class DismantleConfirmView(discord.ui.View):
    def __init__(self, guild_id, discord_user_id, user_internal_id, pet_id, pet_name, rarity, fragments, points):
        super().__init__(timeout=30)
        self.guild_id = guild_id  # 服务器ID，用于 UserCache
        self.discord_user_id = discord_user_id  # 用于验证用户身份（int 类型）
        self.user_internal_id = user_internal_id  # 用于数据库操作
        self.pet_id = pet_id
        self.pet_name = pet_name
        self.rarity = rarity
        self.fragments = fragments
        self.points = points

    @discord.ui.button(label='确认分解', style=discord.ButtonStyle.danger, emoji='💥')
    async def confirm_dismantle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.discord_user_id:
            await interaction.response.send_message("这不是你的分解确认界面！", ephemeral=True)
            return
        
        try:
            from src.db.database import get_supabase_client
            supabase = get_supabase_client()
            
            # 删除宠物
            delete_response = supabase.table('user_pets').delete().eq('id', self.pet_id).eq('user_id', self.user_internal_id).execute()
            
            if not delete_response.data:
                embed = create_embed(
                    "❌ 错误",
                    f"{interaction.user.mention} 宠物不存在或已被分解！",
                    discord.Color.red()
                )
                await interaction.response.edit_message(embed=embed, view=None)
                return
            
            # 检查是否已有该稀有度的碎片记录
            fragment_response = supabase.table('user_pet_fragments').select('amount').eq('user_id', self.user_internal_id).eq('rarity', self.rarity).execute()
            
            if fragment_response.data:
                # 更新现有碎片数量
                current_amount = fragment_response.data[0]['amount']
                new_amount = current_amount + self.fragments
                supabase.table('user_pet_fragments').update({'amount': new_amount}).eq('user_id', self.user_internal_id).eq('rarity', self.rarity).execute()
            else:
                # 插入新的碎片记录
                supabase.table('user_pet_fragments').insert({
                    'user_id': self.user_internal_id,
                    'rarity': self.rarity,
                    'amount': self.fragments
                }).execute()
            
            # 添加积分（使用 UserCache 保证缓存一致性）
            if self.points > 0:
                from src.utils.cache import UserCache
                await UserCache.update_points(
                    self.guild_id,
                    self.discord_user_id,
                    self.user_internal_id,
                    self.points  # 增加积分
                )
                    
        except Exception as e:
            embed = create_embed(
                "❌ 错误",
                f"{interaction.user.mention} 分解宠物时出错了！",
                discord.Color.red()
            )
            await interaction.response.edit_message(embed=embed, view=None)
            return
        
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
        if interaction.user.id != self.discord_user_id:
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
    try:
        from src.db.database import get_supabase_client
        supabase = get_supabase_client()
        
        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed("❌ 错误", "用户不存在，请先使用抽卡功能注册！", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # 检查宠物是否存在且属于用户
        pet_response = supabase.table('user_pets').select('pet_template_id, stars, level').eq('id', pet_id).eq('user_id', user_internal_id).execute()
        
        if not pet_response.data:
            embed = create_embed(
                "❌ 错误",
                f"{interaction.user.mention} 找不到这只宠物或者它不属于你！",
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        pet_data = pet_response.data[0]
        pet_template_id = pet_data['pet_template_id']
        stars = pet_data['stars']
        level = pet_data['level']

        # 获取宠物模板信息
        template_response = supabase.table('pet_templates').select('name, rarity').eq('id', pet_template_id).execute()
        if not template_response.data:
            embed = create_embed("❌ 错误", "宠物模板不存在！", discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return

        template_data = template_response.data[0]
        pet_name = template_data['name']
        rarity = template_data['rarity']

        # 检查是否已经装备了这只宠物
        equipped_response = supabase.table('users').select('equipped_pet_id').eq('id', user_internal_id).execute()
        
        current_equipped_id = None
        if equipped_response.data:
            current_equipped_id = equipped_response.data[0]['equipped_pet_id']
        
        if current_equipped_id == pet_id:
            embed = create_embed(
                "⚠️ 已装备",
                f"{interaction.user.mention} 你已经装备了 **{pet_name}**！",
                discord.Color.yellow()
            )
            await interaction.response.send_message(embed=embed)
            return
            
    except Exception as e:
        embed = create_embed(
            "❌ 错误",
            f"{interaction.user.mention} 装备宠物时出错了！",
            discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    # 检查是否有待领取的积分
    pet_commands = PetCommands(None)
    pending_points = pet_commands.calculate_pending_points(user_internal_id)
    if pending_points > 0:
        embed = create_embed(
            "⚠️ 请先领取积分",
            f"{interaction.user.mention} 你有 **{pending_points}** 点待领取的宠物积分！\n\n"
            f"请先使用 `/pet claim` 领取积分，然后再更换宠物。",
            discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        return
    
    # 如果有其他宠物装备，先更新积分累积
    if current_equipped_id:
        pet_commands = PetCommands(None)
        pet_commands.update_pet_points(user_internal_id)
    
    # 装备新宠物
    now = datetime.datetime.now(datetime.timezone.utc)
    supabase.table('users').update({
        'equipped_pet_id': pet_id,
        'last_pet_points_update': now.isoformat(timespec='seconds')
    }).eq('id', user_internal_id).execute()
    
    # 计算每小时积分和待领取积分
    pet_commands = PetCommands(None)
    hourly_points = pet_commands.calculate_pet_points(rarity, stars, 1, level)
    pending_points = pet_commands.calculate_pending_points(user_internal_id)
    
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
    try:
        from src.db.database import get_supabase_client
        supabase = get_supabase_client()
        
        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed("❌ 错误", "用户不存在，请先使用抽卡功能注册！", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # 查询用户装备的宠物
        user_response = supabase.table('users').select('equipped_pet_id').eq('id', user_internal_id).execute()
        if not user_response.data:
            embed = create_embed("❌ 错误", "用户信息异常！", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        equipped_pet_id = user_response.data[0]['equipped_pet_id']
        
        if not equipped_pet_id:
            embed = create_embed(
                "❌ 没有装备宠物",
                f"{interaction.user.mention} 你当前没有装备任何宠物！",
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        # 获取装备宠物的详细信息
        pet_response = supabase.table('user_pets').select('stars, pet_templates(name, rarity)').eq('id', equipped_pet_id).execute()
        
        if not pet_response.data:
            embed = create_embed(
                "❌ 错误",
                f"{interaction.user.mention} 装备的宠物信息异常！",
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        pet_data = pet_response.data[0]
        pet_name = pet_data['pet_templates']['name']
        rarity = pet_data['pet_templates']['rarity']
        stars = pet_data['stars']
        
    except Exception as e:
        embed = create_embed(
            "❌ 错误",
            f"{interaction.user.mention} 卸下宠物时出错了！",
            discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    # 检查是否有待领取的积分
    pet_commands = PetCommands(None)
    pending_points = pet_commands.calculate_pending_points(user_internal_id)
    if pending_points > 0:
        embed = create_embed(
            "⚠️ 请先领取积分",
            f"{interaction.user.mention} 你有 **{pending_points}** 点待领取的宠物积分！\n\n"
            f"请先使用 `/pet claim` 领取积分，然后再卸下宠物。",
            discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        return
    
    # 更新积分累积
    pet_commands = PetCommands(None)
    pet_commands.update_pet_points(user_internal_id)
    
    # 卸下宠物
    supabase.table('users').update({
        'equipped_pet_id': None,
        'last_pet_points_update': None
    }).eq('id', user_internal_id).execute()
    
    embed = create_embed(
        "📤 卸下成功！",
        f"{interaction.user.mention} 成功卸下了 **{pet_name}**！\n\n"
        f"你可以装备其他宠物来继续获取积分。",
        discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)

async def handle_pet_status(interaction: discord.Interaction):
    """查看装备状态"""
    try:
        from src.db.database import get_supabase_client
        supabase = get_supabase_client()
        
        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if user_internal_id is None:
            embed = create_embed("❌ 错误", "用户不存在，请先使用抽卡功能注册！", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # 查询用户信息
        user_response = supabase.table('users').select('equipped_pet_id, points').eq('id', user_internal_id).execute()
        if not user_response.data:
            embed = create_embed("❌ 错误", "用户数据异常！", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        user_data = user_response.data[0]
        equipped_pet_id = user_data.get('equipped_pet_id')
        current_points = user_data.get('points', 0)
        
        if not equipped_pet_id:
            embed = create_embed(
                "👀 装备状态",
                f"{interaction.user.mention} 你当前没有装备任何宠物！\n\n"
                f"💰 **当前积分：** {current_points}\n\n"
                f"使用 `/pet equip` 来装备一只宠物开始获取积分吧！",
                discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        # 获取宠物详细信息
        pet_response = supabase.table('user_pets').select('pet_template_id, stars, level').eq('id', equipped_pet_id).execute()
        
        if not pet_response.data:
            embed = create_embed(
                "❌ 宠物不存在",
                f"{interaction.user.mention} 装备的宠物不存在！",
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        pet_data = pet_response.data[0]
        pet_template_id = pet_data['pet_template_id']
        stars = pet_data['stars']
        level = pet_data['level']

        # 获取宠物模板信息
        template_response = supabase.table('pet_templates').select('name, rarity').eq('id', pet_template_id).execute()
        if not template_response.data:
            embed = create_embed("❌ 错误", "宠物模板不存在！", discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return

        template_data = template_response.data[0]
        pet_name = template_data['name']
        rarity = template_data['rarity']

        # 计算每小时积分和待领取积分
        pet_commands = PetCommands(None)
        hourly_points = pet_commands.calculate_pet_points(rarity, stars, 1, level)
        pending_points = pet_commands.calculate_pending_points(user_internal_id)
        
        star_display = '⭐' * stars if stars > 0 else '⚪'
        rarity_colors = {'C': '🤍', 'R': '💙', 'SR': '💜', 'SSR': '💛'}
        rarity_color = rarity_colors.get(rarity, '🤍')
        
        embed = create_embed(
            "👀 装备状态",
            f"{interaction.user.mention} 的宠物装备状态：\n\n"
            f"🐾 **装备宠物：** {pet_name}\n"
            f"{rarity_color} **稀有度：** {rarity}\n"
            f"{star_display} **星级：** {stars}\n"
            f"🔢 **等级：** {level}\n"
            f"💰 **每小时积分：** {hourly_points}\n"
            f"⏰ **待领取积分：** {pending_points}\n"
            f"💎 **当前总积分：** {current_points}\n\n"
            f"💡 使用 `/pet claim` 来领取你的宠物积分！",
            discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        embed = create_embed(
            "❌ 错误",
            f"{interaction.user.mention} 查看装备状态时发生错误！",
            discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)

async def handle_pet_claim_points(interaction: discord.Interaction):
    """领取宠物积分"""
    try:
        from src.db.database import get_supabase_client
        supabase = get_supabase_client()
        
        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if user_internal_id is None:
            embed = create_embed("❌ 错误", "用户不存在，请先使用抽卡功能注册！", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # 查询用户信息
        user_response = supabase.table('users').select('equipped_pet_id, points').eq('id', user_internal_id).execute()
        if not user_response.data:
            embed = create_embed("❌ 错误", "用户数据异常！", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        user_data = user_response.data[0]
        equipped_pet_id = user_data.get('equipped_pet_id')
        current_points = user_data.get('points', 0)
        
        # 获取宠物详细信息（如果有装备宠物）
        pet_name = None
        rarity = None
        stars = None
        
        if equipped_pet_id:
            pet_response = supabase.table('user_pets').select('pet_template_id, stars').eq('id', equipped_pet_id).execute()
            if pet_response.data:
                pet_data = pet_response.data[0]
                pet_template_id = pet_data['pet_template_id']
                stars = pet_data['stars']
                
                # 获取宠物模板信息
                template_response = supabase.table('pet_templates').select('name, rarity').eq('id', pet_template_id).execute()
                if template_response.data:
                    template_data = template_response.data[0]
                    pet_name = template_data['name']
                    rarity = template_data['rarity']
    
        # 使用新方法计算待领取积分
        pet_commands = PetCommands(None)
        pending_points = pet_commands.calculate_pending_points(user_internal_id)
        
        if not equipped_pet_id:
            embed = create_embed(
                "❌ 没有装备宠物",
                f"{interaction.user.mention} 你当前没有装备任何宠物！\n\n"
                f"💰 **当前积分：** {current_points}\n\n"
                f"使用 `/pet equip` 来装备一只宠物开始获取积分吧！",
                discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)
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
            return
        
        # 领取积分
        new_total_points = current_points + pending_points
        now = datetime.datetime.now(datetime.timezone.utc)

        supabase.table('users').update({
            'points': new_total_points,
            'last_pet_points_update': now.isoformat(timespec='seconds')
        }).eq('id', user_internal_id).execute()

        # 清除积分缓存，确保check命令显示最新数据
        guild_id = interaction.guild.id
        discord_user_id = interaction.user.id
        await UserCache.invalidate_points_cache(guild_id, discord_user_id)
        
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
    except Exception as e:
        print(f"领取积分时发生错误：{str(e)}")
        embed = create_embed(
            "❌ 错误",
            f"{interaction.user.mention} 领取积分时发生错误！",
            discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)

async def handle_pet_feed(interaction: discord.Interaction, pet_id: int):
    """处理宠物喂食"""
    from src.utils.feeding_system import get_pet_feeding_info
    from src.utils.helpers import get_user_internal_id

    # 获取用户内部ID
    user_internal_id = get_user_internal_id(interaction)
    if not user_internal_id:
        embed = create_embed("❌ 错误", "用户不存在，请先使用抽卡功能注册！", discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # 获取宠物喂食信息
    pet_info = get_pet_feeding_info(pet_id)
    if not pet_info:
        embed = create_embed("❌ 错误", "宠物不存在或不属于你！", discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # 检查宠物所有权
    if pet_info['user_id'] != user_internal_id:
        embed = create_embed("❌ 错误", "这只宠物不属于你！", discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # 显示宠物喂食界面
    view = PetFeedingView(user_internal_id, pet_id, pet_info)
    embed = view.create_feeding_embed()

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class PetFeedingView(discord.ui.View):
    def __init__(self, user_id: int, pet_id: int, pet_info: dict):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.pet_id = pet_id
        self.pet_info = pet_info

        # 添加食粮选择下拉菜单
        self.add_item(FoodSelectForFeeding(user_id, pet_id))

    def create_feeding_embed(self) -> discord.Embed:
        """创建喂食界面embed"""
        from src.utils.feeding_system import FeedingSystem

        # 稀有度颜色映射
        rarity_colors = {
            'C': '⚪',
            'R': '🔵',
            'SR': '🟣',
            'SSR': '🟡'
        }

        # 口味表情映射
        flavor_emojis = {
            'SWEET': '🍯 甜味',
            'SALTY': '🧂 咸味',
            'SOUR': '🍋 酸味',
            'SPICY': '🌶️ 辣味',
            'UMAMI': '🍄 鲜味'
        }

        rarity_color = rarity_colors.get(self.pet_info['rarity'], '⚪')
        favorite_flavor = flavor_emojis.get(self.pet_info['favorite_flavor'], '无偏好')
        dislike_flavor = flavor_emojis.get(self.pet_info['dislike_flavor'], '无')

        # 计算经验进度条
        progress_bar_length = 10
        if self.pet_info['xp_next_level'] > 0:
            progress = min(self.pet_info['xp_current'] / self.pet_info['xp_next_level'], 1.0)
            filled_blocks = int(progress * progress_bar_length)
            progress_bar = "█" * filled_blocks + "░" * (progress_bar_length - filled_blocks)
        else:
            progress_bar = "█" * progress_bar_length

        # 饱食度进度条
        satiety_progress = self.pet_info['satiety'] / 100
        satiety_filled = int(satiety_progress * progress_bar_length)
        satiety_bar = "🟢" * satiety_filled + "⚪" * (progress_bar_length - satiety_filled)

        description = f"{rarity_color} **{self.pet_info['name']}**\n\n"

        # 基本信息
        description += f"📊 **等级：** {self.pet_info['level']}\n"
        description += f"✨ **经验：** {self.pet_info['xp_current']}/{self.pet_info['xp_next_level']}\n"
        description += f"📈 {progress_bar} {int(progress * 100) if self.pet_info['xp_next_level'] > 0 else 100}%\n\n"

        # 饱食度
        description += f"🍽️ **饱食度：** {self.pet_info['satiety']}/100\n"
        description += f"📊 {satiety_bar} {self.pet_info['satiety']}%\n\n"

        # 口味偏好
        description += f"💖 **喜欢：** {favorite_flavor}\n"
        description += f"💔 **讨厌：** {dislike_flavor}\n\n"

        # 喂食说明
        if self.pet_info['satiety'] >= FeedingSystem.SATIETY_MAX:
            description += "⚠️ **宠物已经吃饱了！**\n请等待饱食度重置后再来喂食。"
        else:
            description += "🍴 **选择食粮进行喂食：**\n"
            description += "• 匹配口味偏好可获得额外经验\n"
            description += "• 讨厌的口味会减少经验获得\n"
            description += "• 饱食度每日重置2次（美东时间0点和12点）"

        embed = create_embed(
            "🍽️ 宠物喂食",
            description,
            discord.Color.green() if self.pet_info['satiety'] < FeedingSystem.SATIETY_MAX else discord.Color.orange()
        )

        return embed

class FoodSelectForFeeding(discord.ui.Select):
    def __init__(self, user_id: int, pet_id: int):
        self.user_id = user_id
        self.pet_id = pet_id

        options = self._load_food_options()

        super().__init__(
            placeholder="选择要投喂的食粮...",
            options=options
        )

    def _load_food_options(self) -> list:
        """加载用户的食粮选项"""
        from src.db.database import get_supabase_client

        supabase = get_supabase_client()

        # 查询用户食粮库存
        response = supabase.table('user_food_inventory').select('''
            quantity,
            food_templates(*)
        ''').eq('user_id', self.user_id).gt('quantity', 0).execute()

        if not response.data:
            return [discord.SelectOption(
                label="没有食粮库存",
                description="去杂货铺购买食粮吧！",
                value="none",
                emoji="❌"
            )]

        # 稀有度表情映射
        rarity_emojis = {
            'C': '🤍',
            'R': '💙',
            'SR': '💜',
            'SSR': '💛'
        }

        # 口味表情映射
        flavor_emojis = {
            'SWEET': '🍯',
            'SALTY': '🧂',
            'SOUR': '🍋',
            'SPICY': '🌶️',
            'UMAMI': '🍄'
        }

        options = []
        for item in response.data:
            food = item['food_templates']
            quantity = item['quantity']

            rarity_emoji = rarity_emojis.get(food['rarity'], '⚪')
            flavor_emoji = flavor_emojis.get(food['flavor'], '🍽️')

            label = f"{food['name']} {flavor_emoji}"
            description = f"库存:{quantity} | {food['base_xp']}经验 | +5-8饱食度"

            options.append(discord.SelectOption(
                label=label[:100],
                description=description[:100],
                value=str(food['id']),
                emoji=rarity_emoji
            ))

        return options

    async def callback(self, interaction: discord.Interaction):
        """处理食粮选择回调"""
        if self.values[0] == "none":
            await interaction.response.send_message("❌ 没有可用的食粮！请先去杂货铺购买。", ephemeral=True)
            return

        food_template_id = int(self.values[0])

        # 执行喂食
        await execute_feeding(interaction, self.user_id, self.pet_id, food_template_id)

async def execute_feeding(interaction: discord.Interaction, user_id: int, pet_id: int, food_template_id: int):
    """执行喂食逻辑"""
    from src.db.database import get_supabase_client
    from src.utils.feeding_system import feed_pet

    supabase = get_supabase_client()

    try:
        # 检查食粮库存
        inventory_response = supabase.table('user_food_inventory').select('quantity').eq('user_id', user_id).eq('food_template_id', food_template_id).execute()

        if not inventory_response.data or inventory_response.data[0]['quantity'] <= 0:
            await interaction.response.send_message("❌ 食粮库存不足！", ephemeral=True)
            return

        # 执行喂食
        result = feed_pet(pet_id, food_template_id)

        if not result['success']:
            embed = create_embed("❌ 喂食失败", result['message'], discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 扣除食粮库存
        current_quantity = inventory_response.data[0]['quantity']
        new_quantity = current_quantity - 1

        if new_quantity > 0:
            supabase.table('user_food_inventory').update({'quantity': new_quantity}).eq('user_id', user_id).eq('food_template_id', food_template_id).execute()
        else:
            supabase.table('user_food_inventory').delete().eq('user_id', user_id).eq('food_template_id', food_template_id).execute()

        # 创建成功消息
        description = f"{interaction.user.mention} 的 **{result['pet_name']}** 吃了 **{result['food_name']}**！\n\n"

        # 经验获得
        description += f"✨ **获得经验：** +{result['xp_gained']}\n"

        # 口味匹配bonus
        if result['flavor_bonus'] == 'favorite':
            description += f"💖 **口味匹配：** 额外30%经验！\n"
        elif result['flavor_bonus'] == 'dislike':
            description += f"💔 **不喜欢：** 经验减少10%\n"

        # 饱食度
        description += f"🍽️ **饱食度：** +{result['satiety_gained']} → {result['new_satiety']}/100\n"

        # 等级提升
        if result['level_up']:
            description += f"\n🎉 **恭喜！宠物升级了！**\n"
            description += f"🆙 **新等级：** {result['new_level']}\n"

        embed = create_embed(
            "🍴 喂食成功！",
            description,
            discord.Color.green()
        )

        # 如果饱食度满了，添加提示
        if result['new_satiety'] >= 100:
            embed.add_field(
                name="⚠️ 提示",
                value="宠物已经吃饱了！饱食度会在美东时间0点和12点重置。",
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        print(f"喂食执行错误: {e}")
        embed = create_embed("❌ 错误", "喂食过程中发生错误！", discord.Color.red())
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)

# 宠物自动补全函数
async def pet_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """为宠物参数提供自动补全"""
    try:
        from src.utils.helpers import get_user_internal_id
        from src.db.database import get_supabase_client

        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            return []

        supabase = get_supabase_client()

        # 查询用户的宠物
        pets_response = supabase.table('user_pets').select('id, pet_template_id, stars').eq('user_id', user_internal_id).order('stars', desc=True).limit(25).execute()

        if not pets_response.data:
            return []

        # 获取宠物模板信息
        template_ids = list(set([pet['pet_template_id'] for pet in pets_response.data]))
        templates_response = supabase.table('pet_templates').select('id, name, rarity').in_('id', template_ids).execute()

        # 创建模板映射
        template_map = {template['id']: template for template in templates_response.data}

        pets = []
        for pet in pets_response.data:
            template = template_map.get(pet['pet_template_id'])
            if template:
                pets.append({
                    'id': pet['id'],
                    'name': template['name'],
                    'rarity': template['rarity'],
                    'stars': pet['stars']
                })

        # 按稀有度和星级排序
        rarity_order = {'SSR': 4, 'SR': 3, 'R': 2, 'C': 1}
        pets.sort(key=lambda x: (rarity_order.get(x['rarity'], 0), x['stars'], x['name']), reverse=True)

        # 稀有度颜色映射
        rarity_emojis = {
            "C": "⚪",
            "R": "🔵",
            "SR": "🟣",
            "SSR": "🟡",
        }

        choices = []
        for pet in pets:
            emoji = rarity_emojis.get(pet['rarity'], "⚪")
            star_display = "★" * pet['stars']
            display_name = f"{emoji} {pet['name']} {star_display}"

            # 如果有输入内容，进行过滤
            if current and current.lower() not in pet['name'].lower():
                continue

            choices.append(app_commands.Choice(name=display_name, value=str(pet['id'])))

            # Discord 限制最多 25 个选项
            if len(choices) >= 25:
                break

        return choices

    except Exception as e:
        print(f"宠物自动补全时出错：{str(e)}")
        return []

# 一键喂食命令
@app_commands.command(name="feed_auto", description="🍽️ 一键喂食 - 自动为指定宠物选择最优食粮")
@app_commands.describe(
    pet="选择要喂食的宠物（留空则喂食装备的宠物）",
    mode="喂食模式（选择策略）",
    quantity="喂食次数（可选，默认喂到饱）"
)
@app_commands.autocomplete(pet=pet_autocomplete)
@app_commands.choices(mode=[
    app_commands.Choice(name="🏆 最优经验 - 选择经验效率最高的食粮", value="optimal_xp"),
    app_commands.Choice(name="💖 口味匹配 - 优先匹配宠物偏好口味", value="flavor_match"),
    app_commands.Choice(name="💰 节约模式 - 使用最便宜的可用食粮", value="economic"),
    app_commands.Choice(name="📦 清空库存 - 优先消耗数量多的食粮", value="clear_inventory"),
])
@app_commands.guild_only()
async def feed_auto(interaction: discord.Interaction, pet: str = None, mode: str = "optimal_xp", quantity: int = None):
    """一键喂食指定宠物或装备的宠物"""
    await handle_auto_feeding(interaction, mode, quantity, pet)

async def handle_auto_feeding(interaction: discord.Interaction, mode: str, quantity: int = None, pet_id: str = None):
    """处理一键喂食逻辑"""
    try:
        from src.utils.feeding_system import AutoFeedingSystem
        from src.utils.helpers import get_user_internal_id
        from src.db.database import get_supabase_client

        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed("❌ 错误", "用户不存在，请先使用抽卡功能注册！", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 确定要喂食的宠物ID
        supabase = get_supabase_client()
        target_pet_id = None

        if pet_id:
            # 验证指定的宠物是否属于用户
            pet_response = supabase.table('user_pets').select('id').eq('id', int(pet_id)).eq('user_id', user_internal_id).execute()
            if not pet_response.data:
                embed = create_embed(
                    "❌ 宠物不存在",
                    f"{interaction.user.mention} 指定的宠物不存在或不属于你！",
                    discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            target_pet_id = int(pet_id)
        else:
            # 获取装备的宠物
            user_response = supabase.table('users').select('equipped_pet_id').eq('id', user_internal_id).execute()

            if not user_response.data or not user_response.data[0]['equipped_pet_id']:
                embed = create_embed(
                    "❌ 没有装备宠物",
                    f"{interaction.user.mention} 你当前没有装备任何宠物！\n\n"
                    "请先使用 `/pet equip` 装备一只宠物，或在命令中指定要喂食的宠物。",
                    discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            target_pet_id = user_response.data[0]['equipped_pet_id']

        # 发送初始响应
        await interaction.response.send_message("🍽️ 正在为你的宠物准备最优食粮...", ephemeral=False)

        # 执行一键喂食
        result = AutoFeedingSystem.auto_feed_pet(user_internal_id, target_pet_id, mode, quantity)

        if not result['success']:
            embed = create_embed("❌ 喂食失败", result['message'], discord.Color.red())
            await interaction.edit_original_response(content="", embed=embed, ephemeral=True)
            return

        # 构建成功结果显示
        embed = create_auto_feeding_result_embed(interaction.user.mention, result, mode)
        await interaction.edit_original_response(content="", embed=embed)

    except Exception as e:
        print(f"一键喂食错误: {e}")
        embed = create_embed("❌ 错误", f"喂食过程中发生错误：{str(e)}", discord.Color.red())
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.edit_original_response(content="", embed=embed)

def create_auto_feeding_result_embed(user_mention: str, result: dict, mode: str) -> discord.Embed:
    """创建一键喂食结果展示"""

    # 模式名称映射
    mode_names = {
        "optimal_xp": "🏆 最优经验",
        "flavor_match": "💖 口味匹配",
        "economic": "💰 节约模式",
        "clear_inventory": "📦 清空库存"
    }

    # 稀有度颜色映射
    rarity_colors = {
        'C': '🤍',
        'R': '💙',
        'SR': '💜',
        'SSR': '💛'
    }

    # 口味表情映射
    flavor_emojis = {
        'SWEET': '🍯',
        'SALTY': '🧂',
        'SOUR': '🍋',
        'SPICY': '🌶️',
        'UMAMI': '🍄'
    }

    mode_name = mode_names.get(mode, mode)

    description = f"{user_mention} 一键喂食完成！\n\n"

    # 基础统计信息
    description += f"**📊 喂食统计：**\n"
    description += f"• 喂食模式：{mode_name}\n"
    description += f"• 喂食次数：{result['total_feeds']}次\n"
    description += f"• 经验获得：+{result['total_xp_gained']} XP\n"
    description += f"• 饱食度：{result['original_satiety']} → {result['new_satiety']}\n\n"

    # 使用的食粮详情
    if result['food_summary']:
        description += f"**🍯 使用的食粮：**\n"
        for food_name, info in result['food_summary'].items():
            rarity_color = rarity_colors.get(info['rarity'], '⚪')
            flavor_emoji = flavor_emojis.get(info['flavor'], '🍽️')

            # 口味匹配提示
            match_text = ""
            if info['flavor_matches'] > 0:
                match_text = f" (匹配偏好 +30% 经验 x{info['flavor_matches']})"

            description += f"{rarity_color} {food_name} {flavor_emoji} x{info['count']}{match_text}\n"
        description += "\n"

    # 等级变化
    if result['level_up']:
        description += f"**🎉 恭喜升级！**\n"
        description += f"⭐ **等级变化：** Lv.{result['original_level']} → Lv.{result['new_level']}！\n\n"

    # 宠物状态
    description += f"**🐾 宠物：** {result['pet_name']}\n"
    description += f"**🆙 当前等级：** Lv.{result['new_level']}"

    # 如果饱食度满了，添加提示
    if result['new_satiety'] >= 100:
        description += f"\n\n💡 **提示：** 宠物已经吃饱了！饱食度会在美东时间0点和12点重置。"

    embed = create_embed("🍽️ 一键喂食完成", description, discord.Color.green())

    return embed

def setup(bot):
    """注册斜杠命令"""
    bot.tree.add_command(pet)
    bot.tree.add_command(feed_auto)