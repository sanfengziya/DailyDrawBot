import discord
from discord.ext import commands
from discord import app_commands
from src.utils.ui import create_embed
from src.utils.helpers import get_user_internal_id
from src.utils.i18n import get_guild_locale, t
from src.utils.cache import UserCache

class ForgeCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 锻造配方配置
    FORGE_RECIPES = {
        'C_TO_R': {'ratio': 10, 'points': 50},
        'R_TO_SR': {'ratio': 5, 'points': 80},
        'SR_TO_SSR': {'ratio': 3, 'points': 100}
    }

    # 稀有度映射 - 使用国际化
    @staticmethod
    def get_rarity_name(rarity, locale='zh-CN'):
        """获取稀有度名称"""
        return t("forge.rarity_mapping." + rarity, locale=locale)

    # 稀有度颜色
    RARITY_COLORS = {
        'C': '🤍',
        'R': '💙',
        'SR': '💜',
        'SSR': '💛'
    }

    def get_user_fragments(self, user_id):
        """获取用户碎片库存"""
        try:
            from src.db.database import get_supabase_client
            supabase = get_supabase_client()

            response = supabase.table('user_pet_fragments').select('rarity, amount').eq('user_id', user_id).gt('amount', 0).execute()

            fragments = {}
            for fragment in response.data:
                fragments[fragment['rarity']] = fragment['amount']

            return fragments

        except Exception as e:
            print(f"{t('forge.errors.get_user_fragments_failed', locale='zh-CN', error=e)}")
            return {}

    def calculate_max_crafts(self, from_rarity, to_rarity, fragments, user_points, locale='zh-CN'):
        """计算最大可合成数量"""
        recipe_key = f"{from_rarity}_TO_{to_rarity}"
        if recipe_key not in self.FORGE_RECIPES:
            return 0, t("forge.errors.invalid_recipe", locale=locale)

        recipe = self.FORGE_RECIPES[recipe_key]
        required_fragments = recipe['ratio']
        required_points = recipe['points']

        # 检查碎片数量
        available_fragments = fragments.get(from_rarity, 0)
        if available_fragments < required_fragments:
            return 0, t("forge.errors.insufficient_fragments", locale=locale, required=required_fragments, rarity=self.get_rarity_name(from_rarity, locale))

        # 基于碎片数量计算最大合成次数
        max_by_fragments = available_fragments // required_fragments

        # 基于积分计算最大合成次数
        max_by_points = user_points // required_points if required_points > 0 else max_by_fragments

        # 取较小值
        max_crafts = min(max_by_fragments, max_by_points)

        if max_crafts == 0:
            if max_by_fragments == 0:
                return 0, t("forge.errors.insufficient_fragments", locale=locale, required=required_fragments, rarity=self.get_rarity_name(from_rarity, locale))
            else:
                return 0, t("forge.errors.insufficient_points", locale=locale, required=required_points)

        return max_crafts, None

    def execute_forge(self, user_id, from_rarity, to_rarity, quantity, locale='zh-CN'):
        """执行合成操作"""
        try:
            from src.db.database import get_supabase_client
            supabase = get_supabase_client()

            recipe_key = f"{from_rarity}_TO_{to_rarity}"
            recipe = self.FORGE_RECIPES[recipe_key]

            total_fragments_needed = recipe['ratio'] * quantity
            total_points_needed = recipe['points'] * quantity

            # 获取当前用户数据
            user_response = supabase.table('users').select('points').eq('id', user_id).execute()
            if not user_response.data:
                return False, t("forge.errors.user_data_not_found", locale=locale)

            current_points = user_response.data[0]['points']

            # 获取当前碎片数量
            fragments_response = supabase.table('user_pet_fragments').select('amount').eq('user_id', user_id).eq('rarity', from_rarity).execute()
            if not fragments_response.data:
                return False, t("forge.errors.no_fragments_of_type", locale=locale, rarity=self.get_rarity_name(from_rarity, locale))

            current_fragments = fragments_response.data[0]['amount']

            # 验证资源是否足够
            if current_fragments < total_fragments_needed:
                return False, t("forge.errors.insufficient_fragments_detail", locale=locale, required=total_fragments_needed, current=current_fragments)

            if current_points < total_points_needed:
                return False, t("forge.errors.insufficient_points_detail", locale=locale, required=total_points_needed, current=current_points)

            # 扣除源碎片
            new_source_amount = current_fragments - total_fragments_needed
            if new_source_amount > 0:
                supabase.table('user_pet_fragments').update({'amount': new_source_amount}).eq('user_id', user_id).eq('rarity', from_rarity).execute()
            else:
                supabase.table('user_pet_fragments').delete().eq('user_id', user_id).eq('rarity', from_rarity).execute()

            # 扣除积分
            supabase.table('users').update({'points': current_points - total_points_needed}).eq('id', user_id).execute()

            # 添加目标碎片
            target_response = supabase.table('user_pet_fragments').select('amount').eq('user_id', user_id).eq('rarity', to_rarity).execute()

            if target_response.data:
                # 更新现有记录
                current_target = target_response.data[0]['amount']
                new_target_amount = current_target + quantity
                supabase.table('user_pet_fragments').update({'amount': new_target_amount}).eq('user_id', user_id).eq('rarity', to_rarity).execute()
            else:
                # 插入新记录
                supabase.table('user_pet_fragments').insert({
                    'user_id': user_id,
                    'rarity': to_rarity,
                    'amount': quantity
                }).execute()

            return True, t("forge.success.message", locale=locale, quantity=quantity, rarity=self.get_rarity_name(to_rarity, locale))

        except Exception as e:
            print(f"{t('forge.errors.execute_failed', locale=locale, error=e)}")
            return False, t("forge.errors.synthesis_failed", locale=locale, error=str(e))

# 创建锻造选项（现在使用autocomplete，不再需要固定的choices函数）

async def forge_action_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """为forge命令的action参数提供基于服务器语言的自动补全"""
    from src.utils.i18n import t, get_guild_locale

    # 获取服务器语言设置
    server_locale = get_guild_locale(interaction.guild.id)

    actions = [
        ("view", "forge.command.choices.action.view"),
        ("craft", "forge.command.choices.action.craft")
    ]

    choices = []
    for action_value, translation_key in actions:
        # 使用服务器语言获取翻译
        localized_name = t(translation_key, locale=server_locale,
                         default=action_value.title())

        # 如果用户有输入，进行过滤
        if current and current.lower() not in localized_name.lower() and current.lower() not in action_value.lower():
            continue

        choices.append(app_commands.Choice(name=localized_name, value=action_value))

    return choices

async def forge_from_rarity_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """为forge命令的from_rarity参数提供基于服务器语言的自动补全"""
    from src.utils.i18n import t, get_guild_locale

    # 获取服务器语言设置
    server_locale = get_guild_locale(interaction.guild.id)

    rarities = [
        ("C", "forge.command.choices.from_rarity.C"),
        ("R", "forge.command.choices.from_rarity.R"),
        ("SR", "forge.command.choices.from_rarity.SR")
    ]

    choices = []
    for rarity_value, translation_key in rarities:
        # 使用服务器语言获取翻译
        localized_name = t(translation_key, locale=server_locale,
                         default=f"Common ({rarity_value})" if rarity_value == "C" else f"Rare ({rarity_value})" if rarity_value == "R" else f"Epic ({rarity_value})")

        # 如果用户有输入，进行过滤
        if current and current.lower() not in localized_name.lower() and current.lower() not in rarity_value.lower():
            continue

        choices.append(app_commands.Choice(name=localized_name, value=rarity_value))

    return choices

async def forge_to_rarity_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """为forge命令的to_rarity参数提供基于服务器语言的自动补全"""
    from src.utils.i18n import t, get_guild_locale

    # 获取服务器语言设置
    server_locale = get_guild_locale(interaction.guild.id)

    rarities = [
        ("R", "forge.command.choices.to_rarity.R"),
        ("SR", "forge.command.choices.to_rarity.SR"),
        ("SSR", "forge.command.choices.to_rarity.SSR")
    ]

    choices = []
    for rarity_value, translation_key in rarities:
        # 使用服务器语言获取翻译
        localized_name = t(translation_key, locale=server_locale,
                         default=f"Rare ({rarity_value})" if rarity_value == "R" else f"Epic ({rarity_value})" if rarity_value == "SR" else f"Legendary ({rarity_value})")

        # 如果用户有输入，进行过滤
        if current and current.lower() not in localized_name.lower() and current.lower() not in rarity_value.lower():
            continue

        choices.append(app_commands.Choice(name=localized_name, value=rarity_value))

    return choices

# 主锻造命令
@app_commands.command(name="forge", description="Fragment forge - convert and combine fragments")
@app_commands.describe(
    action="Select action type",
    from_rarity="Source fragment rarity",
    to_rarity="Target fragment rarity",
    quantity="Number of fragments to convert (default: 1)"
)
@app_commands.autocomplete(action=forge_action_autocomplete, from_rarity=forge_from_rarity_autocomplete, to_rarity=forge_to_rarity_autocomplete)
@app_commands.guild_only()
async def forge(interaction: discord.Interaction, action: str, from_rarity: str = None, to_rarity: str = None, quantity: int = 1):
    """锻造台主命令"""
    if action == "view":
        await handle_forge_view(interaction)
    elif action == "craft":
        await handle_forge_craft(interaction, from_rarity, to_rarity, quantity)
    else:
        locale = get_guild_locale(interaction.guild.id if interaction.guild else None)
        embed = create_embed(t("forge.errors.error_title", locale=locale), t("forge.errors.invalid_action_type", locale=locale), discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def handle_forge_view(interaction: discord.Interaction):
    """处理查看锻造台"""
    try:
        locale = get_guild_locale(interaction.guild.id if interaction.guild else None)

        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed(t("forge.errors.error_title", locale=locale), t("forge.errors.user_not_registered", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 获取用户积分
        from src.db.database import get_supabase_client
        supabase = get_supabase_client()
        user_response = supabase.table('users').select('points').eq('id', user_internal_id).execute()

        if not user_response.data:
            embed = create_embed(t("forge.errors.error_title", locale=locale), t("forge.errors.cannot_get_user_data", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        user_points = user_response.data[0]['points']

        # 获取用户碎片库存
        forge_commands = ForgeCommands(None)
        fragments = forge_commands.get_user_fragments(user_internal_id)

        # 构建显示内容
        description = t("forge.view.user_forge.title", locale=locale, user=interaction.user.mention)

        # 显示碎片库存
        if fragments:
            description += t("forge.view.fragments.title", locale=locale)
            rarity_order = ['SSR', 'SR', 'R', 'C']
            for rarity in rarity_order:
                if rarity in fragments:
                    color = ForgeCommands.RARITY_COLORS[rarity]
                    name = forge_commands.get_rarity_name(rarity, locale)
                    amount = fragments[rarity]
                    description += t("forge.view.fragments.display_item", locale=locale, color=color, name=name, amount=amount)
        else:
            description += t("forge.view.fragments.no_fragments", locale=locale)

        description += t("forge.view.current_points", locale=locale, points=user_points)

        # 显示合成规则
        description += t("forge.view.crafting_rules.title", locale=locale)
        description += t("forge.view.crafting_rules.c_to_r", locale=locale)
        description += t("forge.view.crafting_rules.r_to_sr", locale=locale)
        description += t("forge.view.crafting_rules.sr_to_ssr", locale=locale)

        # 显示使用说明
        description += t("forge.view.usage.title", locale=locale)
        description += t("forge.view.usage.example_command", locale=locale)
        description += t("forge.view.usage.example_description", locale=locale)

        # 显示可用操作
        if fragments:
            available_crafts = []
            if fragments.get('C', 0) >= 10:
                available_crafts.append("C → R")
            if fragments.get('R', 0) >= 8:
                available_crafts.append("R → SR")
            if fragments.get('SR', 0) >= 5:
                available_crafts.append("SR → SSR")

            if available_crafts:
                description += t("forge.view.available_crafts.title", locale=locale)
                description += " | ".join(available_crafts)
            else:
                description += t("forge.view.no_available_crafts", locale=locale)
        else:
            description += t("forge.view.no_fragments_tip", locale=locale)

        embed = create_embed(t("forge.view.title", locale=locale), description, discord.Color.gold())
        await interaction.response.send_message(embed=embed)

    except Exception as e:
        locale = get_guild_locale(interaction.guild.id if interaction.guild else None)
        print(f"查看锻造台错误: {e}")
        embed = create_embed(t("forge.errors.error_title", locale=locale), t("forge.errors.forge_unavailable", locale=locale), discord.Color.red())
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)

async def handle_forge_craft(interaction: discord.Interaction, from_rarity: str, to_rarity: str, quantity: int):
    """处理合成碎片"""
    try:
        locale = get_guild_locale(interaction.guild.id if interaction.guild else None)

        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed(t("forge.errors.error_title", locale=locale), t("forge.errors.user_not_found_craft", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 验证参数
        if not from_rarity or not to_rarity:
            embed = create_embed(t("forge.errors.error_title", locale=locale), t("forge.errors.missing_rarity_params", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if quantity < 1:
            embed = create_embed(t("forge.errors.error_title", locale=locale), t("forge.errors.invalid_quantity", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 验证合成路径
        valid_paths = [('C', 'R'), ('R', 'SR'), ('SR', 'SSR')]
        if (from_rarity, to_rarity) not in valid_paths:
            embed = create_embed(t("forge.errors.error_title", locale=locale), t("forge.errors.invalid_crafting_path", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 获取用户数据
        from src.db.database import get_supabase_client
        supabase = get_supabase_client()
        user_response = supabase.table('users').select('points').eq('id', user_internal_id).execute()

        if not user_response.data:
            embed = create_embed(t("forge.errors.error_title", locale=locale), t("forge.errors.cannot_get_data_craft", locale=locale), discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        user_points = user_response.data[0]['points']

        # 获取用户碎片库存
        forge_commands = ForgeCommands(None)
        fragments = forge_commands.get_user_fragments(user_internal_id)

        # 计算最大可合成数量
        max_crafts, error_msg = forge_commands.calculate_max_crafts(from_rarity, to_rarity, fragments, user_points, locale)

        if max_crafts == 0:
            embed = create_embed(t("forge.errors.cannot_craft.title", locale=locale), error_msg, discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 检查请求数量是否可行
        if quantity > max_crafts:
            embed = create_embed(
                t("forge.errors.quantity_exceeded.title", locale=locale),
                t("forge.errors.quantity_exceeded.description", locale=locale, max=max_crafts, requested=quantity),
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 执行合成
        success, message = forge_commands.execute_forge(user_internal_id, from_rarity, to_rarity, quantity, locale)

        # 清除积分缓存，确保check命令显示最新数据
        if success:
            guild_id = interaction.guild.id
            discord_user_id = interaction.user.id
            await UserCache.invalidate_points_cache(guild_id, discord_user_id)

        if success:
            # 获取合成信息用于显示
            recipe_key = f"{from_rarity}_TO_{to_rarity}"
            recipe = ForgeCommands.FORGE_RECIPES[recipe_key]

            from_name = forge_commands.get_rarity_name(from_rarity, locale)
            to_name = forge_commands.get_rarity_name(to_rarity, locale)
            from_color = ForgeCommands.RARITY_COLORS[from_rarity]
            to_color = ForgeCommands.RARITY_COLORS[to_rarity]

            total_fragments_consumed = recipe['ratio'] * quantity
            total_points_consumed = recipe['points'] * quantity

            description = t("forge.craft.success.title", locale=locale, user=interaction.user.mention)
            description += t("forge.craft.success.result.title", locale=locale)
            description += t("forge.craft.success.result.description", locale=locale, from_color=from_color, from_name=from_name, to_color=to_color, to_name=to_name)
            description += t("forge.craft.success.result.consumed", locale=locale)
            description += t("forge.craft.success.result.fragments_consumed", locale=locale, color=from_color, name=from_name, amount=total_fragments_consumed)
            description += t("forge.craft.success.result.points_consumed", locale=locale, points=total_points_consumed)
            description += t("forge.craft.success.result.gained", locale=locale)
            description += t("forge.craft.success.result.fragments_gained", locale=locale, color=to_color, name=to_name, quantity=quantity)

            embed = create_embed(t("forge.craft.success.embed_title", locale=locale), description, discord.Color.green())
        else:
            embed = create_embed(t("forge.craft.failure.title", locale=locale), message, discord.Color.red())

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        locale = get_guild_locale(interaction.guild.id if interaction.guild else None)
        print(f"合成碎片错误: {e}")
        embed = create_embed(t("forge.errors.error_title", locale=locale), t("forge.errors.crafting_failed", locale=locale, error=str(e)), discord.Color.red())
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)


def setup(bot):
    """注册斜杠命令"""
    bot.tree.add_command(forge)