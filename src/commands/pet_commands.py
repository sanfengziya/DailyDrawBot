import discord
from discord.ext import commands
from discord import app_commands
import datetime
from src.utils.ui import create_embed
from src.utils.helpers import get_user_internal_id

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
    
    def calculate_pet_points(self, rarity, stars, hours):
        """计算宠物积分获取量"""
        base_points = self.PET_POINTS_PER_HOUR.get(rarity, 0)
        multiplier = stars + 1
        return int(base_points * multiplier * hours)
    
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
            pet_response = supabase.table('user_pets').select('pet_template_id, stars').eq('id', equipped_pet_id).execute()
            
            if not pet_response.data:
                return 0
            
            pet_data = pet_response.data[0]
            pet_template_id = pet_data['pet_template_id']
            stars = pet_data['stars']
            
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
            pending_points = self.calculate_pet_points(rarity, stars, actual_hours)
            
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
        await interaction.response.send_message(embed=embed)
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
        pet_response = supabase.table('user_pets').select('id, pet_template_id, stars, created_at').eq('id', pet_id).eq('user_id', user_internal_id).execute()
        
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
        await interaction.response.send_message(embed=embed)
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
        "宠物信息",
        f"{rarity_colors[rarity]} {interaction.user.mention} 的 {pet_name}\n"
        f"**宠物ID：** {pet_id}\n"
        f"**稀有度：** {rarity}\n"
        f"**星级：** {star_display} ({stars}/{max_stars})\n"
        f"**获得时间：** {(datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00')) if isinstance(created_at, str) else created_at).strftime('%Y-%m-%d')}"
        f"{upgrade_info}",
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
        await interaction.response.send_message(embed=embed)
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
        await interaction.response.send_message(embed=embed)
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
    
    view = DismantleConfirmView(str(interaction.user.id), user_internal_id, pet_id, pet_name, rarity, total_fragments, total_points)
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
        await interaction.response.send_message(embed=embed)
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
    def __init__(self, discord_user_id, user_internal_id, pet_id, pet_name, rarity, fragments, points):
        super().__init__(timeout=30)
        self.discord_user_id = discord_user_id  # 用于验证用户身份
        self.user_internal_id = user_internal_id  # 用于数据库操作
        self.pet_id = pet_id
        self.pet_name = pet_name
        self.rarity = rarity
        self.fragments = fragments
        self.points = points

    @discord.ui.button(label='确认分解', style=discord.ButtonStyle.danger, emoji='💥')
    async def confirm_dismantle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_user_id:
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
            
            # 添加积分
            if self.points > 0:
                user_response = supabase.table('users').select('points').eq('id', self.user_internal_id).execute()
                if user_response.data:
                    current_points = user_response.data[0]['points']
                    new_points = current_points + self.points
                    supabase.table('users').update({'points': new_points}).eq('id', self.user_internal_id).execute()
                    
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
        if str(interaction.user.id) != self.discord_user_id:
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
        await interaction.response.send_message(embed=embed)
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
    hourly_points = pet_commands.calculate_pet_points(rarity, stars, 1)
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
        await interaction.response.send_message(embed=embed)
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
        pet_response = supabase.table('user_pets').select('pet_template_id, stars').eq('id', equipped_pet_id).execute()
        
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
        hourly_points = pet_commands.calculate_pet_points(rarity, stars, 1)
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
        await interaction.response.send_message(embed=embed)

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
        await interaction.response.send_message(embed=embed)

def setup(bot):
    """注册斜杠命令"""
    bot.tree.add_command(pet)