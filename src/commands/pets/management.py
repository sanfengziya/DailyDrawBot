import discord
from discord.ext import commands
from discord import app_commands
import datetime
from src.utils.ui import create_embed
from src.utils.helpers import get_user_internal_id
from src.utils.cache import UserCache
from src.utils.i18n import get_guild_locale, t, get_context_locale, get_localized_pet_name, get_localized_food_name, get_localized_food_description

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
        """添加碎片到玩家库存（同步版本，用于向后兼容）"""
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
            print(f"Error adding fragments: {str(e)}")

    async def add_fragments_async(self, player_id, rarity, amount):
        """异步添加碎片到玩家库存"""
        try:
            from src.db.database import get_supabase_client
            supabase = get_supabase_client()

            # 先查询是否存在
            existing = supabase.table('user_pet_fragments').select('amount').eq('user_id', player_id).eq('rarity', rarity).execute()

            if existing.data:
                # 更新现有记录
                current_amount = existing.data[0]['amount']
                new_amount = current_amount + amount
                supabase.table('user_pet_fragments').update({'amount': new_amount}).eq('user_id', player_id).eq('rarity', rarity).execute()
            else:
                # 插入新记录
                supabase.table('user_pet_fragments').insert({
                    'user_id': player_id,
                    'rarity': rarity,
                    'amount': amount
                }).execute()

        except Exception as e:
            print(f"Error adding fragments async: {str(e)}")
            raise  # 在异步环境中重新抛出异常以便于处理
    
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
            print(f"Error updating pet points timestamp: {str(e)}")

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
            template_response = supabase.table('pet_templates').select('id, en_name, cn_name, rarity').eq('id', pet_template_id).execute()
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
            print(f"Error calculating pending points: {str(e)}")
            return 0

# 宠物选择视图
class PetSelectView(discord.ui.View):
    def __init__(self, user_id: int, action: str, guild_id: int = None):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.action = action
        self.guild_id = guild_id

    async def setup_select(self):
        """设置宠物选择下拉菜单"""
        try:
            from src.db.database import get_supabase_client
            supabase = get_supabase_client()
            
            # 查询用户的宠物
            pets_response = supabase.table('user_pets').select('id, pet_template_id, stars').eq('user_id', self.user_id).limit(25).execute()
            
            if not pets_response.data:
                return False
            
            # 获取所有宠物模板信息
            template_ids = list(set([pet['pet_template_id'] for pet in pets_response.data]))
            templates_response = supabase.table('pet_templates').select('id, en_name, cn_name, rarity').in_('id', template_ids).execute()

            # 创建模板映射
            template_map = {template['id']: template for template in templates_response.data}

            pets = []
            locale = get_guild_locale(self.guild_id)  # 使用正确的语言环境
            for pet in pets_response.data:
                template = template_map.get(pet['pet_template_id'])
                if template:
                    pet_name = get_localized_pet_name(template, locale)
                    pets.append((pet['id'], pet_name, template['rarity'], pet['stars']))
            
            # 按稀有度和星级排序（稀有度优先，SSR > SR > R > C；同稀有度按星级从高到低）
            rarity_order = {'SSR': 1, 'SR': 2, 'R': 3, 'C': 4}
            pets.sort(key=lambda x: (rarity_order.get(x[2], 5), -x[3]))
            
        except Exception as e:
            print(f"Error setting up pet selection menu: {str(e)}")
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
        
        select = PetSelect(self.action, options, self.guild_id)
        self.add_item(select)
        return True

class PetSelect(discord.ui.Select):
    def __init__(self, action: str, options, guild_id: int = None):
        self.action = action
        self.guild_id = guild_id
        locale = get_guild_locale(guild_id)

        # 如果是批量分解，使用多选模式
        if action == "batch_dismantle":
            super().__init__(
                placeholder=t("pet.ui.placeholders.select_batch_dismantle", locale=locale, default="选择要批量分解的宠物 (最多20个)..."),
                options=options,
                min_values=1,
                max_values=min(len(options), 20)  # 最多选择20个
            )
        else:
            super().__init__(
                placeholder=t("pet.ui.placeholders.select_" + action, locale=locale, default=f"选择要{self.get_action_name(locale)}的宠物..."),
                options=options
            )

    def get_action_name(self, locale=None):
        if locale is None:
            locale = get_guild_locale(self.guild_id)
        action_names = {
            "info": t("pet.command.choices.info", locale=locale),
            "upgrade": t("pet.command.choices.upgrade", locale=locale),
            "dismantle": t("pet.command.choices.dismantle", locale=locale),
            "batch_dismantle": t("pet.command.choices.batch_dismantle", locale=locale),
            "equip": t("pet.command.choices.equip", locale=locale),
            "feed": t("pet.command.choices.feed", locale=locale)
        }
        return action_names.get(self.action, t("pet.ui.actions.operate", locale=locale))
    
    async def callback(self, interaction: discord.Interaction):
        if self.action == "batch_dismantle":
            # 批量分解模式，传递多个宠物ID
            pet_ids = [int(pet_id) for pet_id in self.values]
            await handle_batch_dismantle_selection(interaction, pet_ids)
        else:
            # 单选模式，传递单个宠物ID
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

# 主宠物命令定义（现在使用autocomplete，不再需要固定的choices函数）

async def pet_action_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """为pet命令的action参数提供基于服务器语言的自动补全"""
    from src.utils.i18n import t, get_guild_locale

    # 获取服务器语言设置
    server_locale = get_guild_locale(interaction.guild.id)

    actions = [
        ("list", "pet.command.choices.list"),
        ("info", "pet.command.choices.info"),
        ("upgrade", "pet.command.choices.upgrade"),
        ("dismantle", "pet.command.choices.dismantle"),
        ("batch_dismantle", "pet.command.choices.batch_dismantle"),
        ("fragments", "pet.command.choices.fragments"),
        ("equip", "pet.command.choices.equip"),
        ("unequip", "pet.command.choices.unequip"),
        ("status", "pet.command.choices.status"),
        ("claim", "pet.command.choices.claim"),
        ("feed", "pet.command.choices.feed")
    ]

    choices = []
    for action_value, translation_key in actions:
        # 使用服务器语言获取翻译
        localized_name = t(translation_key, locale=server_locale,
                         default=action_value.replace("_", " ").title() if action_value != "list" else "View List")

        # 如果用户有输入，进行过滤
        if current and current.lower() not in localized_name.lower() and current.lower() not in action_value.lower():
            continue

        choices.append(app_commands.Choice(name=localized_name, value=action_value))

    return choices

@app_commands.command(name="pet", description="Pet system - view, upgrade, and manage pets")
@app_commands.guild_only()
@app_commands.describe(
    action="Select action type",
    page="Page number (for list view, default: 1)"
)
@app_commands.autocomplete(action=pet_action_autocomplete)
async def pet(interaction: discord.Interaction, action: str, page: int = 1):
    """宠物系统主命令"""
    locale = get_context_locale(interaction)

    if action == "list":
        await handle_pet_list(interaction, page)
    elif action == "batch_dismantle":
        await handle_batch_dismantle_mode_selection(interaction)
    elif action in ["info", "upgrade", "dismantle", "equip", "feed"]:
        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed(t("pet.errors.user_not_found.title", locale=locale), t("pet.errors.user_not_found.message", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 显示宠物选择界面
        guild_id = interaction.guild.id if interaction.guild else None
        view = PetSelectView(user_internal_id, action, guild_id)
        has_pets = await view.setup_select()

        if not has_pets:
            embed = create_embed(
                t("pet.errors.no_pets.title", locale=locale),
                t("pet.errors.no_pets.message", locale=locale),
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        action_names = {
            "info": t("pet.action_names.info", locale=locale),
            "upgrade": t("pet.action_names.upgrade", locale=locale),
            "dismantle": t("pet.action_names.dismantle", locale=locale),
            "batch_dismantle": t("pet.command.choices.batch_dismantle", locale=locale),
            "equip": t("pet.action_names.equip", locale=locale),
            "feed": t("pet.action_names.feed", locale=locale)
        }

        embed = create_embed(
            f"🐾 {action_names[action]}",
            t("pet.select_pet.description", locale=locale),
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

        locale = get_context_locale(interaction)

        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed(t("pet.errors.user_not_found.title", locale=locale), t("pet.errors.user_not_found.message", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # 先获取所有宠物（不分页）
        all_pets_response = supabase.table('user_pets').select('id, pet_template_id, stars, created_at').eq('user_id', user_internal_id).execute()

        total_pets = len(all_pets_response.data) if all_pets_response.data else 0

        if not all_pets_response.data:
            embed = create_embed(
                t("pet.list.title", locale=locale),
                t("pet.list.no_pets", locale=locale, user=interaction.user.mention),
                discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)
            return

        # 获取所有相关的宠物模板
        template_ids = list(set([pet['pet_template_id'] for pet in all_pets_response.data]))
        templates_response = supabase.table('pet_templates').select('id, cn_name, en_name, rarity').in_('id', template_ids).execute()
        templates_dict = {template['id']: template for template in templates_response.data}

        # 获取稀有度配置
        rarities = list(set([template['rarity'] for template in templates_response.data]))
        rarity_configs_response = supabase.table('pet_rarity_configs').select('rarity, max_stars').in_('rarity', rarities).execute()
        rarity_configs_dict = {config['rarity']: config for config in rarity_configs_response.data}

        # 组合所有宠物数据
        pets_data = []
        for pet in all_pets_response.data:
            template = templates_dict.get(pet['pet_template_id'])
            if template:
                rarity_config = rarity_configs_dict.get(template['rarity'])
                max_stars = rarity_config['max_stars'] if rarity_config else 0
                pets_data.append({
                    'id': pet['id'],
                    'name': get_localized_pet_name(template, locale),
                    'rarity': template['rarity'],
                    'stars': pet['stars'],
                    'max_stars': max_stars,
                    'created_at': pet['created_at']
                })

        # 按稀有度、星级、创建时间排序（稀有度优先）
        rarity_order = {'SSR': 1, 'SR': 2, 'R': 3, 'C': 4}
        pets_data.sort(key=lambda x: (rarity_order.get(x['rarity'], 5), -x['stars'], x['created_at']))

        # 分页处理
        per_page = 10
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        pets_data = pets_data[start_idx:end_idx]
        
        pets = [(pet['id'], pet['name'], pet['rarity'], pet['stars'], pet['max_stars'], pet['created_at']) for pet in pets_data]
        
        rarity_colors = {
            'C': '🤍',
            'R': '💙',
            'SR': '💜',
            'SSR': '💛'
        }
        
        description = ""
        for pet_id, pet_name, rarity, stars, max_stars, created_at in pets:
            star_display = '⭐' * stars if stars > 0 else t("pet.list.star_display_none", locale=locale)
            description += f"{rarity_colors[rarity]} **{pet_name}** (ID: {pet_id})\n"
            description += f"   {t('pet.list.star_label', locale=locale)}: {star_display} ({stars}/{max_stars})\n\n"
        
        total_pages = (total_pets + per_page - 1) // per_page
        
    except Exception as e:
        embed = create_embed(
            t("pet.errors.user_not_found.title", locale=locale),
            t("pet.list.query_error", locale=locale, user=interaction.user.mention, error=str(e)),
            discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    embed = create_embed(
        title=t("pet.ui.list_title", locale=locale),
        description=f"{interaction.user.mention} {t('pet.ui.possessive', locale=locale)} (第 {page}/{total_pages} 页)\n {description}",
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"{t('pet.ui.total_pets', locale=locale)} {total_pets} {t('pet.ui.pets_count', locale=locale)}")
    await interaction.response.send_message(embed=embed)

async def handle_pet_info(interaction: discord.Interaction, pet_id: int):
    """查看宠物详情"""
    try:
        from src.db.database import get_supabase_client
        supabase = get_supabase_client()

        # 获取语言设置
        locale = get_context_locale(interaction)

        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed(t("pet.errors.user_not_found.title", locale=locale), t("pet.errors.user_not_found.message", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # 查询宠物基本信息
        pet_response = supabase.table('user_pets').select('id, pet_template_id, stars, created_at, level, xp_current, xp_total, satiety, favorite_flavor, dislike_flavor').eq('id', pet_id).eq('user_id', user_internal_id).execute()

        if not pet_response.data:
            embed = create_embed(
                t("pet.errors.pet_not_found_or_unauthorized", locale=locale, user=interaction.user.mention),
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return

        pet_data = pet_response.data[0]
        
        # 获取宠物模板信息
        template_response = supabase.table('pet_templates').select('en_name, cn_name, rarity').eq('id', pet_data['pet_template_id']).execute()
        if not template_response.data:
            embed = create_embed(t("pet.upgrade.errors.template_not_found.title", locale=locale), t("pet.upgrade.errors.template_not_found.description", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        template_data = template_response.data[0]
        
        # 获取稀有度配置
        rarity_response = supabase.table('pet_rarity_configs').select('max_stars').eq('rarity', template_data['rarity']).execute()
        if not rarity_response.data:
            embed = create_embed(t("pet.upgrade.errors.rarity_config_not_found.title", locale=locale), t("pet.upgrade.errors.rarity_config_not_found.description", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        pet_name = get_localized_pet_name(template_data, get_context_locale(interaction))
        rarity = template_data['rarity']
        stars = pet_data['stars']
        max_stars = rarity_response.data[0]['max_stars']
        created_at = pet_data['created_at']
    
    except Exception as e:
        embed = create_embed(
            t("pet.errors.user_not_found.title", locale=locale),
            t("pet.info.query_error", locale=locale, user=interaction.user.mention, error=str(e)),
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
    
    star_display = '⭐' * stars if stars > 0 else t("pet.info.star_display_none", locale=locale)
    
    # 计算升星费用（如果还能升星）
    upgrade_info = ""
    if stars < max_stars:
        cost = PetCommands.UPGRADE_COSTS[stars]
        upgrade_info = f"\n**{t('pet.upgrade_cost.title', locale=locale)}**\n{t('pet.upgrade_cost.format', locale=locale, count=cost['fragments'], rarity=rarity, points=cost['points'])}"
    else:
        upgrade_info = f"\n**{t('pet.errors.max_stars_reached.title', locale=locale)}**\n{t('pet.errors.max_stars_reached.message', locale=locale, user=interaction.user.mention, pet_name=pet_name)}"
    
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
    favorite_flavor_display = t(f"pet.flavor_descriptions.{favorite_flavor}", locale=locale, default=flavor_emojis.get(favorite_flavor, t("pet.info.flavor_fallback_no_preference", locale=locale)))
    dislike_flavor_display = t(f"pet.flavor_descriptions.{dislike_flavor}", locale=locale, default=flavor_emojis.get(dislike_flavor, t("pet.info.flavor_fallback_none", locale=locale)))
    
    # 构建描述内容
    possessive_suffix = t("pet.info.possessive_suffix", locale=locale)
    possessive = f"{interaction.user.mention}{possessive_suffix}"
    description = f"{possessive} {rarity_colors[rarity]} **{pet_name}**\n\n"

    # 基本信息
    colon = ":" if locale.startswith('en') else "："
    description += f"🆔 **{t('pet.info_labels.pet_id', locale=locale)}{colon}** {pet_id}\n"
    description += f"💎 **{t('pet.info_labels.rarity', locale=locale)}{colon}** {rarity}\n"
    description += f"⭐ **{t('pet.info_labels.stars', locale=locale)}{colon}** {star_display} ({stars}/{max_stars})\n\n"

    # 等级和经验
    description += f"📊 **{t('pet.info_labels.level', locale=locale)}{colon}** {level}\n"
    description += f"✨ **{t('pet.info_labels.experience', locale=locale)}{colon}** {xp_current}/{xp_needed_for_next_level}\n"
    description += f"📈 {progress_bar} {progress_percent}%\n\n"

    # 饱食度
    description += f"🍽️ **{t('pet.info_labels.satiety', locale=locale)}{colon}** {satiety}/100\n"
    description += f"📊 {satiety_bar} {satiety}%\n\n"

    # 口味偏好
    description += f"💖 **{t('pet.info_labels.favorite', locale=locale)}{colon}** {favorite_flavor_display}\n"
    description += f"💔 **{t('pet.info_labels.dislike', locale=locale)}{colon}** {dislike_flavor_display}\n\n"

    # 总经验和获得时间
    description += f"🏆 **{t('pet.info_labels.total_experience', locale=locale)}{colon}** {xp_total}\n"
    description += f"📅 **{t('pet.info_labels.acquisition_date', locale=locale)}{colon}** {(datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00')) if isinstance(created_at, str) else created_at).strftime('%Y-%m-%d')}\n"
    
    # 升星信息
    description += f"{upgrade_info}"

    embed = create_embed(
        f"🐾 {t('pet.ui.title', locale=locale)}",
        description,
        discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

async def handle_pet_upgrade(interaction: discord.Interaction, pet_id: int):
    """升星宠物"""
    locale = get_context_locale(interaction)
    try:
        from src.db.database import get_supabase_client
        supabase = get_supabase_client()

        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed(t("pet.errors.user_not_found.title", locale=locale), t("pet.errors.user_not_found.message", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # 获取宠物信息
        pet_response = supabase.table('user_pets').select('id, pet_template_id, stars').eq('id', pet_id).eq('user_id', user_internal_id).execute()

        if not pet_response.data:
            embed = create_embed(
                t("pet.upgrade.errors.pet_not_found.title", locale=locale),
                t("pet.upgrade.errors.pet_not_found.description", locale=locale, user=interaction.user.mention),
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        pet_data = pet_response.data[0]
        
        # 获取宠物模板信息
        template_response = supabase.table('pet_templates').select('en_name, cn_name, rarity').eq('id', pet_data['pet_template_id']).execute()
        if not template_response.data:
            embed = create_embed(t("pet.upgrade.errors.template_not_found.title", locale=locale), t("pet.upgrade.errors.template_not_found.description", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        template_data = template_response.data[0]
        
        # 获取稀有度配置
        rarity_response = supabase.table('pet_rarity_configs').select('max_stars').eq('rarity', template_data['rarity']).execute()
        if not rarity_response.data:
            embed = create_embed(t("pet.upgrade.errors.rarity_config_not_found.title", locale=locale), t("pet.upgrade.errors.rarity_config_not_found.description", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        pet_name = get_localized_pet_name(template_data, get_context_locale(interaction))
        rarity = template_data['rarity']
        stars = pet_data['stars']
        max_stars = rarity_response.data[0]['max_stars']
        
        if stars >= max_stars:
            embed = create_embed(
                t("pet.upgrade.errors.max_stars_reached.title", locale=locale),
                t("pet.upgrade.errors.max_stars_reached.description", locale=locale, user=interaction.user.mention, pet_name=pet_name),
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
                t("pet.upgrade.errors.cannot_get_resources.title", locale=locale),
                t("pet.upgrade.errors.cannot_get_resources.description", locale=locale, user=interaction.user.mention),
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
                t("pet.upgrade.errors.insufficient_points.title", locale=locale),
                t("pet.upgrade.errors.insufficient_points.description", locale=locale, user=interaction.user.mention, required_points=required_points, points=points),
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        if fragments < required_fragments:
            embed = create_embed(
                t("pet.upgrade.errors.insufficient_fragments.title", locale=locale),
                t("pet.upgrade.errors.insufficient_fragments.description", locale=locale, user=interaction.user.mention, required_fragments=required_fragments, rarity=rarity, fragments=fragments),
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
            t("pet.upgrade.success.title", locale=locale),
            t("pet.upgrade.success.description", locale=locale, user=interaction.user.mention, pet_name=pet_name, stars=star_display, current=new_stars, max=max_stars, fragments=required_fragments, rarity=rarity, points=required_points),
            discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        embed = create_embed(
            t("pet.upgrade.errors.system_error.title", locale=locale),
            t("pet.upgrade.errors.system_error.description", locale=locale, error=str(e)),
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
            embed = create_embed(t("pet.errors.user_not_found.title", locale=locale), t("pet.errors.user_not_found.message", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        locale = get_guild_locale(interaction.guild.id)
        
        # 检查宠物是否正在装备
        user_response = supabase.table('users').select('equipped_pet_id').eq('id', user_internal_id).execute()
        if user_response.data and user_response.data[0]['equipped_pet_id'] == pet_id:
            embed = create_embed(
                t("pet.errors.cannot_dismantle_equipped.title", locale=locale),
                t("pet.errors.cannot_dismantle_equipped.message", locale=locale, user=interaction.user.mention),
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return

        # 获取宠物信息
        pet_response = supabase.table('user_pets').select('pet_template_id, stars').eq('id', pet_id).eq('user_id', user_internal_id).execute()
        
        if not pet_response.data:
            embed = create_embed(
                t("pet.errors.user_not_found.title", locale=locale),
                t("pet.errors.pet_not_found_or_unauthorized", locale=locale, user=interaction.user.mention),
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        pet_data = pet_response.data[0]
        pet_template_id = pet_data['pet_template_id']
        stars = pet_data['stars']
        
        # 获取宠物模板信息
        template_response = supabase.table('pet_templates').select('id, cn_name, en_name, rarity').eq('id', pet_template_id).execute()
        if not template_response.data:
            embed = create_embed(t("pet.upgrade.errors.template_not_found.title", locale=locale), t("pet.upgrade.errors.template_not_found.description", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        template_data = template_response.data[0]
        pet_name = get_localized_pet_name(template_data, get_context_locale(interaction))
        rarity = template_data['rarity']
        
    except Exception as e:
        locale = get_guild_locale(interaction.guild.id)
        embed = create_embed(
            t("pet.errors.user_not_found.title", locale=locale),
            t("pet.dismantle.query_error", locale=locale, user=interaction.user.mention),
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
    
    locale = get_guild_locale(interaction.guild.id)
    
    # 创建确认界面
    description = t("pet.dismantle.confirm.description", locale=locale, user=interaction.user.mention, pet_name=pet_name)
    description += t("pet.dismantle.confirm.benefits", locale=locale)
    description += t("pet.dismantle.confirm.benefits_fragments", locale=locale, fragments=total_fragments, rarity=rarity)
    description += t("pet.dismantle.confirm.benefits_points", locale=locale, points=total_points)
    description += t("pet.dismantle.confirm.warning", locale=locale)
    
    embed = create_embed(
        t("pet.dismantle.confirm.title", locale=locale),
        description,
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
            embed = create_embed(t("pet.errors.user_not_found.title", locale=locale), t("pet.errors.user_not_found.message", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # 查询碎片库存
        response = supabase.table('user_pet_fragments').select('rarity, amount').eq('user_id', user_internal_id).gt('amount', 0).execute()
        
        fragments = response.data
        
        # 手动排序（Supabase不支持复杂的CASE排序）
        rarity_order = {'SSR': 1, 'SR': 2, 'R': 3, 'C': 4}
        fragments.sort(key=lambda x: rarity_order.get(x['rarity'], 5))
        
    except Exception as e:
        locale = get_guild_locale(interaction.guild.id)
        embed = create_embed(
            t("pet.errors.user_not_found.title", locale=locale),
            t("pet.fragments.query_error", locale=locale, user=interaction.user.mention),
            discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    locale = get_guild_locale(interaction.guild.id)
    
    if not fragments:
        embed = create_embed(
            t("pet.fragments.title", locale=locale),
            t("pet.fragments.no_fragments", locale=locale, user=interaction.user.mention),
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
        description += t("pet.fragments.display", locale=locale, color=rarity_colors[rarity], rarity=rarity, amount=amount)
    
    embed = create_embed(
        title=t("pet.fragments.title", locale=locale),
        description=t("pet.fragments.description", locale=locale, user=interaction.user.mention, description=description),
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
        
        # 获取语言环境并设置按钮标签
        locale = get_guild_locale(guild_id)
        
        # 创建确认按钮
        confirm_button = discord.ui.Button(
            label=t("pet.ui.buttons.confirm", locale=locale),
            style=discord.ButtonStyle.danger,
            emoji='💥',
            custom_id='confirm_dismantle'
        )
        confirm_button.callback = self.confirm_dismantle_callback
        self.add_item(confirm_button)
        
        # 创建取消按钮
        cancel_button = discord.ui.Button(
            label=t("pet.ui.buttons.cancel", locale=locale),
            style=discord.ButtonStyle.secondary,
            emoji='❌',
            custom_id='cancel_dismantle'
        )
        cancel_button.callback = self.cancel_dismantle_callback
        self.add_item(cancel_button)

    async def confirm_dismantle_callback(self, interaction: discord.Interaction):
        locale = get_guild_locale(interaction.guild.id)
        if interaction.user.id != self.discord_user_id:
            await interaction.response.send_message(t("pet.errors.not_your_interface", locale=locale), ephemeral=True)
            return
        
        try:
            from src.db.database import get_supabase_client
            supabase = get_supabase_client()
            
            # 删除宠物
            delete_response = supabase.table('user_pets').delete().eq('id', self.pet_id).eq('user_id', self.user_internal_id).execute()
            
            if not delete_response.data:
                embed = create_embed(
                    t("pet.errors.user_not_found.title", locale=locale),
                    t("pet.dismantle.error_deleting", locale=locale, user=interaction.user.mention),
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
                t("pet.errors.user_not_found.title", locale=locale),
                t("pet.dismantle.error_executing", locale=locale, user=interaction.user.mention),
                discord.Color.red()
            )
            await interaction.response.edit_message(embed=embed, view=None)
            return

        # 先编辑原消息（移除按钮）
        await interaction.response.edit_message(content=t("pet.dismantle.confirm.processing", locale=locale), embed=None, view=None)

        # 发送公开的成功消息
        embed = create_embed(
            t("pet.dismantle.success.title", locale=locale),
            t("pet.dismantle.success.description", locale=locale, user=interaction.user.mention, pet_name=self.pet_name, fragments=self.fragments, rarity=self.rarity, points=self.points),
            discord.Color.green()
        )
        await interaction.followup.send(embed=embed)

    async def cancel_dismantle_callback(self, interaction: discord.Interaction):
        locale = get_guild_locale(interaction.guild.id)
        if interaction.user.id != self.discord_user_id:
            await interaction.response.send_message(t("pet.errors.not_your_interface", locale=locale), ephemeral=True)
            return
        
        embed = create_embed(
            t("pet.dismantle.cancelled.title", locale=locale),
            t("pet.dismantle.cancelled.message", locale=locale, user=interaction.user.mention),
            discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=None)

async def handle_pet_equip(interaction: discord.Interaction, pet_id: int):
    """装备宠物"""
    locale = get_guild_locale(interaction.guild.id)
    try:
        from src.db.database import get_supabase_client
        supabase = get_supabase_client()
        
        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed(t("pet.errors.user_not_found.title", locale=locale), t("pet.errors.user_not_found.message", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # 检查宠物是否存在且属于用户
        pet_response = supabase.table('user_pets').select('pet_template_id, stars, level').eq('id', pet_id).eq('user_id', user_internal_id).execute()
        
        if not pet_response.data:
            embed = create_embed(
                t("pet.equip.pet_not_found.title", locale=locale),
                t("pet.equip.pet_not_found.message", locale=locale, user=interaction.user.mention),
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        pet_data = pet_response.data[0]
        pet_template_id = pet_data['pet_template_id']
        stars = pet_data['stars']
        level = pet_data['level']

        # 获取宠物模板信息
        template_response = supabase.table('pet_templates').select('id, cn_name, en_name, rarity').eq('id', pet_template_id).execute()
        if not template_response.data:
            embed = create_embed(t("pet.upgrade.errors.template_not_found.title", locale=locale), t("pet.upgrade.errors.template_not_found.description", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return

        template_data = template_response.data[0]
        pet_name = get_localized_pet_name(template_data, get_context_locale(interaction))
        rarity = template_data['rarity']

        # 检查是否已经装备了这只宠物
        equipped_response = supabase.table('users').select('equipped_pet_id').eq('id', user_internal_id).execute()
        
        current_equipped_id = None
        if equipped_response.data:
            current_equipped_id = equipped_response.data[0]['equipped_pet_id']
        
        if current_equipped_id == pet_id:
            embed = create_embed(
                t("pet.errors.already_equipped.title", locale=locale),
                t("pet.errors.already_equipped.message", locale=locale, user=interaction.user.mention, pet_name=pet_name),
                discord.Color.yellow()
            )
            await interaction.response.send_message(embed=embed)
            return
            
    except Exception as e:
        embed = create_embed(
            t("pet.errors.user_not_found.title", locale=locale),
            t("pet.equip.query_error", locale=locale, user=interaction.user.mention),
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
            t("pet.equip.claim_pending_points.title", locale=locale),
            t("pet.equip.claim_pending_points.description", locale=locale, user=interaction.user.mention, points=pending_points),
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
        t("pet.equip.success.title", locale=locale),
        t("pet.equip.success.description", locale=locale, user=interaction.user.mention, pet_name=pet_name, rarity_color=rarity_color, rarity=rarity, stars=star_display, star_count=stars, hourly_points=hourly_points),
        discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

async def handle_pet_unequip(interaction: discord.Interaction):
    """卸下宠物"""
    locale = get_guild_locale(interaction.guild.id)
    try:
        from src.db.database import get_supabase_client
        supabase = get_supabase_client()
        
        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed(t("pet.errors.user_not_found.title", locale=locale), t("pet.errors.user_not_found.message", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # 查询用户装备的宠物
        user_response = supabase.table('users').select('equipped_pet_id').eq('id', user_internal_id).execute()
        if not user_response.data:
            embed = create_embed(t("pet.errors.user_not_found.title", locale=locale), t("pet.unequip.user_data_error", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        equipped_pet_id = user_response.data[0]['equipped_pet_id']
        
        if not equipped_pet_id:
            embed = create_embed(
                t("pet.errors.no_equipped_pet.title", locale=locale),
                t("pet.errors.no_equipped_pet.message", locale=locale, user=interaction.user.mention),
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        # 获取装备宠物的详细信息
        pet_response = supabase.table('user_pets').select('stars, pet_templates(cn_name, en_name, rarity)').eq('id', equipped_pet_id).execute()
        
        if not pet_response.data:
            embed = create_embed(
                t("pet.errors.user_not_found.title", locale=locale),
                t("pet.errors.equipped_pet_info_malformed", locale=locale, user=interaction.user.mention),
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        pet_data = pet_response.data[0]
        pet_template_data = pet_data['pet_templates']
        pet_name = get_localized_pet_name(pet_template_data, get_context_locale(interaction))
        rarity = pet_template_data['rarity']
        stars = pet_data['stars']
        
    except Exception as e:
        embed = create_embed(
            t("pet.errors.user_not_found.title", locale=locale),
            t("pet.unequip.query_error", locale=locale, user=interaction.user.mention),
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
            t("pet.unequip.claim_pending_points.title", locale=locale),
            t("pet.unequip.claim_pending_points.description", locale=locale, user=interaction.user.mention, points=pending_points),
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
        t("pet.unequip.success.title", locale=locale),
        t("pet.unequip.success.description", locale=locale, user=interaction.user.mention, pet_name=pet_name),
        discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)

async def handle_pet_status(interaction: discord.Interaction):
    """查看装备状态"""
    locale = get_guild_locale(interaction.guild.id)
    try:
        from src.db.database import get_supabase_client
        supabase = get_supabase_client()
        
        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if user_internal_id is None:
            embed = create_embed(t("pet.errors.user_not_found.title", locale=locale), t("pet.errors.user_not_found.message", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # 查询用户信息
        user_response = supabase.table('users').select('equipped_pet_id, points').eq('id', user_internal_id).execute()
        if not user_response.data:
            embed = create_embed(t("pet.errors.user_not_found.title", locale=locale), t("pet.status.user_data_error", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        user_data = user_response.data[0]
        equipped_pet_id = user_data.get('equipped_pet_id')
        current_points = user_data.get('points', 0)
        
        if not equipped_pet_id:
            embed = create_embed(
                t("pet.status.no_pet_equipped.title", locale=locale),
                t("pet.status.no_pet_equipped.description", locale=locale, user=interaction.user.mention, points=current_points),
                discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        # 获取宠物详细信息
        pet_response = supabase.table('user_pets').select('pet_template_id, stars, level').eq('id', equipped_pet_id).execute()
        
        if not pet_response.data:
            embed = create_embed(
                t("pet.status.pet_not_found.title", locale=locale),
                t("pet.status.pet_not_found.message", locale=locale, user=interaction.user.mention),
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        pet_data = pet_response.data[0]
        pet_template_id = pet_data['pet_template_id']
        stars = pet_data['stars']
        level = pet_data['level']

        # 获取宠物模板信息
        template_response = supabase.table('pet_templates').select('id, cn_name, en_name, rarity').eq('id', pet_template_id).execute()
        if not template_response.data:
            embed = create_embed(t("pet.upgrade.errors.template_not_found.title", locale=locale), t("pet.upgrade.errors.template_not_found.description", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return

        template_data = template_response.data[0]
        pet_name = get_localized_pet_name(template_data, get_context_locale(interaction))
        rarity = template_data['rarity']

        # 计算每小时积分和待领取积分
        pet_commands = PetCommands(None)
        hourly_points = pet_commands.calculate_pet_points(rarity, stars, 1, level)
        pending_points = pet_commands.calculate_pending_points(user_internal_id)
        
        star_display = '⭐' * stars if stars > 0 else '⚪'
        rarity_colors = {'C': '🤍', 'R': '💙', 'SR': '💜', 'SSR': '💛'}
        rarity_color = rarity_colors.get(rarity, '🤍')
        
        embed = create_embed(
            t("pet.status.title", locale=locale),
            t("pet.status.equipment_info", locale=locale, user=interaction.user.mention, pet_name=pet_name, rarity_color=rarity_color, rarity=rarity, stars=star_display, star_count=stars, level=level, hourly_points=hourly_points, pending_points=pending_points, points=current_points),
            discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        embed = create_embed(
            t("pet.errors.user_not_found.title", locale=locale),
            t("pet.status.query_error", locale=locale, user=interaction.user.mention),
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
        locale = get_guild_locale(interaction.guild.id)
        user_internal_id = get_user_internal_id(interaction)
        if user_internal_id is None:
            embed = create_embed(t("pet.errors.user_not_found.title", locale=locale), t("pet.errors.user_not_found.message", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # 查询用户信息
        user_response = supabase.table('users').select('equipped_pet_id, points').eq('id', user_internal_id).execute()
        if not user_response.data:
            embed = create_embed(t("pet.errors.user_not_found.title", locale=locale), t("pet.claim.user_data_error", locale=locale), discord.Color.red())
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
                template_response = supabase.table('pet_templates').select('*').eq('id', pet_template_id).execute()
                if template_response.data:
                    template_data = template_response.data[0]
                    pet_name = get_localized_pet_name(template_data, get_context_locale(interaction))
                    rarity = template_data['rarity']
    
        # 使用新方法计算待领取积分
        pet_commands = PetCommands(None)
        pending_points = pet_commands.calculate_pending_points(user_internal_id)
        
        if not equipped_pet_id:
            embed = create_embed(
                t("pet.claim.no_equipped_pet.title", locale=locale),
                t("pet.claim.no_equipped_pet.description", locale=locale, user=interaction.user.mention, points=current_points),
                discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        if pending_points <= 0:
            star_display = '⭐' * stars if stars > 0 else '⚪'
            rarity_colors = {'C': '🤍', 'R': '💙', 'SR': '💜', 'SSR': '💛'}
            rarity_color = rarity_colors.get(rarity, '🤍')
            
            embed = create_embed(
                t("pet.claim.no_points_to_claim.title", locale=locale),
                t("pet.claim.no_points_to_claim.description", locale=locale, user=interaction.user.mention, pet_name=pet_name, rarity_color=rarity_color, rarity=rarity, stars=star_display, star_count=stars, points=current_points),
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
            t("pet.claim.success.title", locale=locale),
            t("pet.claim.success.description", locale=locale, user=interaction.user.mention, pet_name=pet_name, rarity_color=rarity_color, rarity=rarity, stars=star_display, star_count=stars, points=pending_points, total=new_total_points),
            discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        locale = get_guild_locale(interaction.guild.id)
        print(t("pet.claim.debug_error", locale=locale, error=str(e)))
        embed = create_embed(
            t("pet.errors.user_not_found.title", locale=locale),
            t("pet.claim.query_error", locale=locale, user=interaction.user.mention),
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
        embed = create_embed(t("pet.errors.user_not_found.title", locale=locale), t("pet.errors.user_not_found.message", locale=locale), discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # 获取语言设置
    locale = get_guild_locale(interaction.guild.id)
    
    # 获取宠物喂食信息
    pet_info = get_pet_feeding_info(pet_id, locale)
    if not pet_info:
        embed = create_embed(t("pet.errors.user_not_found.title", locale=locale), t("pet.errors.pet_not_found_or_unauthorized_feed", locale=locale), discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # 检查宠物所有权
    if pet_info['user_id'] != user_internal_id:
        embed = create_embed(t("pet.errors.user_not_found.title", locale=locale), t("pet.errors.pet_not_owned", locale=locale), discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # 显示宠物喂食界面
    view = PetFeedingView(user_internal_id, pet_id, pet_info, interaction.guild.id if interaction.guild else None)
    embed = view.create_feeding_embed()

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class PetFeedingView(discord.ui.View):
    def __init__(self, user_id: int, pet_id: int, pet_info: dict, guild_id: int = None):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.pet_id = pet_id
        self.pet_info = pet_info
        self.guild_id = guild_id

        # 添加食粮选择下拉菜单
        self.add_item(FoodSelectForFeeding(user_id, pet_id, guild_id))

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

        # 获取语言环境
        locale = get_guild_locale(self.guild_id)

        rarity_color = rarity_colors.get(self.pet_info['rarity'], '⚪')
        favorite_flavor = t(f"pet.flavor_descriptions.{self.pet_info['favorite_flavor']}", locale=locale, default=t("pet.flavor_descriptions.no_preference", locale=locale))
        dislike_flavor = t(f"pet.flavor_descriptions.{self.pet_info['dislike_flavor']}", locale=locale, default=t("pet.flavor_descriptions.none", locale=locale))

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
        description += t("pet.feed.display.level", locale=locale, level=self.pet_info['level'])
        description += t("pet.feed.display.experience", locale=locale, current=self.pet_info['xp_current'], needed=self.pet_info['xp_next_level'])
        description += t("pet.feed.display.experience_bar", locale=locale, bar=progress_bar, percent=int(progress * 100) if self.pet_info['xp_next_level'] > 0 else 100)

        # 饱食度
        description += t("pet.feed.display.satiety", locale=locale, satiety=self.pet_info['satiety'])
        description += t("pet.feed.display.satiety_bar", locale=locale, bar=satiety_bar, satiety=self.pet_info['satiety'])

        # 口味偏好
        description += t("pet.feed.display.favorite", locale=locale, flavor=favorite_flavor)
        description += t("pet.feed.display.dislike", locale=locale, flavor=dislike_flavor)

        # 喂食说明
        if self.pet_info['satiety'] >= FeedingSystem.SATIETY_MAX:
            description += t("pet.feed.already_full", locale=locale)
        else:
            description += t("pet.feed.instructions.title", locale=locale)
            description += t("pet.feed.instructions.match_bonus", locale=locale)
            description += t("pet.feed.instructions.dislike_penalty", locale=locale)
            description += t("pet.feed.instructions.satiety_reset", locale=locale)

        embed = create_embed(
            t("pet.feed.title", locale=locale),
            description,
            discord.Color.green() if self.pet_info['satiety'] < FeedingSystem.SATIETY_MAX else discord.Color.orange()
        )

        return embed

class FoodSelectForFeeding(discord.ui.Select):
    def __init__(self, user_id: int, pet_id: int, guild_id: int = None):
        self.user_id = user_id
        self.pet_id = pet_id
        self.guild_id = guild_id

        options = self._load_food_options()

        locale = get_guild_locale(guild_id)
        super().__init__(
            placeholder=t("pet.feed.select_food.placeholder", locale=locale),
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

        locale = get_guild_locale(self.guild_id)
        if not response.data:
            return [discord.SelectOption(
                label=t("pet.feed.no_food_stock", locale=locale),
                description=t("pet.feed.go_shop_to_buy", locale=locale),
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

            food_name = get_localized_food_name(food, locale)
            label = f"{food_name} {flavor_emoji}"
            description = t("pet.feed.select_food.stock_format", locale=locale, quantity=quantity, xp=food['base_xp'])

            options.append(discord.SelectOption(
                label=label[:100],
                description=description[:100],
                value=str(food['id']),
                emoji=rarity_emoji
            ))

        return options

    async def callback(self, interaction: discord.Interaction):
        """处理食粮选择回调"""
        locale = get_guild_locale(interaction.guild.id)
        if self.values[0] == "none":
            await interaction.response.send_message(t("pet.feed.no_available_food", locale=locale), ephemeral=True)
            return

        food_template_id = int(self.values[0])

        # 执行喂食
        await execute_feeding(interaction, self.user_id, self.pet_id, food_template_id)

async def execute_feeding(interaction: discord.Interaction, user_id: int, pet_id: int, food_template_id: int):
    """执行喂食逻辑"""
    from src.db.database import get_supabase_client
    from src.utils.feeding_system import feed_pet

    locale = get_guild_locale(interaction.guild.id)
    supabase = get_supabase_client()

    try:
        # 检查食粮库存
        inventory_response = supabase.table('user_food_inventory').select('quantity').eq('user_id', user_id).eq('food_template_id', food_template_id).execute()

        if not inventory_response.data or inventory_response.data[0]['quantity'] <= 0:
            await interaction.response.send_message(t("pet.feed.insufficient_food_stock", locale=locale), ephemeral=True)
            return

        # 执行喂食
        result = feed_pet(pet_id, food_template_id, locale)

        if not result['success']:
            embed = create_embed(t("pet.feed.failure.title", locale=locale), result['message'], discord.Color.red())
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
        locale = get_guild_locale(interaction.guild.id)
        description = t("pet.feed.display.ate", locale=locale, user=interaction.user.mention, pet_name=result['pet_name'], food_name=result['food_name'])

        # 经验获得
        description += t("pet.feed.success.description.xp_gained", locale=locale, xp=result['xp_gained'])

        # 口味匹配bonus
        if result['flavor_bonus'] == 'favorite':
            description += t("pet.feed.success.description.flavor_match", locale=locale)
        elif result['flavor_bonus'] == 'dislike':
            description += t("pet.feed.success.description.dislike_penalty", locale=locale)

        # 饱食度
        description += t("pet.feed.success.description.satiety_increase", locale=locale, gained=result['satiety_gained'], new=result['new_satiety'])

        # 等级提升
        if result['level_up']:
            description += "\n" + t("pet.feed.success.description.level_up", locale=locale)
            description += t("pet.feed.success.description.new_level", locale=locale, level=result['new_level'])

        embed = create_embed(
            t("pet.feed.success.title", locale=locale),
            description,
            discord.Color.green()
        )

        # 如果饱食度满了，添加提示
        if result['new_satiety'] >= 100:
            embed.add_field(
                name=t("common.notice", locale=locale),
                value=t("pet.feed.satiety_full_notice", locale=locale),
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        print(t("pet.feed.execution_debug_error", locale=locale, error=str(e)))
        embed = create_embed(t("pet.feed.error.title", locale=locale), t("pet.feed.error.message", locale=locale), discord.Color.red())
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

        locale = get_context_locale(interaction)
        supabase = get_supabase_client()

        # 查询用户的宠物
        pets_response = supabase.table('user_pets').select('id, pet_template_id, stars').eq('user_id', user_internal_id).order('stars', desc=True).limit(25).execute()

        if not pets_response.data:
            return []

        # 获取宠物模板信息
        template_ids = list(set([pet['pet_template_id'] for pet in pets_response.data]))
        templates_response = supabase.table('pet_templates').select('id, cn_name, en_name, rarity').in_('id', template_ids).execute()

        # 创建模板映射
        template_map = {template['id']: template for template in templates_response.data}

        pets = []
        for pet in pets_response.data:
            template = template_map.get(pet['pet_template_id'])
            if template:
                pets.append({
                    'id': pet['id'],
                    'name': get_localized_pet_name(template, locale),
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
        print(f"Error in pet autocomplete: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

# 创建喂食模式选项（现在使用autocomplete，不再需要固定的choices函数）

async def feed_mode_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """为auto_feed命令的mode参数提供基于服务器语言的自动补全"""
    from src.utils.i18n import t, get_guild_locale

    # 获取服务器语言设置
    server_locale = get_guild_locale(interaction.guild.id)

    modes = [
        ("optimal_xp", "pet.auto_feed.command.choices.mode.optimal_xp"),
        ("flavor_match", "pet.auto_feed.command.choices.mode.flavor_match"),
        ("economic", "pet.auto_feed.command.choices.mode.economic"),
        ("clear_inventory", "pet.auto_feed.command.choices.mode.clear_inventory")
    ]

    choices = []
    for mode_value, translation_key in modes:
        # 使用服务器语言获取翻译
        localized_name = t(translation_key, locale=server_locale,
                         default=mode_value.replace("_", " ").title())

        # 如果用户有输入，进行过滤
        if current and current.lower() not in localized_name.lower() and current.lower() not in mode_value.lower():
            continue

        choices.append(app_commands.Choice(name=localized_name, value=mode_value))

    return choices

# 一键喂食命令
@app_commands.command(name="auto_feed", description="Auto feed - automatically select optimal food for specified pet")
@app_commands.describe(
    pet="Select pet to feed (leave empty to feed equipped pet)",
    mode="Feeding mode (strategy selection)",
    quantity="Number of times to feed (optional, default: until full)"
)
@app_commands.autocomplete(pet=pet_autocomplete, mode=feed_mode_autocomplete)
@app_commands.guild_only()
async def auto_feed(interaction: discord.Interaction, pet: str = None, mode: str = "optimal_xp", quantity: int = None):
    """一键喂食指定宠物或装备的宠物"""
    await handle_auto_feeding(interaction, mode, quantity, pet)

async def handle_auto_feeding(interaction: discord.Interaction, mode: str, quantity: int = None, pet_id: str = None):
    """处理一键喂食逻辑"""
    try:
        from src.utils.feeding_system import AutoFeedingSystem
        from src.utils.helpers import get_user_internal_id
        from src.db.database import get_supabase_client

        # 获取当前语言环境
        locale = get_guild_locale(interaction.guild.id)

        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed(t("pet.errors.user_not_found.title", locale=locale), t("pet.errors.user_not_found.message", locale=locale), discord.Color.red())
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
                    t("pet.auto_feed.errors.pet_not_exist_title", locale=locale),
                    t("pet.auto_feed.pet_not_exist", locale=locale, user=interaction.user.mention),
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
                    t("pet.auto_feed.errors.no_equipped_title", locale=locale),
                    t("pet.auto_feed.no_equipped_pet", locale=locale, user=interaction.user.mention),
                    discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            target_pet_id = user_response.data[0]['equipped_pet_id']

        # 发送初始响应
        await interaction.response.send_message(t("pet.feed.preparing_food", locale=locale), ephemeral=False)

        # 执行一键喂食
        result = AutoFeedingSystem.auto_feed_pet(user_internal_id, target_pet_id, mode, quantity, locale)

        if not result['success']:
            embed = create_embed(t("pet.feed.failure.title", locale=locale), result['message'], discord.Color.red())
            await interaction.edit_original_response(content="", embed=embed)
            return

        # 构建成功结果显示
        embed = create_auto_feeding_result_embed(interaction.user.mention, result, mode, locale)
        await interaction.edit_original_response(content="", embed=embed)

    except Exception as e:
        print(t("pet.feed.execution_debug_error", locale=locale, error=str(e)))
        embed = create_embed(t("pet.feed.error.title", locale=locale), t("pet.auto_feed.error", locale=locale, error=str(e)), discord.Color.red())
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.edit_original_response(content="", embed=embed)

def create_auto_feeding_result_embed(user_mention: str, result: dict, mode: str, locale: str) -> discord.Embed:
    """创建一键喂食结果展示"""

    # 使用翻译获取模式名称
    mode_name = t(f"pet.auto_feed.mode_names.{mode}", locale=locale, default=mode)

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

    description = t("pet.auto_feed.completed.description", locale=locale, user=user_mention) + "\n\n"

    # 基础统计信息
    description += t("pet.auto_feed.completed.statistics.title", locale=locale) + "\n"
    description += t("pet.auto_feed.completed.statistics.mode", locale=locale, mode=mode_name) + "\n"
    description += t("pet.auto_feed.completed.statistics.feed_count", locale=locale, count=result['total_feeds']) + "\n"
    description += t("pet.auto_feed.completed.statistics.xp_gained", locale=locale, xp=result['total_xp_gained']) + "\n"
    description += t("pet.auto_feed.completed.statistics.satiety_change", locale=locale, original=result['original_satiety'], new=result['new_satiety']) + "\n\n"

    # 使用的食粮详情
    if result['food_summary']:
        description += t("pet.auto_feed.completed.used_food.title", locale=locale) + "\n"
        for food_name, info in result['food_summary'].items():
            rarity_color = rarity_colors.get(info['rarity'], '⚪')
            flavor_emoji = flavor_emojis.get(info['flavor'], '🍽️')

            # 口味匹配提示
            match_text = ""
            if info['flavor_matches'] > 0:
                match_text = t("pet.auto_feed.completed.used_food.flavor_matches", locale=locale, count=info['flavor_matches'])

            description += f"{rarity_color} {food_name} {flavor_emoji} x{info['count']}{match_text}\n"
        description += "\n"

    # 等级变化
    if result['level_up']:
        description += t("pet.auto_feed.completed.level_up.title", locale=locale) + "\n"
        description += t("pet.auto_feed.completed.level_up.description", locale=locale, original=result['original_level'], new=result['new_level']) + "\n\n"

    # 宠物状态
    description += t("pet.auto_feed.completed.pet_status.title", locale=locale, name=result['pet_name']) + "\n"
    description += t("pet.auto_feed.completed.pet_status.level", locale=locale, level=result['new_level'])

    # 如果饱食度满了，添加提示
    if result['new_satiety'] >= 100:
        description += f"\n\n" + t("pet.auto_feed.completed.satiety_full_notice", locale=locale)

    embed = create_embed(t("pet.auto_feed.completed.title", locale=locale), description, discord.Color.green())

    return embed

async def handle_batch_dismantle_selection(interaction: discord.Interaction, pet_ids: list):
    """处理批量分解选择"""
    try:
        from src.db.database import get_supabase_client
        supabase = get_supabase_client()

        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed(
                t("pet.errors.user_not_found.title", locale=get_guild_locale(interaction.guild.id)),
                t("pet.errors.user_not_found.message", locale=get_guild_locale(interaction.guild.id)),
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        locale = get_guild_locale(interaction.guild.id)

        # 检查选择的宠物数量
        if len(pet_ids) > 20:
            embed = create_embed(
                t("pet.batch_dismantle.errors.too_many_pets.title", locale=locale),
                t("pet.batch_dismantle.errors.too_many_pets.message", locale=locale, count=20),
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 获取装备的宠物ID，防止分解装备的宠物
        user_response = supabase.table('users').select('equipped_pet_id').eq('id', user_internal_id).execute()
        equipped_pet_id = user_response.data[0]['equipped_pet_id'] if user_response.data else None

        # 获取选中宠物的详细信息
        pets_response = supabase.table('user_pets').select('id, pet_template_id, stars').eq('user_id', user_internal_id).in_('id', pet_ids).execute()

        if not pets_response.data or len(pets_response.data) != len(pet_ids):
            embed = create_embed(
                t("pet.errors.pet_not_found_or_unauthorized", locale=locale),
                t("pet.batch_dismantle.errors.invalid_pets", locale=locale),
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 检查是否有装备的宠物
        invalid_pets = []
        valid_pets = []

        for pet in pets_response.data:
            if pet['id'] == equipped_pet_id:
                invalid_pets.append(pet['id'])
            else:
                valid_pets.append(pet)

        if invalid_pets:
            embed = create_embed(
                t("pet.batch_dismantle.errors.equipped_included.title", locale=locale),
                t("pet.batch_dismantle.errors.equipped_included.message", locale=locale),
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if not valid_pets:
            embed = create_embed(
                t("pet.batch_dismantle.errors.no_valid_pets.title", locale=locale),
                t("pet.batch_dismantle.errors.no_valid_pets.message", locale=locale),
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 获取宠物模板信息
        template_ids = list(set([pet['pet_template_id'] for pet in valid_pets]))
        templates_response = supabase.table('pet_templates').select('id, cn_name, en_name, rarity').in_('id', template_ids).execute()

        template_map = {template['id']: template for template in templates_response.data}

        # 计算总收益
        total_fragments_by_rarity = {'C': 0, 'R': 0, 'SR': 0, 'SSR': 0}
        total_points = 0
        pet_details = []

        for pet in valid_pets:
            template = template_map.get(pet['pet_template_id'])
            if template:
                rarity = template['rarity']
                stars = pet['stars']

                # 计算单个宠物的分解收益
                base_fragments = 10
                star_bonus_fragments = stars
                star_bonus_points = stars * 200

                total_fragments_by_rarity[rarity] += base_fragments + star_bonus_fragments
                total_points += star_bonus_points

                pet_name = get_localized_pet_name(template, locale)
                pet_details.append({
                    'id': pet['id'],
                    'name': pet_name,
                    'rarity': rarity,
                    'stars': stars,
                    'fragments': base_fragments + star_bonus_fragments,
                    'points': star_bonus_points
                })

        # 创建确认界面
        view = BatchDismantleConfirmView(
            interaction.guild.id,
            interaction.user.id,
            user_internal_id,
            pet_details,
            total_fragments_by_rarity,
            total_points
        )

        await interaction.response.send_message(embed=view.create_confirm_embed(), view=view, ephemeral=True)

    except Exception as e:
        locale = get_guild_locale(interaction.guild.id)
        print(f"Error in batch dismantle selection: {str(e)}")
        embed = create_embed(
            t("pet.errors.system_error.title", locale=locale),
            t("pet.batch_dismantle.errors.selection_error", locale=locale, error=str(e)),
            discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)


class BatchDismantleConfirmView(discord.ui.View):
    """批量分解确认界面"""
    def __init__(self, guild_id, discord_user_id, user_internal_id, pet_details, total_fragments_by_rarity, total_points):
        super().__init__(timeout=60)
        self.guild_id = guild_id
        self.discord_user_id = discord_user_id
        self.user_internal_id = user_internal_id
        self.pet_details = pet_details
        self.total_fragments_by_rarity = total_fragments_by_rarity
        self.total_points = total_points
        self.user_mention = f"<@{discord_user_id}>"

        # 获取语言环境并设置按钮
        locale = get_guild_locale(guild_id)

        # 添加确认按钮
        confirm_button = discord.ui.Button(
            label=t("pet.ui.buttons.confirm_batch_dismantle", locale=locale),
            style=discord.ButtonStyle.danger,
            emoji='💥',
            custom_id='confirm_batch_dismantle'
        )
        confirm_button.callback = self.confirm_callback
        self.add_item(confirm_button)

        # 添加取消按钮
        cancel_button = discord.ui.Button(
            label=t("pet.ui.buttons.cancel", locale=locale),
            style=discord.ButtonStyle.secondary,
            emoji='❌',
            custom_id='cancel_batch_dismantle'
        )
        cancel_button.callback = self.cancel_callback
        self.add_item(cancel_button)

    def create_confirm_embed(self):
        """创建确认界面的embed"""
        locale = get_guild_locale(self.guild_id)

        description = t("pet.batch_dismantle.confirm.description", locale=locale,
                       user=self.user_mention, count=len(self.pet_details))
        description += "\n\n" + t("pet.batch_dismantle.confirm.selected_pets", locale=locale) + "\n"

        # 显示选中的宠物列表（限制显示数量）
        rarity_emojis = {'C': '⚪', 'R': '🔵', 'SR': '🟣', 'SSR': '🟡'}
        display_count = min(10, len(self.pet_details))  # 最多显示10个

        for i, pet in enumerate(self.pet_details[:display_count]):
            emoji = rarity_emojis.get(pet['rarity'], '⚪')
            star_display = "⭐" * pet['stars'] if pet['stars'] > 0 else ""
            description += f"{emoji} {pet['name']} {star_display}\n"

        if len(self.pet_details) > display_count:
            description += t("pet.batch_dismantle.confirm.more_pets", locale=locale,
                            remaining=len(self.pet_details) - display_count)

        description += "\n\n" + t("pet.batch_dismantle.confirm.benefits", locale=locale) + "\n"

        # 显示各稀有度碎片数量
        for rarity in ['SSR', 'SR', 'R', 'C']:
            if self.total_fragments_by_rarity[rarity] > 0:
                emoji = rarity_emojis.get(rarity, '⚪')
                description += f"{emoji} {rarity}碎片: +{self.total_fragments_by_rarity[rarity]}个\n"

        if self.total_points > 0:
            description += t("pet.batch_dismantle.confirm.points", locale=locale, points=self.total_points)

        description += "\n\n" + t("pet.batch_dismantle.confirm.warning", locale=locale)

        embed = create_embed(
            t("pet.batch_dismantle.confirm.title", locale=locale),
            description,
            discord.Color.orange()
        )

        return embed

    async def confirm_callback(self, interaction: discord.Interaction):
        """确认批量分解的回调"""
        # 验证用户身份
        if interaction.user.id != self.discord_user_id:
            await interaction.response.send_message(
                t("pet.errors.unauthorized_operation", locale=get_guild_locale(interaction.guild.id)),
                ephemeral=True
            )
            return

        await self.execute_batch_dismantle(interaction)

    async def cancel_callback(self, interaction: discord.Interaction):
        """取消批量分解的回调"""
        # 验证用户身份
        if interaction.user.id != self.discord_user_id:
            await interaction.response.send_message(
                t("pet.errors.unauthorized_operation", locale=get_guild_locale(interaction.guild.id)),
                ephemeral=True
            )
            return

        locale = get_guild_locale(interaction.guild.id)
        embed = create_embed(
            t("pet.batch_dismantle.cancelled.title", locale=locale),
            t("pet.batch_dismantle.cancelled.message", locale=locale, user=self.user_mention),
            discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=None)

    async def execute_batch_dismantle(self, interaction: discord.Interaction):
        """执行批量分解"""
        try:
            from src.db.database import get_supabase_client
            supabase = get_supabase_client()

            locale = get_guild_locale(interaction.guild.id)

            # 获取PetCommands实例来使用add_fragments方法
            pet_commands = PetCommands(None)

            # 开始事务性操作
            dismantled_pets = []
            errors = []
            total_points_earned = 0
            total_fragments_by_rarity = {'C': 0, 'R': 0, 'SR': 0, 'SSR': 0}

            # 验证所有宠物仍然可以被分解（防止并发操作）
            user_response = supabase.table('users').select('equipped_pet_id').eq('id', self.user_internal_id).execute()
            current_equipped_pet_id = user_response.data[0]['equipped_pet_id'] if user_response.data else None

            for pet in self.pet_details:
                if pet['id'] == current_equipped_pet_id:
                    errors.append(f"{pet['name']} - 已装备")
                    continue

                try:
                    # 删除宠物记录
                    supabase.table('user_pets').delete().eq('id', pet['id']).eq('user_id', self.user_internal_id).execute()

                    # 异步添加碎片
                    await pet_commands.add_fragments_async(self.user_internal_id, pet['rarity'], pet['fragments'])

                    # 累积积分和碎片
                    total_points_earned += pet.get('points', 0)
                    total_fragments_by_rarity[pet['rarity']] += pet['fragments']

                    dismantled_pets.append(pet)

                except Exception as e:
                    errors.append(f"{pet['name']} - 分解失败: {str(e)}")

            # 添加总积分（如果有）
            if total_points_earned > 0:
                from src.utils.cache import UserCache
                await UserCache.update_points(
                    interaction.guild.id,
                    interaction.user.id,
                    self.user_internal_id,
                    total_points_earned
                )

            # 如果所有操作都失败了
            if not dismantled_pets:
                embed = create_embed(
                    t("pet.batch_dismantle.errors.all_failed.title", locale=locale),
                    t("pet.batch_dismantle.errors.all_failed.message", locale=locale) + "\n" + "\n".join(errors),
                    discord.Color.red()
                )
                # 先编辑原消息（移除按钮）
                await interaction.response.edit_message(
                    content=t("pet.dismantle.confirm.batch_failed", locale=locale),
                    embed=None,
                    view=None
                )
                # 发送公开错误消息
                await interaction.followup.send(embed=embed)
                return

            # 创建结果embed
            embed = self.create_result_embed(dismantled_pets, errors, total_points_earned, total_fragments_by_rarity)
            # 先编辑原消息（移除按钮）
            await interaction.response.edit_message(
                content=t("pet.dismantle.confirm.batch_completed", locale=locale),
                embed=None,
                view=None
            )
            # 发送公开结果消息
            await interaction.followup.send(embed=embed)

        except Exception as e:
            locale = get_guild_locale(interaction.guild.id)
            print(f"Error executing batch dismantle: {str(e)}")
            embed = create_embed(
                t("pet.errors.system_error.title", locale=locale),
                t("pet.batch_dismantle.errors.execution_error", locale=locale, error=str(e)),
                discord.Color.red()
            )
            # 先编辑原消息（移除按钮）
            await interaction.response.edit_message(
                content=t("pet.dismantle.confirm.batch_error", locale=locale),
                embed=None,
                view=None
            )
            # 发送公开错误消息
            await interaction.followup.send(embed=embed)

    def create_result_embed(self, dismantled_pets, errors, total_points_earned=0, total_fragments_by_rarity=None):
        """创建分解结果的embed"""
        locale = get_guild_locale(self.guild_id)

        if total_fragments_by_rarity is None:
            total_fragments_by_rarity = {'C': 0, 'R': 0, 'SR': 0, 'SSR': 0}

        # 智能显示：如果有失败的宠物则显示总数，否则只显示成功数量
        success_count = len(dismantled_pets)
        total_count = len(self.pet_details)

        if success_count == total_count:
            # 全部成功，不显示总数
            description = t("pet.batch_dismantle.completed.description_all_success", locale=locale,
                           user=self.user_mention, success_count=success_count)
        else:
            # 部分失败，显示总数
            description = t("pet.batch_dismantle.completed.description", locale=locale,
                           user=self.user_mention, success_count=success_count, total_count=total_count)

        # 显示获得的积分和碎片
        if dismantled_pets and (total_points_earned > 0 or any(count > 0 for count in total_fragments_by_rarity.values())):
            description += "\n\n" + t("pet.batch_dismantle.completed.rewards", locale=locale) + "\n"

            # 显示积分
            if total_points_earned > 0:
                description += f"💰 {t('pet.batch_dismantle.completed.points', locale=locale, points=total_points_earned)}\n"

            # 显示碎片
            rarity_emojis = {'C': '⚪', 'R': '🔵', 'SR': '🟣', 'SSR': '🟡'}
            rarity_names = {'C': '普通', 'R': '稀有', 'SR': '史诗', 'SSR': '传说'}

            for rarity, count in total_fragments_by_rarity.items():
                if count > 0:
                    emoji = rarity_emojis.get(rarity, '⚪')
                    rarity_name = rarity_names.get(rarity, rarity)
                    description += f"{emoji} {t('pet.batch_dismantle.completed.fragments', locale=locale, count=count, rarity=rarity_name)}\n"

        if dismantled_pets:
            description += "\n\n" + t("pet.batch_dismantle.completed.dismantled_pets", locale=locale) + "\n"

            rarity_emojis = {'C': '⚪', 'R': '🔵', 'SR': '🟣', 'SSR': '🟡'}
            display_count = min(8, len(dismantled_pets))

            for pet in dismantled_pets[:display_count]:
                emoji = rarity_emojis.get(pet['rarity'], '⚪')
                star_display = "⭐" * pet['stars'] if pet['stars'] > 0 else ""
                description += f"{emoji} {pet['name']} {star_display}\n"

            if len(dismantled_pets) > display_count:
                description += t("pet.batch_dismantle.completed.more_pets", locale=locale,
                                remaining=len(dismantled_pets) - display_count)

        if errors:
            description += "\n\n" + t("pet.batch_dismantle.completed.errors", locale=locale) + "\n"
            for error in errors[:3]:  # 最多显示3个错误
                description += f"• {error}\n"
            if len(errors) > 3:
                description += f"• ... 还有{len(errors) - 3}个错误"

        embed = create_embed(
            t("pet.batch_dismantle.completed.title", locale=locale),
            description,
            discord.Color.green() if not errors else discord.Color.orange()
        )

        return embed


async def handle_batch_dismantle_mode_selection(interaction: discord.Interaction):
    """处理批量分解模式选择"""
    try:
        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed(
                t("pet.errors.user_not_found.title", locale=get_context_locale(interaction)),
                t("pet.errors.user_not_found.message", locale=get_context_locale(interaction)),
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        locale = get_context_locale(interaction)

        # 创建模式选择界面
        view = BatchDismantleModeView(interaction.user.id, user_internal_id, interaction.guild.id)
        embed = view.create_mode_selection_embed()

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    except Exception as e:
        locale = get_context_locale(interaction)
        print(f"Error in batch dismantle mode selection: {str(e)}")
        embed = create_embed(
            t("pet.errors.system_error.title", locale=locale),
            t("pet.batch_dismantle.errors.mode_selection_error", locale=locale, error=str(e)),
            discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)


class BatchDismantleModeView(discord.ui.View):
    """批量分解模式选择界面"""
    def __init__(self, discord_user_id, user_internal_id, guild_id):
        super().__init__(timeout=60)
        self.discord_user_id = discord_user_id
        self.user_internal_id = user_internal_id
        self.guild_id = guild_id

        # 添加模式选择按钮
        self.add_item(BatchDismantleModeSelect(self.guild_id))

    def create_mode_selection_embed(self):
        """创建模式选择界面的embed"""
        locale = get_guild_locale(self.guild_id)

        description = t("pet.batch_dismantle.mode.description", locale=locale)
        description += "\n\n" + t("pet.batch_dismantle.mode.options.description", locale=locale)
        description += "\n\n" + t("pet.batch_dismantle.mode.manual.description", locale=locale)
        description += "\n\n" + t("pet.batch_dismantle.mode.auto.description", locale=locale)

        embed = create_embed(
            t("pet.batch_dismantle.mode.title", locale=locale),
            description,
            discord.Color.blue()
        )

        return embed

    async def handle_mode_selection(self, interaction: discord.Interaction, mode: str):
        """处理模式选择"""
        # 验证用户身份
        if interaction.user.id != self.discord_user_id:
            await interaction.response.send_message(
                t("pet.errors.unauthorized_operation", locale=get_context_locale(interaction)),
                ephemeral=True
            )
            return

        if mode == "select":
            # 手动选择模式 - 显示宠物选择界面
            await self.show_manual_selection(interaction)
        elif mode == "auto":
            # 自动筛选模式 - 显示筛选参数界面
            await self.show_auto_selection(interaction)

    async def show_manual_selection(self, interaction: discord.Interaction):
        """显示手动选择界面"""
        try:
            guild_id = interaction.guild.id if interaction.guild else None
            view = PetSelectView(self.user_internal_id, "batch_dismantle", guild_id)
            has_pets = await view.setup_select()

            if not has_pets:
                locale = get_context_locale(interaction)
                embed = create_embed(
                    t("pet.errors.no_pets.title", locale=locale),
                    t("pet.errors.no_pets.message", locale=locale),
                    discord.Color.red()
                )
                await interaction.response.edit_message(embed=embed, view=None)
                return

            action_names = {
                "batch_dismantle": t("pet.command.choices.batch_dismantle", locale=get_context_locale(interaction))
            }

            embed = create_embed(
                f"🐾 {action_names['batch_dismantle']}",
                t("pet.batch_dismantle.manual.description", locale=get_context_locale(interaction)),
                discord.Color.blue()
            )
            await interaction.response.edit_message(embed=embed, view=view)

        except Exception as e:
            locale = get_context_locale(interaction)
            print(f"Error showing manual selection: {str(e)}")
            embed = create_embed(
                t("pet.errors.system_error.title", locale=locale),
                t("pet.batch_dismantle.errors.manual_selection_error", locale=locale, error=str(e)),
                discord.Color.red()
            )
            await interaction.response.edit_message(embed=embed, view=None)

    async def show_auto_selection(self, interaction: discord.Interaction):
        """显示自动筛选界面"""
        try:
            view = BatchDismantleAutoView(self.discord_user_id, self.user_internal_id, self.guild_id)
            embed = view.create_auto_selection_embed()

            await interaction.response.edit_message(embed=embed, view=view)

        except Exception as e:
            locale = get_context_locale(interaction)
            print(f"Error showing auto selection: {str(e)}")
            embed = create_embed(
                t("pet.errors.system_error.title", locale=locale),
                t("pet.batch_dismantle.errors.auto_selection_error", locale=locale, error=str(e)),
                discord.Color.red()
            )
            await interaction.response.edit_message(embed=embed, view=None)


class BatchDismantleModeSelect(discord.ui.Select):
    """批量分解模式选择下拉菜单"""
    def __init__(self, guild_id):
        self.guild_id = guild_id
        locale = get_guild_locale(guild_id)

        options = [
            discord.SelectOption(
                label=t("pet.batch_dismantle.mode.manual.label", locale=locale),
                description=t("pet.batch_dismantle.mode.manual.description_short", locale=locale),
                value="select",
                emoji="🎯"
            ),
            discord.SelectOption(
                label=t("pet.batch_dismantle.mode.auto.label", locale=locale),
                description=t("pet.batch_dismantle.mode.auto.description_short", locale=locale),
                value="auto",
                emoji="⚡"
            )
        ]

        super().__init__(
            placeholder=t("pet.batch_dismantle.mode.placeholder", locale=locale),
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        """处理模式选择回调"""
        selected_mode = self.values[0]
        view = self.view  # 获取父视图
        await view.handle_mode_selection(interaction, selected_mode)


class BatchDismantleAutoView(discord.ui.View):
    """批量分解自动筛选界面"""
    def __init__(self, discord_user_id, user_internal_id, guild_id):
        super().__init__(timeout=60)
        self.discord_user_id = discord_user_id
        self.user_internal_id = user_internal_id
        self.guild_id = guild_id

        # 添加筛选选项下拉菜单
        self.add_item(BatchDismantleRarityFilter(self.guild_id))
        self.add_item(BatchDismantleStarFilter(self.guild_id))

        # 添加确认按钮
        locale = get_guild_locale(guild_id)
        confirm_button = discord.ui.Button(
            label=t("pet.ui.buttons.apply_filters", locale=locale),
            style=discord.ButtonStyle.primary,
            emoji="✅"
        )
        confirm_button.callback = self.apply_filters
        self.add_item(confirm_button)

        # 为下拉菜单添加回调，以便在选择时更新embed
        for child in self.children:
            if isinstance(child, (BatchDismantleRarityFilter, BatchDismantleStarFilter)):
                child.callback = self.on_filter_select

    def create_auto_selection_embed(self, rarity_filter=None, star_filter=None):
        """创建自动筛选界面的embed"""
        locale = get_guild_locale(self.guild_id)

        description = t("pet.batch_dismantle.auto.description", locale=locale)
        description += "\n\n" + t("pet.batch_dismantle.auto.instructions", locale=locale)

        # 添加当前选择的筛选条件
        if rarity_filter or star_filter:
            description += "\n\n" + t("pet.batch_dismantle.auto.current_filters", locale=locale)

            if rarity_filter:
                rarity_text = self.get_rarity_filter_text(rarity_filter, locale)
                description += f"\n🏷️ {t('pet.batch_dismantle.auto.filter_label.rarity', locale=locale)}: {rarity_text}"

            if star_filter:
                star_text = self.get_star_filter_text(star_filter, locale)
                description += f"\n⭐ {t('pet.batch_dismantle.auto.filter_label.star', locale=locale)}: {star_text}"

        embed = create_embed(
            t("pet.batch_dismantle.auto.title", locale=locale),
            description,
            discord.Color.purple()
        )

        return embed

    def get_rarity_filter_text(self, rarity_filter, locale):
        """获取稀有度筛选条件的显示文本"""
        rarity_texts = {
            'c': t("pet.batch_dismantle.filter.rarity.c_only", locale=locale),
            'r': t("pet.batch_dismantle.filter.rarity.r_only", locale=locale),
            'sr': t("pet.batch_dismantle.filter.rarity.sr_only", locale=locale),
            'ssr': t("pet.batch_dismantle.filter.rarity.ssr_only", locale=locale),
            'below_sr': t("pet.batch_dismantle.filter.rarity.below_sr", locale=locale),
            'below_ssr': t("pet.batch_dismantle.filter.rarity.below_ssr", locale=locale),
        }
        return rarity_texts.get(rarity_filter, rarity_filter)

    def get_star_filter_text(self, star_filter, locale):
        """获取星级筛选条件的显示文本"""
        star_texts = {
            'max_0': t("pet.batch_dismantle.filter.star.max_0", locale=locale),
            'max_1': t("pet.batch_dismantle.filter.star.max_1", locale=locale),
            'max_2': t("pet.batch_dismantle.filter.star.max_2", locale=locale),
            'max_3': t("pet.batch_dismantle.filter.star.max_3", locale=locale),
        }
        return star_texts.get(star_filter, star_filter)

    async def on_filter_select(self, interaction: discord.Interaction):
        """处理筛选选择回调"""
        # 验证用户身份
        if interaction.user.id != self.discord_user_id:
            await interaction.response.send_message(
                t("pet.errors.unauthorized_operation", locale=get_context_locale(interaction)),
                ephemeral=True
            )
            return

        # 获取当前选择的筛选条件
        rarity_filter = None
        star_filter = None

        for child in self.children:
            if isinstance(child, BatchDismantleRarityFilter):
                rarity_filter = child.values[0] if child.values else None
            elif isinstance(child, BatchDismantleStarFilter):
                star_filter = child.values[0] if child.values else None

        # 更新embed显示当前选择
        locale = get_guild_locale(self.guild_id)
        embed = self.create_auto_selection_embed(rarity_filter, star_filter)

        # 获取当前视图内容并更新
        if not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.message.edit(embed=embed, view=self)

    async def apply_filters(self, interaction: discord.Interaction):
        """应用筛选条件并执行自动批量分解"""
        # 验证用户身份
        if interaction.user.id != self.discord_user_id:
            await interaction.response.send_message(
                t("pet.errors.unauthorized_operation", locale=get_context_locale(interaction)),
                ephemeral=True
            )
            return

        # 获取筛选条件
        rarity_filter = None
        star_filter = None

        for child in self.children:
            if isinstance(child, BatchDismantleRarityFilter):
                rarity_filter = child.values[0] if child.values else None
            elif isinstance(child, BatchDismantleStarFilter):
                star_filter = child.values[0] if child.values else None

        await self.execute_auto_dismantle(interaction, rarity_filter, star_filter)

    async def execute_auto_dismantle(self, interaction: discord.Interaction, rarity_filter, star_filter):
        """执行自动筛选和批量分解"""
        try:
            from src.db.database import get_supabase_client
            supabase = get_supabase_client()

            locale = get_context_locale(interaction)

            # 构建查询条件
            query = supabase.table('user_pets').select('id, pet_template_id, stars').eq('user_id', self.user_internal_id)

            # 获取装备的宠物ID
            user_response = supabase.table('users').select('equipped_pet_id').eq('id', self.user_internal_id).execute()
            equipped_pet_id = user_response.data[0]['equipped_pet_id'] if user_response.data else None

            # 获取所有用户宠物
            pets_response = query.execute()

            if not pets_response.data:
                embed = create_embed(
                    t("pet.batch_dismantle.errors.no_pets.title", locale=locale),
                    t("pet.batch_dismantle.errors.no_pets.message", locale=locale),
                    discord.Color.red()
                )
                await interaction.response.edit_message(embed=embed, view=None)
                return

            # 获取宠物模板信息用于筛选
            pet_ids = [pet['id'] for pet in pets_response.data]
            template_ids = [pet['pet_template_id'] for pet in pets_response.data]

            templates_response = supabase.table('pet_templates').select('id, cn_name, en_name, rarity').in_('id', template_ids).execute()
            template_map = {template['id']: template for template in templates_response.data}

            # 应用筛选条件
            filtered_pets = []
            for pet in pets_response.data:
                # 跳过装备的宠物
                if pet['id'] == equipped_pet_id:
                    continue

                template = template_map.get(pet['pet_template_id'])
                if not template:
                    continue

                # 应用稀有度筛选
                if rarity_filter:
                    if not self.rarity_matches_filter(template['rarity'], rarity_filter):
                        continue

                # 应用星级筛选
                if star_filter:
                    if not self.star_matches_filter(pet['stars'], star_filter):
                        continue

                filtered_pets.append({
                    'id': pet['id'],
                    'pet_template_id': pet['pet_template_id'],
                    'stars': pet['stars'],
                    'template': template
                })

            if not filtered_pets:
                embed = create_embed(
                    t("pet.batch_dismantle.auto.no_matches.title", locale=locale),
                    t("pet.batch_dismantle.auto.no_matches.message", locale=locale),
                    discord.Color.orange()
                )
                await interaction.response.edit_message(embed=embed, view=None)
                return

            # 限制最多20只宠物
            selected_pets = filtered_pets[:20]

            # 准备批量分解数据
            pet_details = []
            total_fragments_by_rarity = {'C': 0, 'R': 0, 'SR': 0, 'SSR': 0}
            total_points = 0

            for pet in selected_pets:
                template = pet['template']
                rarity = template['rarity']
                stars = pet['stars']

                # 计算分解收益
                base_fragments = 10
                star_bonus_fragments = stars
                star_bonus_points = stars * 200

                total_fragments_by_rarity[rarity] += base_fragments + star_bonus_fragments
                total_points += star_bonus_points

                pet_name = get_localized_pet_name(template, locale)
                pet_details.append({
                    'id': pet['id'],
                    'name': pet_name,
                    'rarity': rarity,
                    'stars': stars,
                    'fragments': base_fragments + star_bonus_fragments,
                    'points': star_bonus_points
                })

            # 创建确认界面
            view = BatchDismantleConfirmView(
                interaction.guild.id,
                interaction.user.id,
                self.user_internal_id,
                pet_details,
                total_fragments_by_rarity,
                total_points
            )

            await interaction.response.edit_message(embed=view.create_confirm_embed(), view=view)

        except Exception as e:
            locale = get_context_locale(interaction)
            print(f"Error executing auto dismantle: {str(e)}")
            embed = create_embed(
                t("pet.errors.system_error.title", locale=locale),
                t("pet.batch_dismantle.errors.auto_execution_error", locale=locale, error=str(e)),
                discord.Color.red()
            )
            await interaction.response.edit_message(embed=embed, view=None)

    def rarity_matches_filter(self, rarity, rarity_filter):
        """检查稀有度是否匹配筛选条件"""
        filters = {
            'c': ['C'],
            'r': ['R'],
            'sr': ['SR'],
            'ssr': ['SSR'],
            'below_sr': ['C', 'R'],
            'below_ssr': ['C', 'R', 'SR']
        }
        return rarity in filters.get(rarity_filter, [])

    def star_matches_filter(self, stars, star_filter):
        """检查星级是否匹配筛选条件"""
        max_stars = {
            'max_0': 0,
            'max_1': 1,
            'max_2': 2,
            'max_3': 3
        }
        return stars <= max_stars.get(star_filter, float('inf'))


class BatchDismantleRarityFilter(discord.ui.Select):
    """稀有度筛选下拉菜单"""
    def __init__(self, guild_id):
        self.guild_id = guild_id
        locale = get_guild_locale(guild_id)

        options = [
            discord.SelectOption(
                label=t("pet.batch_dismantle.filter.rarity.all", locale=locale),
                description=t("pet.batch_dismantle.filter.rarity.all_desc", locale=locale),
                value="all"
            ),
            discord.SelectOption(
                label=t("pet.batch_dismantle.filter.rarity.c_only", locale=locale),
                description=t("pet.batch_dismantle.filter.rarity.c_desc", locale=locale),
                value="c"
            ),
            discord.SelectOption(
                label=t("pet.batch_dismantle.filter.rarity.r_only", locale=locale),
                description=t("pet.batch_dismantle.filter.rarity.r_desc", locale=locale),
                value="r"
            ),
            discord.SelectOption(
                label=t("pet.batch_dismantle.filter.rarity.sr_only", locale=locale),
                description=t("pet.batch_dismantle.filter.rarity.sr_desc", locale=locale),
                value="sr"
            ),
            discord.SelectOption(
                label=t("pet.batch_dismantle.filter.rarity.ssr_only", locale=locale),
                description=t("pet.batch_dismantle.filter.rarity.ssr_desc", locale=locale),
                value="ssr"
            ),
            discord.SelectOption(
                label=t("pet.batch_dismantle.filter.rarity.below_sr", locale=locale),
                description=t("pet.batch_dismantle.filter.rarity.below_sr_desc", locale=locale),
                value="below_sr"
            ),
            discord.SelectOption(
                label=t("pet.batch_dismantle.filter.rarity.below_ssr", locale=locale),
                description=t("pet.batch_dismantle.filter.rarity.below_ssr_desc", locale=locale),
                value="below_ssr"
            )
        ]

        super().__init__(
            placeholder=t("pet.batch_dismantle.filter.rarity.placeholder", locale=locale),
            options=options,
            min_values=1,
            max_values=1
        )


class BatchDismantleStarFilter(discord.ui.Select):
    """星级筛选下拉菜单"""
    def __init__(self, guild_id):
        self.guild_id = guild_id
        locale = get_guild_locale(guild_id)

        options = [
            discord.SelectOption(
                label=t("pet.batch_dismantle.filter.star.all", locale=locale),
                description=t("pet.batch_dismantle.filter.star.all_desc", locale=locale),
                value="all"
            ),
            discord.SelectOption(
                label=t("pet.batch_dismantle.filter.star.max_0", locale=locale),
                description=t("pet.batch_dismantle.filter.star.max_0_desc", locale=locale),
                value="max_0"
            ),
            discord.SelectOption(
                label=t("pet.batch_dismantle.filter.star.max_1", locale=locale),
                description=t("pet.batch_dismantle.filter.star.max_1_desc", locale=locale),
                value="max_1"
            ),
            discord.SelectOption(
                label=t("pet.batch_dismantle.filter.star.max_2", locale=locale),
                description=t("pet.batch_dismantle.filter.star.max_2_desc", locale=locale),
                value="max_2"
            ),
            discord.SelectOption(
                label=t("pet.batch_dismantle.filter.star.max_3", locale=locale),
                description=t("pet.batch_dismantle.filter.star.max_3_desc", locale=locale),
                value="max_3"
            )
        ]

        super().__init__(
            placeholder=t("pet.batch_dismantle.filter.star.placeholder", locale=locale),
            options=options,
            min_values=1,
            max_values=1
        )


def setup(bot):
    """注册斜杠命令"""
    bot.tree.add_command(pet)
    bot.tree.add_command(auto_feed)