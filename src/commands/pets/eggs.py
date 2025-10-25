import discord
from discord.ext import commands
from discord import app_commands
import random
import datetime
from src.db.database import get_connection
from src.utils.ui import create_embed
from src.utils.helpers import get_user_internal_id, get_user_data_sync
from src.utils.i18n import get_guild_locale, t, get_context_locale, get_localized_pet_name
from src.utils.draw_limiter import DrawLimiter
from src.utils.cache import UserCache

class EggCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 抽蛋成本配置
    SINGLE_DRAW_COST = 250
    TEN_DRAW_COST = 2250

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
    def get_pet_names(locale=None):
        """从数据库获取宠物名称"""
        supabase = get_connection()

        try:
            result = supabase.table("pet_templates").select("id, en_name, rarity").execute()

            # 组织数据为字典格式
            pet_names = {}
            for template in result.data:
                pet_name = get_localized_pet_name(template, locale)
                rarity = template["rarity"]
                if rarity not in pet_names:
                    pet_names[rarity] = []
                pet_names[rarity].append(pet_name)

            return pet_names

        except Exception as e:
            print(f"获取宠物名称失败: {e}")
            return {}

    @staticmethod
    def get_draw_probabilities():
        """从数据库获取抽蛋概率配置"""
        supabase = get_connection()

        try:
            result = supabase.table("egg_draw_probabilities").select("rarity, probability").execute()

            # 按指定顺序排序
            order = ['SSR', 'SR', 'R', 'C']
            probabilities = []
            for rarity in order:
                for item in result.data:
                    if item["rarity"] == rarity:
                        probabilities.append((item["rarity"], item["probability"]))
                        break

            return probabilities

        except Exception as e:
            print(f"获取抽蛋概率失败: {e}")
            return []

    @staticmethod
    def get_hatch_probabilities(egg_rarity):
        """从数据库获取指定蛋稀有度的孵化概率配置"""
        supabase = get_connection()

        try:
            result = supabase.table("egg_hatch_probabilities").select("pet_rarity, probability").eq("egg_rarity", egg_rarity).execute()

            # 按指定顺序排序
            order = ['SSR', 'SR', 'R', 'C']
            probabilities = []
            for rarity in order:
                for item in result.data:
                    if item["pet_rarity"] == rarity:
                        probabilities.append((item["pet_rarity"], item["probability"]))
                        break

            return probabilities

        except Exception as e:
            print(f"获取孵化概率失败: {e}")
            return []

# 创建蛋action选项
def _create_egg_action_choices():
    """创建蛋action选项，使用英文作为默认名称并添加本地化支持"""
    from src.utils.i18n import get_all_localizations
    
    actions = ["draw", "list", "hatch", "claim"]
    choices = []
    
    for action_value in actions:
        choice = app_commands.Choice(name=action_value.title(), value=action_value)
        choice.name_localizations = get_all_localizations(f"egg.command.choices.{action_value}")
        choices.append(choice)
    
    return choices

# 斜杠命令定义
@app_commands.command(name="egg", description="Egg system - draw, hatch, and view eggs")
@app_commands.describe(action="Select action type")
@app_commands.choices(action=_create_egg_action_choices())
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
    # 检查用户积分和保底进度
    supabase = get_connection()
    locale = get_guild_locale(interaction.guild.id if interaction.guild else None)

    try:
        user_internal_id = get_user_internal_id(interaction)
        guild_id = interaction.guild.id
        discord_user_id = interaction.user.id

        # 使用Redis缓存获取用户积分
        points = await UserCache.get_points(guild_id, discord_user_id)

        # 使用Redis获取保底计数（异步）
        pity_counter = await DrawLimiter.get_egg_pity_count(guild_id, discord_user_id)

        # 获取实际的抽蛋概率
        draw_probabilities = EggCommands.get_draw_probabilities()

    except Exception as e:
        print(f"抽蛋功能错误: {e}")
        locale = get_guild_locale(interaction.guild.id if interaction.guild else None)
        embed = discord.Embed(
            title=t("common.system_error_title", locale=locale),
            description=t("egg.errors.draw_function_unavailable", locale=locale),
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # 构建概率显示文本
    rarity_names = {'SSR': t("egg.rarity_display.SSR", locale=locale), 'SR': t("egg.rarity_display.SR", locale=locale), 'R': t("egg.rarity_display.R", locale=locale), 'C': t("egg.rarity_display.C", locale=locale)}
    probability_text = t("egg.probability_display", locale=locale)
    for rarity, probability in draw_probabilities:
        probability_text += f"{rarity_names[rarity]}：{float(probability)}%\n"

    # 保底进度显示
    remaining_draws = 50 - pity_counter
    pity_text = f"\n**🎯 {t('egg.pity.progress_title', locale=locale)}：** {pity_counter}/50"
    if remaining_draws <= 10:
        pity_text += t("egg.pity.warning_legendary_soon", locale=locale, remaining_draws=remaining_draws)
    else:
        pity_text += t("egg.pity.distance_to_pity", locale=locale, remaining_draws=remaining_draws)

    embed = create_embed(
        t("egg.ui.draw_interface.title", locale=locale),
        t("egg.ui.draw_interface.points_info", locale=locale, points=points, single_cost=EggCommands.SINGLE_DRAW_COST, ten_cost=EggCommands.TEN_DRAW_COST) +
        f"{probability_text}"
        f"{pity_text}",
        discord.Color.gold()
    )

    view = EggDrawView(interaction.user, interaction.guild.id)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def handle_egg_list(interaction: discord.Interaction):
    """处理查看蛋列表功能"""
    await egg_list(interaction)

async def handle_egg_hatch(interaction: discord.Interaction):
    """处理孵化蛋功能"""
    supabase = get_connection()
    locale = get_guild_locale(interaction.guild.id if interaction.guild else None)

    try:
        # 获取用户ID并验证
        user_id = get_user_internal_id(interaction)
        if not user_id:
            return

        # 首先检查是否已经有蛋在孵化中
        result = supabase.table("user_eggs").select("id, rarity, hatch_started_at, hatch_completed_at").eq("user_id", user_id).eq("status", "hatching").execute()

        incubating_egg = result.data[0] if result.data else None

    except Exception as e:
        print(f"孵化蛋功能错误: {e}")
        embed = discord.Embed(
            title=t("common.system_error_title", locale=locale),
            description=t("egg.errors.hatch_function_unavailable", locale=locale),
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if incubating_egg:
        egg_id = incubating_egg["id"]
        rarity = incubating_egg["rarity"]
        start_time = incubating_egg["hatch_started_at"]
        end_time = incubating_egg["hatch_completed_at"]

        rarity_names = {'C': t("egg.rarity_names.C", locale=locale), 'R': t("egg.rarity_names.R", locale=locale), 'SR': t("egg.rarity_names.SR", locale=locale), 'SSR': t("egg.rarity_names.SSR", locale=locale)}
        rarity_emojis = {'C': '🤍', 'R': '💙', 'SR': '💜', 'SSR': '💛'}

        rarity_name = rarity_names[rarity]
        emoji = rarity_emojis[rarity]

        current_time = datetime.datetime.now(datetime.timezone.utc)
        if end_time and current_time >= datetime.datetime.fromisoformat(end_time.replace('Z', '+00:00')):
            status_text = t("egg.inventory.status.completed", locale=locale)
            action_text = t("egg.inventory.status.action_claim", locale=locale)
        else:
            if end_time:
                end_dt = datetime.datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                remaining = end_dt - current_time
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                if hours > 0:
                    time_text = t("egg.inventory.status.time_format_hours", locale=locale, hours=hours, minutes=minutes)
                else:
                    time_text = t("egg.inventory.status.time_format_minutes", locale=locale, minutes=minutes)
                status_text = t("egg.inventory.status.time_remaining", locale=locale, time=time_text)
            else:
                status_text = t("egg.inventory.status.incubating", locale=locale)
            action_text = t("egg.inventory.status.waiting", locale=locale)

        embed = create_embed(
            t("egg.hatch.already_hatching.title", locale=locale),
            t("egg.hatch.already_hatching.description", locale=locale, emoji=emoji, rarity_name=rarity_name, status_text=status_text, action_text=action_text),
            discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    try:
        # 查询用户的待孵化蛋
        result = supabase.table("user_eggs").select("id, rarity, created_at").eq("user_id", user_id).eq("status", "pending").order("rarity", desc=True).order("created_at", desc=True).limit(25).execute()

        eggs = result.data

        if not eggs:
            await interaction.response.send_message(t("egg.hatch.no_eggs_available", locale=locale), ephemeral=True)
            return

    except Exception as e:
        print(f"查询待孵化蛋错误: {e}")
        embed = discord.Embed(
            title=t("common.system_error_title", locale=locale),
            description=t("egg.errors.query_eggs_failed", locale=locale),
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # 创建选择界面
    embed = create_embed(
        t("egg.hatch.select_egg.title", locale=locale),
        t("egg.hatch.select_egg.description", locale=locale, count=len(eggs)),
        discord.Color.orange()
    )

    view = EggHatchView(eggs, interaction.guild.id)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def handle_egg_claim(interaction: discord.Interaction):
    """处理领取宠物功能"""
    supabase = get_connection()
    locale = get_guild_locale(interaction.guild.id if interaction.guild else None)

    try:
        # 获取用户ID并验证
        user_id = get_user_internal_id(interaction)
        if not user_id:
            return

        # 查询已完成孵化的蛋
        current_time = datetime.datetime.now(datetime.timezone.utc)

        result = supabase.table("user_eggs") \
        .select("id, rarity, hatch_completed_at") \
        .eq("user_id", user_id) \
        .eq("status", "hatching") \
        .lte("hatch_completed_at", current_time.isoformat()) \
        .execute()


        ready_eggs = result.data

        if not ready_eggs:
            await interaction.response.send_message(t("egg.claim.no_ready_pets", locale=locale), ephemeral=True)
            return

        # 获取用户的传说蛋保底计数器
        user_data = supabase.table("users").select("legendary_egg_pity_counter").eq("id", user_id).execute()
        legendary_pity_counter = user_data.data[0].get("legendary_egg_pity_counter", 0) if user_data.data else 0

    except Exception as e:
        print(f"查询已完成孵化的蛋错误: {e}")
        embed = discord.Embed(
            title=t("common.system_error_title", locale=locale),
            description=t("egg.errors.query_completed_eggs_failed", locale=locale),
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # 批量领取所有完成的蛋
    claimed_pets = []
    pity_triggered = False  # 标记是否触发了保底
    has_legendary_egg = False  # 标记是否领取了传说蛋

    try:
        # 获取宠物名称数据
        pet_names = EggCommands.get_pet_names(locale)

        for egg in ready_eggs:
            egg_id = egg["id"]
            rarity = egg["rarity"]
            end_time = egg["hatch_completed_at"]

            # 检查是否真的已经完成孵化
            if end_time:
                end_dt = datetime.datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                if current_time < end_dt:
                    continue  # 跳过未完成的蛋

            # 标记是否领取了传说蛋
            if rarity == 'SSR':
                has_legendary_egg = True

            # 根据蛋的稀有度和孵化概率决定宠物稀有度
            # 传说蛋保底机制:第一次未出SSR则第二次必出SSR
            if rarity == 'SSR' and legendary_pity_counter >= 1:
                # 触发保底,必出SSR
                pet_rarity = 'SSR'
                pity_triggered = True
                legendary_pity_counter = 0  # 重置计数器
            else:
                # 正常概率孵化
                hatch_probabilities = EggCommands.get_hatch_probabilities(rarity)

                # 使用概率决定宠物稀有度
                rand = random.random() * 100
                cumulative_prob = 0
                pet_rarity = rarity  # 默认值，如果没有配置概率就使用蛋的稀有度

                for rarity_option, probability in hatch_probabilities:
                    cumulative_prob += float(probability)
                    if rand < cumulative_prob:
                        pet_rarity = rarity_option
                        break

                # 如果是传说蛋,根据是否出SSR更新计数器
                if rarity == 'SSR':
                    if pet_rarity == 'SSR':
                        legendary_pity_counter = 0  # 出了SSR,重置计数器
                    else:
                        legendary_pity_counter += 1  # 没出SSR,计数器+1

            # 生成宠物
            pet_names_for_rarity = pet_names.get(pet_rarity, [])
            if not pet_names_for_rarity:
                # 如果没有该稀有度的宠物，回退到蛋的稀有度
                pet_rarity = rarity
                pet_names_for_rarity = pet_names.get(pet_rarity, [])

            pet_name = random.choice(pet_names_for_rarity)
            initial_stars = random.randint(*EggCommands.INITIAL_STARS[pet_rarity])

            # 从数据库获取max_stars
            rarity_config_response = supabase.table('pet_rarity_configs').select('max_stars').eq('rarity', pet_rarity).execute()
            max_stars = rarity_config_response.data[0]['max_stars'] if rarity_config_response.data else EggCommands.MAX_STARS[pet_rarity]

            # 从pet_templates表获取pet_template_id（需要通过cn_name和en_name查找）
            pet_template_response = supabase.table('pet_templates').select('id, en_name').eq('rarity', pet_rarity).execute()
            pet_template_id = None
            for template in pet_template_response.data:
                if get_localized_pet_name(template, locale) == pet_name:
                    pet_template_id = template['id']
                    break

            if not pet_template_id:
                # 如果找不到对应的模板，跳过这个宠物
                continue

            # 生成随机偏好食物和厌恶事物
            from src.utils.feeding_system import FlavorType
            flavors = [flavor.value for flavor in FlavorType]

            # 随机选择偏好食物
            favorite_flavor = random.choice(flavors)

            # 从剩余口味中随机选择厌恶事物
            remaining_flavors = [f for f in flavors if f != favorite_flavor]
            dislike_flavor = random.choice(remaining_flavors)

            # 添加到宠物库存
            supabase.table("user_pets").insert({
                "user_id": user_id,
                "pet_template_id": pet_template_id,
                "stars": initial_stars,
                "favorite_flavor": favorite_flavor,
                "dislike_flavor": dislike_flavor,
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
            }).execute()

            # 更新蛋状态为已领取
            supabase.table("user_eggs").update({"status": "claimed"}).eq("id", egg_id).execute()

            rarity_names = {'C': t("egg.rarity_names.C", locale=locale), 'R': t("egg.rarity_names.R", locale=locale), 'SR': t("egg.rarity_names.SR", locale=locale), 'SSR': t("egg.rarity_names.SSR", locale=locale)}
            rarity_emojis = {'C': '🤍', 'R': '💙', 'SR': '💜', 'SSR': '💛'}

            claimed_pets.append({
                'name': pet_name,
                'rarity': pet_rarity,
                'rarity_name': rarity_names[pet_rarity],
                'emoji': rarity_emojis[pet_rarity],
                'stars': initial_stars,
                'egg_rarity': rarity_names[rarity]  # 记录原始蛋的稀有度
            })

        # 更新数据库中的传说蛋保底计数器
        supabase.table("users").update({"legendary_egg_pity_counter": legendary_pity_counter}).eq("id", user_id).execute()

    except Exception as e:
        print(f"领取宠物错误: {e}")
        embed = discord.Embed(
            title=t("common.system_error_title", locale=locale),
            description=t("egg.errors.claim_pet_failed", locale=locale),
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # 创建结果展示
    result_text = ""
    for pet in claimed_pets:
        stars_text = "⭐" * pet['stars']
        result_text += f"{pet['emoji']} **{pet['name']}** ({pet['rarity_name']}) {stars_text} {t('egg.from_egg', locale=locale, rarity=pet['egg_rarity'])}\n"

    # 添加保底触发信息
    pity_info = ""
    if pity_triggered:
        pity_info = t("egg.claim.pity_triggered.legendary", locale=locale)

    # 只在领取了传说蛋时才显示保底进度
    pity_status = ""
    if has_legendary_egg:
        pity_status = t("egg.claim.pity_status.legendary", locale=locale, counter=legendary_pity_counter)
        if legendary_pity_counter == 1:
            pity_status += t("egg.claim.pity_status.legendary_next", locale=locale)

    embed = create_embed(
        t("egg.claim.success.title", locale=locale),
        t("egg.claim.success.description", locale=locale, user=interaction.user.mention, result_text=result_text, count=len(claimed_pets)) + pity_info + pity_status,
        discord.Color.gold()
    )

    await interaction.response.send_message(embed=embed)

async def egg_list(interaction: discord.Interaction):
    """查看蛋和孵化状态"""
    locale = get_guild_locale(interaction.guild.id if interaction.guild else None)
    try:
        supabase = get_connection()

        # 获取用户ID并验证
        user_id = get_user_internal_id(interaction)
        if not user_id:
            return

        # 查询用户的蛋
        eggs_response = supabase.table('user_eggs').select('id, rarity, created_at').eq('user_id', user_id).eq('status', 'pending').order('created_at', desc=True).execute()
        eggs = [(row['id'], row['rarity'], row['created_at']) for row in eggs_response.data]

        # 查询孵化中的蛋
        incubating_response = supabase.table('user_eggs').select('id, rarity, hatch_started_at, hatch_completed_at').eq('user_id', user_id).eq('status', 'hatching').order('hatch_completed_at').execute()
        incubating = [(row['id'], row['rarity'], row['hatch_started_at'], row['hatch_completed_at']) for row in incubating_response.data]

        # 查询可领取的蛋
        current_time = datetime.datetime.now(datetime.timezone.utc)
        ready_response = supabase.table('user_eggs').select('*', count='exact').eq('user_id', user_id).eq('status', 'hatching').execute()
        ready_count = len([egg for egg in ready_response.data if egg.get('hatch_completed_at') and datetime.datetime.fromisoformat(egg['hatch_completed_at'].replace('Z', '+00:00')) <= current_time])

    except Exception as e:
        await interaction.response.send_message(t("egg.errors.query_list_error", locale=locale, error=str(e)), ephemeral=True)
        return

    if not eggs and not incubating:
        embed = create_embed(
            t("egg.inventory.title", locale=locale),
            t("egg.inventory.no_eggs", locale=locale),
            discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)
        return

    # 构建显示内容
    description = ""

    # 显示可领取提示
    if ready_count > 0:
        description += t("egg.inventory.ready_pets_notification", locale=locale, count=ready_count)

    if incubating:
        description += t("egg.inventory.sections.hatching", locale=locale)
        for egg_id, rarity, start_time, end_time in incubating:
            rarity_emoji = {'C': '🤍', 'R': '💙', 'SR': '💜', 'SSR': '💛'}[rarity]
            rarity_name = {'C': t("egg.rarity_names.C", locale=locale), 'R': t("egg.rarity_names.R", locale=locale), 'SR': t("egg.rarity_names.SR", locale=locale), 'SSR': t("egg.rarity_names.SSR", locale=locale)}[rarity]
            now = datetime.datetime.now(datetime.timezone.utc)

            # 确保end_time也是UTC时区
            if isinstance(end_time, str):
                if end_time.endswith('Z'):
                    end_time = end_time[:-1] + '+00:00'
                end_time = datetime.datetime.fromisoformat(end_time)

            if now >= end_time:
                status = t("egg.inventory.status.ready", locale=locale)
            else:
                remaining = end_time - now
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                if hours > 0:
                    time_str = t("egg.inventory.status.time_format_hours", locale=locale, hours=hours, minutes=minutes)
                    status = f"⏰ {time_str}"
                else:
                    time_str = t("egg.inventory.status.time_format_minutes", locale=locale, minutes=minutes)
                    status = f"⏰ {time_str}"

            description += f"{rarity_emoji} {rarity_name}{t('common.egg_suffix', locale=locale)} - {status}\n"
        description += "\n"

    if eggs:
        description += t("egg.inventory.sections.inventory", locale=locale)
        egg_count = {}
        for egg_id, rarity, created_at in eggs:
            if egg_id not in [inc[0] for inc in incubating]:  # 排除孵化中的蛋
                if rarity not in egg_count:
                    egg_count[rarity] = []
                egg_count[rarity].append(egg_id)

        for rarity in ['SSR', 'SR', 'R', 'C']:
            if rarity in egg_count:
                rarity_emoji = {'C': '🤍', 'R': '💙', 'SR': '💜', 'SSR': '💛'}[rarity]
                rarity_name = {'C': t("egg.rarity_names.C", locale=locale), 'R': t("egg.rarity_names.R", locale=locale), 'SR': t("egg.rarity_names.SR", locale=locale), 'SSR': t("egg.rarity_names.SSR", locale=locale)}[rarity]
                description += f"{rarity_emoji} {rarity_name}{t('common.egg_suffix', locale=locale)} x{len(egg_count[rarity])}\n"

    embed = create_embed(
        t("egg.inventory.title", locale=locale),
        description,
        discord.Color.blue()
    )

    await interaction.response.send_message(embed=embed)

# 抽蛋视图类
class EggDrawView(discord.ui.View):
    def __init__(self, user, guild_id):
        super().__init__(timeout=300)
        self.user = user
        self.guild_id = guild_id
        self.locale = get_guild_locale(guild_id)
        self._update_button_labels()
    
    def _update_button_labels(self):
        """初始化按钮标签"""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.custom_id == "single_draw_btn":
                    item.label = t("egg.ui.buttons.single_draw", locale=self.locale)
                elif item.custom_id == "ten_draw_btn":
                    item.label = t("egg.ui.buttons.ten_draw", locale=self.locale)

    @discord.ui.button(label="🎲", style=discord.ButtonStyle.primary, custom_id="single_draw_btn")
    async def single_draw(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message(t("egg.errors.not_your_interface", locale=self.locale), ephemeral=True)
            return

        await self.perform_draw(interaction, 1, EggCommands.SINGLE_DRAW_COST)

    @discord.ui.button(label="🎰", style=discord.ButtonStyle.success, custom_id="ten_draw_btn")
    async def ten_draw(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message(t("egg.errors.not_your_interface", locale=self.locale), ephemeral=True)
            return

        await self.perform_draw(interaction, 10, EggCommands.TEN_DRAW_COST)

    async def perform_draw(self, interaction, count, cost):
        """执行抽蛋"""
        try:
            supabase = get_connection()
            guild_id = interaction.guild.id
            discord_user_id = interaction.user.id
            locale = get_guild_locale(guild_id)

            # 获取用户ID
            user_id = await UserCache.get_user_id(guild_id, discord_user_id)
            if not user_id:
                await interaction.response.send_message(t("egg.errors.user_not_found", locale=locale), ephemeral=True)
                return

            # 使用Redis获取积分
            points = await UserCache.get_points(guild_id, discord_user_id)

            if points < cost:
                await interaction.response.send_message(
                    t("egg.errors.insufficient_points", locale=locale, cost=cost, points=points),
                    ephemeral=True
                )
                return

            # 使用Redis获取保底计数（异步）
            current_pity = await DrawLimiter.get_egg_pity_count(guild_id, discord_user_id)

            # 先发送初始响应，避免交互超时
            await interaction.response.send_message(t("egg.drawing.in_progress", locale=locale), ephemeral=True)

            # 扣除积分 (使用UserCache更新缓存)
            await UserCache.update_points(guild_id, discord_user_id, user_id, -cost)

            # 带保底机制的抽蛋
            results, new_pity = self.draw_eggs_with_pity(count, current_pity)

            # 更新数据库中的保底计数
            supabase.table('users').update({'egg_pity_counter': new_pity}).eq('id', user_id).execute()

            # 更新Redis中的保底计数（异步）
            if new_pity == 0:
                # 触发保底，重置计数
                await DrawLimiter.reset_egg_pity(guild_id, discord_user_id)
            else:
                # 直接设置新的保底计数
                from src.db.redis_client import redis_client
                key = f'egg:pity:{guild_id}:{discord_user_id}'
                await redis_client.set(key, new_pity)

            # 添加蛋到玩家库存
            eggs_to_insert = []
            for rarity in results:
                # 直接使用稀有度作为蛋代码，与egg_types表匹配
                eggs_to_insert.append({
                    'user_id': user_id,
                    'rarity': rarity,
                    'status': 'pending',
                    'created_at': datetime.datetime.now().isoformat(timespec='seconds')
                })

            if eggs_to_insert:
                supabase.table('user_eggs').insert(eggs_to_insert).execute()

        except Exception as e:
            await interaction.edit_original_response(content=t("egg.errors.draw_error", locale=locale, error=str(e)))
            return

        # 显示结果
        result_text = ""
        rarity_count = {}
        for rarity in results:
            rarity_count[rarity] = rarity_count.get(rarity, 0) + 1

        for rarity in ['SSR', 'SR', 'R', 'C']:
            if rarity in rarity_count:
                emoji = {'C': '🤍', 'R': '💙', 'SR': '💜', 'SSR': '💛'}[rarity]
                name = {'C': t("egg.rarity_names.C", locale=locale), 'R': t("egg.rarity_names.R", locale=locale), 'SR': t("egg.rarity_names.SR", locale=locale), 'SSR': t("egg.rarity_names.SSR", locale=locale)}[rarity]
                result_text += f"{emoji} {name}{t('common.egg_suffix', locale=locale)} x{rarity_count[rarity]}\n"

        # 检查是否触发了保底
        pity_triggered = current_pity + count > 49 and 'SSR' in rarity_count
        pity_info = ""
        if pity_triggered and current_pity >= 49:
            pity_info = t("egg.drawing.pity_triggered_legendary", locale=locale)

        # 显示新的保底进度
        remaining = 50 - new_pity
        pity_progress = t("egg.drawing.pity_progress", locale=locale, current=new_pity, remaining=remaining)

        embed = create_embed(
            t("egg.drawing.result.title", locale=locale, count=count),
            f"**{interaction.user.mention} {t('egg.drawing.result.obtained', locale=locale)}：**\n{result_text}\n"
            f"**{t('egg.drawing.result.cost', locale=locale)}：** {cost} {t('common.points', locale=locale)}"
            f"{pity_info}"
            f"{pity_progress}",
            discord.Color.green()
        )

        # 先编辑原始私有消息
        await interaction.edit_original_response(content=t("egg.drawing.result.completed", locale=locale), embed=None, view=None)
        # 然后发送公开的结果消息
        await interaction.followup.send(embed=embed)

    def draw_eggs_with_pity(self, count, current_pity):
        """
        带保底机制的抽蛋系统

        Args:
            count: 抽取次数
            current_pity: 当前保底计数

        Returns:
            tuple: (results, new_pity) - 抽取结果列表和新的保底计数
        """
        # 获取抽蛋概率配置
        draw_probabilities = EggCommands.get_draw_probabilities()

        results = []
        pity = current_pity

        for i in range(count):
            # 检查是否达到保底（50抽）
            if pity >= 49:  # 因为是0-49，所以49就是第50抽
                # 保底触发，必出SSR
                results.append('SSR')
                pity = 0  # 重置保底计数
            else:
                # 正常概率抽取
                rand = random.random() * 100
                cumulative_prob = 0
                drawn_rarity = 'C'  # 默认值

                # 按概率从高到低排序，累积概率判断
                for rarity, probability in draw_probabilities:
                    cumulative_prob += float(probability)
                    if rand < cumulative_prob:
                        drawn_rarity = rarity
                        break

                results.append(drawn_rarity)

                # 如果抽到SSR，重置保底计数；否则增加计数
                if drawn_rarity == 'SSR':
                    pity = 0
                else:
                    pity += 1

        return results, pity


class EggHatchView(discord.ui.View):
    def __init__(self, eggs, guild_id=None):
        super().__init__(timeout=300)
        self.eggs = eggs
        self.locale = get_guild_locale(guild_id)

        # 创建选择菜单
        options = []
        for egg in eggs[:25]:  # Discord限制最多25个选项
            egg_id = egg['id']
            rarity = egg['rarity']
            created_at = egg['created_at']
            rarity_names = {'C': t("egg.rarity_names.C", locale=self.locale), 'R': t("egg.rarity_names.R", locale=self.locale), 'SR': t("egg.rarity_names.SR", locale=self.locale), 'SSR': t("egg.rarity_names.SSR", locale=self.locale)}
            rarity_emojis = {'C': '🤍', 'R': '💙', 'SR': '💜', 'SSR': '💛'}

            rarity_name = rarity_names.get(rarity, t("common.unknown", locale=self.locale))
            emoji = rarity_emojis.get(rarity, '❓')

            # 格式化创建时间
            if isinstance(created_at, str):
                created_at_dt = datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            else:
                created_at_dt = created_at
            time_str = created_at_dt.strftime("%m-%d %H:%M")

            options.append(discord.SelectOption(
                label=f"{emoji} {rarity_name} {t('common.egg_suffix', locale=self.locale).strip()}",
                description=t("egg.ui.description.got", locale=self.locale, time=time_str),
                value=str(egg_id),
                emoji=emoji
            ))

        if options:
            select = EggSelect(options, self.eggs, self.locale)
            self.add_item(select)


class EggSelect(discord.ui.Select):
    def __init__(self, options, eggs, locale):
        super().__init__(placeholder=t("egg.ui.placeholders.select_egg", locale=locale), options=options)
        self.eggs = eggs
        self.locale = locale

    async def callback(self, interaction: discord.Interaction):
        selected_egg_id = int(self.values[0])

        # 找到选中的蛋
        selected_egg = None
        for egg in self.eggs:
            if egg['id'] == selected_egg_id:
                selected_egg = egg
                break

        if not selected_egg:
            await interaction.response.send_message(t("egg.errors.egg_not_found", locale=self.locale), ephemeral=True)
            return

        egg_id = selected_egg['id']
        rarity = selected_egg['rarity']

        # 计算孵化时间（根据稀有度）
        hatch_times = {'C': 1, 'R': 2, 'SR': 4, 'SSR': 8}  # 小时
        hatch_hours = hatch_times.get(rarity, 1)

        # 开始孵化
        try:
            supabase = get_connection()

            start_time = datetime.datetime.now(datetime.timezone.utc)
            end_time = start_time + datetime.timedelta(hours=hatch_hours)

            supabase.table('user_eggs').update({
                'status': 'hatching',
                'hatch_started_at': start_time.isoformat(timespec='seconds'),
                'hatch_completed_at': end_time.isoformat(timespec='seconds')
            }).eq('id', egg_id).execute()

        except Exception as e:
            await interaction.response.send_message(t("egg.errors.start_hatch_error", locale=self.locale, error=str(e)), ephemeral=True)
            return

        rarity_names = {'C': t("egg.rarity_names.C", locale=self.locale), 'R': t("egg.rarity_names.R", locale=self.locale), 'SR': t("egg.rarity_names.SR", locale=self.locale), 'SSR': t("egg.rarity_names.SSR", locale=self.locale)}
        rarity_name = rarity_names.get(rarity, t("common.unknown", locale=self.locale))

        embed = create_embed(
            t("egg.hatch.start.title", locale=self.locale),
            t("egg.hatch.start.description", locale=self.locale, user=interaction.user.mention, rarity_name=rarity_name, hours=hatch_hours),
            discord.Color.green()
        )

        # 先编辑原始私有消息
        await interaction.response.edit_message(content=t("egg.hatch.start.confirmation", locale=self.locale), embed=None, view=None)
        # 然后发送公开的孵化消息
        await interaction.followup.send(embed=embed)


def setup(bot):
    """注册斜杠命令"""
    bot.tree.add_command(egg)
