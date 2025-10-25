import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Dict
from datetime import datetime
from zoneinfo import ZoneInfo
from src.utils.ui import create_embed
from src.utils.helpers import get_user_internal_id, get_user_internal_id_with_guild_and_discord_id
from src.utils.i18n import get_default_locale, get_guild_locale, get_all_localizations, t, get_context_locale, get_localized_food_name, get_localized_food_description

# 稀有度颜色映射
RARITY_COLORS = {
    'C': '⚪',
    'R': '🔵',
    'SR': '🟣',
    'SSR': '🟡'
}

# 口味表情映射
FLAVOR_EMOJIS = {
    'SWEET': '🍯',
    'SALTY': '🧂',
    'SOUR': '🍋',
    'SPICY': '🌶️',
    'UMAMI': '🍄'
}

def get_user_internal_id(interaction):
    """从interaction获取用户内部ID"""
    from src.utils.helpers import get_user_internal_id_with_guild_and_discord_id
    import asyncio

    # 因为这是一个同步函数调用异步函数，我们需要获取当前的事件循环
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 如果事件循环正在运行，我们不能直接调用run_until_complete
            # 这种情况下应该使用异步版本
            return None
        else:
            return get_user_internal_id_with_guild_and_discord_id(
                guild_id=interaction.guild.id,
                discord_user_id=interaction.user.id
            )
    except:
        return None

class ShopCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


async def get_today_shop_items(locale: str = None) -> List[Dict]:
    """获取今日商店商品列表"""
    from src.db.database import get_supabase_client

    supabase = get_supabase_client()
    today = datetime.now(ZoneInfo("America/New_York")).date()

    if not locale:
        locale = get_default_locale()

    # 获取今日商品目录
    catalog_response = supabase.table('daily_shop_catalog').select('''
        food_template_id,
        food_templates(*)
    ''').eq('refresh_date', today.isoformat()).execute()

    if not catalog_response.data:
        return []

    # 组装商品列表
    shop_items = []
    for row in catalog_response.data:
        ft = row['food_templates']
        if not ft:
            continue

        shop_items.append({
            'food_template_id': row['food_template_id'],
            'name': get_localized_food_name(ft, locale),
            'rarity': ft['rarity'],
            'flavor': ft['flavor'],
            'price': ft['price'],
            'xp_bonus': ft['base_xp'],
            'xp_flow': ft.get('xp_flow', 0),
            'description': get_localized_food_description(ft, locale)
        })

    return shop_items

def get_shop_menu_embed(shop_items, user_points: int, food_purchased_today: int = 0, locale: str | None = None):
    """创建商店菜单embed（仅显示，不含购买功能）"""

    from src.utils.feeding_system import FeedingSystem
    max_purchases = FeedingSystem.MAX_DAILY_FOOD_PURCHASES

    if locale is None:
        locale = get_default_locale()

    embed = create_embed(
        t("shop_module.items.menu.title", locale=locale),
        t(
            "shop_module.items.menu.header",
            locale=locale,
            points=user_points,
            purchased=food_purchased_today,
            limit=max_purchases
        ),
        discord.Color.blue()
    )

    if not shop_items:
        embed.description += t(
            "shop_module.items.menu.empty_notice",
            locale=locale,
            limit=max_purchases
        )
        return embed

    items_text = ""
    for item in shop_items:
        rarity_heart = RARITY_COLORS.get(item['rarity'], '⚪')
        flavor_emoji = FLAVOR_EMOJIS.get(item['flavor'], '❓')
        xp_flow = item.get('xp_flow', 0)
        description = item.get('description', '')

        items_text += t(
            "shop_module.items.menu.item_block",
            locale=locale,
            rarity_icon=rarity_heart,
            name=item['name'],
            flavor_icon=flavor_emoji,
            rarity=item['rarity'],
            price=item['price'],
            xp=item['xp_bonus'],
            xp_flow=xp_flow
        )

        # 添加描述信息（如果存在）
        if description:
            items_text += t(
                "shop_module.items.menu.item_description",
                locale=locale,
                description=description
            )

    embed.description += f"\n{items_text}" + t(
        "shop_module.items.menu.tail",
        locale=locale,
        limit=max_purchases
    )

    # 保留购买提示
    embed.set_footer(text=t("shop_module.items.menu.footer", locale=locale))

    return embed

async def item_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> List[app_commands.Choice[str]]:
    """为商品名称提供自动补全选项"""
    try:
        locale = get_guild_locale(interaction.guild.id if interaction.guild else None)
        # 获取今日商品列表
        today_items = await get_today_shop_items(locale)

        # 过滤匹配当前输入的商品
        choices = []
        for item in today_items:
            item_name = item['name']
            rarity_emoji = RARITY_COLORS.get(item['rarity'], '⚪')
            flavor_emoji = FLAVOR_EMOJIS.get(item['flavor'], '❓')

            # 如果当前输入为空或商品名包含当前输入，则添加到选项中
            if not current or current.lower() in item_name.lower():
                choice_name = t(
                    "shop_module.items.autocomplete.entry",
                    locale=locale,
                    rarity_icon=rarity_emoji,
                    name=item_name,
                    flavor_icon=flavor_emoji,
                    price=item['price']
                )
                choices.append(app_commands.Choice(name=choice_name, value=item_name))

        # 最多返回25个选项（Discord限制）
        return choices[:25]
    except Exception:
        # 如果出错，返回空列表
        return []

# 使用英文作为默认名称，通过 name_localizations 支持其他语言
choice_menu = app_commands.Choice(
    name="view menu",
    value="menu"
)
choice_menu.name_localizations = get_all_localizations("shop_module.items.command.choice_menu")

choice_buy = app_commands.Choice(
    name="buy",
    value="buy"
)
choice_buy.name_localizations = get_all_localizations("shop_module.items.command.choice_buy")


@app_commands.command(name="shop", description="Shop - view items and make purchases")
@app_commands.guild_only()
@app_commands.describe(
    action="Select action type",
    item="Select item to purchase",
    quantity="Purchase quantity (default: 1)"
)
@app_commands.choices(action=[choice_menu, choice_buy])
@app_commands.autocomplete(item=item_autocomplete)
async def shop(interaction: discord.Interaction, action: str, item: str = None, quantity: int = 1):
    """杂货铺主命令"""
    # 先defer响应避免超时
    await interaction.response.defer()

    locale = get_guild_locale(interaction.guild.id if interaction.guild else None)

    # 获取用户内部ID
    user_internal_id = get_user_internal_id_with_guild_and_discord_id(
        guild_id=interaction.guild.id,
        discord_user_id=interaction.user.id
    )
    if not user_internal_id:
        embed = create_embed(
            t("shop_module.items.errors.title", locale=locale),
            t("shop_module.items.errors.user_missing", locale=locale),
            discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    if action == "menu":
        # 获取今日商品（按服务器）
        today_items = await get_today_shop_items(locale)

        # 获取用户积分和购买限制信息
        from src.db.database import get_supabase_client
        from datetime import date
        supabase = get_supabase_client()
        user_points = 0
        food_purchased_today = 0
        today = datetime.now(ZoneInfo("America/New_York")).date()

        try:
            user_resp = supabase.table('users').select(
                'points, food_purchased_today, last_food_purchase_date'
            ).eq('id', user_internal_id).execute()
            if user_resp.data:
                user_data = user_resp.data[0]
                user_points = user_data.get('points', 0)
                food_purchased_today = user_data.get('food_purchased_today', 0) or 0
                last_food_purchase_date = user_data.get('last_food_purchase_date')

                # 检查是否跨天重置购买数量
                if last_food_purchase_date != today.isoformat():
                    food_purchased_today = 0
        except Exception:
            user_points = 0
            food_purchased_today = 0

        # 创建仅显示商店的embed（不含购买按钮）
        embed = get_shop_menu_embed(today_items, user_points, food_purchased_today, locale)
        await interaction.followup.send(embed=embed)

    elif action == "buy":
        if not item:
            embed = create_embed(
                t("shop_module.items.errors.title", locale=locale),
                t("shop_module.items.errors.require_item", locale=locale),
                discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # 验证数量
        if quantity <= 0:
            embed = create_embed(
                t("shop_module.items.errors.title", locale=locale),
                t("shop_module.items.errors.quantity_positive", locale=locale),
                discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if quantity > 99:
            embed = create_embed(
                t("shop_module.items.errors.title", locale=locale),
                t("shop_module.items.errors.quantity_max", locale=locale),
                discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # 获取今日商品
        today_items = await get_today_shop_items(locale)

        # 查找指定商品
        target_item = None
        for shop_item in today_items:
            if shop_item['name'].lower() == item.lower():
                target_item = shop_item
                break

        if not target_item:
            embed = create_embed(
                t("shop_module.items.not_found.title", locale=locale),
                t("shop_module.items.not_found.description", locale=locale, item=item),
                discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return


        # 直接执行购买逻辑
        from src.utils.feeding_system import FeedingSystem

        success, purchase_info = await FeedingSystem.purchase_food(
            user_internal_id,
            target_item['food_template_id'],
            quantity,
            guild_id=interaction.guild.id,
            discord_user_id=interaction.user.id
        )

        if success:
            embed = create_embed(
                t("shop_module.items.purchase.success_title", locale=locale),
                t(
                    "shop_module.items.purchase.success_description",
                    locale=locale,
                    mention=interaction.user.mention,
                    quantity=purchase_info[0],
                    rarity_icon=RARITY_COLORS.get(target_item['rarity'], '⚪'),
                    name=target_item['name'],
                    flavor_icon=FLAVOR_EMOJIS.get(target_item['flavor'], '❓'),
                    cost=purchase_info[1],
                    balance=purchase_info[2],
                    purchased=purchase_info[3],
                    limit=FeedingSystem.MAX_DAILY_FOOD_PURCHASES
                ),
                discord.Color.green()
            )
        else:
            embed = create_embed(
                t("shop_module.items.purchase.failure_title", locale=locale),
                str(purchase_info),
                discord.Color.red()
            )

        await interaction.followup.send(embed=embed)

    else:
        embed = create_embed(
            t("shop_module.items.command.invalid_action_title", locale=locale),
            t("shop_module.items.command.invalid_action_desc", locale=locale),
            discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

inventory_choice_food = app_commands.Choice(
    name="food",
    value="food"
)
inventory_choice_food.name_localizations = get_all_localizations("shop_module.items.inventory_command.choice_food")


@app_commands.command(name="inventory", description="View your item inventory")
@app_commands.guild_only()
@app_commands.describe(item_type="Item type to view")
@app_commands.choices(item_type=[inventory_choice_food])
async def inventory(interaction: discord.Interaction, item_type: str = "food"):
    """查看库存命令"""
    # 先defer响应避免超时
    await interaction.response.defer()

    locale = get_guild_locale(interaction.guild.id if interaction.guild else None)

    if item_type != "food":
        await interaction.followup.send(
            t("shop_module.items.errors.unsupported_type", locale=locale),
            ephemeral=True
        )
        return

    # 获取用户内部ID
    user_internal_id = get_user_internal_id_with_guild_and_discord_id(
        guild_id=interaction.guild.id,
        discord_user_id=interaction.user.id
    )
    if not user_internal_id:
        embed = create_embed(
            t("shop_module.items.errors.title", locale=locale),
            t("shop_module.items.errors.user_missing", locale=locale),
            discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    from src.db.database import get_supabase_client
    supabase = get_supabase_client()

    # 查询用户食粮库存
    response = supabase.table('user_food_inventory').select('''
        quantity,
        food_templates(*)
    ''').eq('user_id', user_internal_id).gt('quantity', 0).execute()

    if not response.data:
        embed = create_embed(
            t("shop_module.items.inventory.title", locale=locale),
            t(
                "shop_module.items.inventory.empty_description",
                locale=locale,
                mention=interaction.user.mention
            ),
            discord.Color.orange()
        )
        await interaction.followup.send(embed=embed)
        return

    # 整理库存数据
    inventory_data = []
    for item in response.data:
        food_template = item['food_templates']
        if food_template:
            inventory_data.append({
                'name': get_localized_food_name(food_template, locale),
                'rarity': food_template['rarity'],
                'flavor': food_template['flavor'],
                'quantity': item['quantity'],
                'xp_bonus': food_template['base_xp'],
                'description': get_localized_food_description(food_template, locale)
            })

    # 按稀有度排序
    rarity_order = {'SSR': 0, 'SR': 1, 'R': 2, 'C': 3}
    inventory_data.sort(key=lambda x: rarity_order.get(x['rarity'], 4))

    # 创建库存展示
    description = t(
        "shop_module.items.inventory.intro",
        locale=locale,
        mention=interaction.user.mention
    )

    for item in inventory_data:
        rarity_emoji = RARITY_COLORS.get(item['rarity'], '⚪')
        flavor_emoji = FLAVOR_EMOJIS.get(item['flavor'], '❓')
        item_description = item.get('description', '')

        description += t(
            "shop_module.items.inventory.entry_line",
            locale=locale,
            rarity_icon=rarity_emoji,
            name=item['name'],
            flavor_icon=flavor_emoji,
            quantity=item['quantity']
        )
        description += t(
            "shop_module.items.inventory.entry_stats",
            locale=locale,
            xp=item['xp_bonus']
        )

        # 添加描述信息（如果存在）
        if item_description:
            description += t(
                "shop_module.items.inventory.entry_description",
                locale=locale,
                description=item_description
            )

        description += "\n"

    embed = create_embed(
        t("shop_module.items.inventory.title", locale=locale),
        description,
        discord.Color.blue()
    )

    total_items = sum([item['quantity'] for item in inventory_data])
    embed.set_footer(
        text=t(
            "shop_module.items.inventory.footer",
            locale=locale,
            types=len(inventory_data),
            total=total_items
        )
    )

    await interaction.followup.send(embed=embed)

def setup(bot):
    """注册斜杠命令"""
    bot.tree.add_command(shop)
    bot.tree.add_command(inventory)


# Apply localization to command metadata
shop.description_localizations = get_all_localizations("shop_module.items.command.description")
def _set_param_localizations(command, param_name, key):
    localizations = get_all_localizations(key)
    for param in command.parameters:
        if param.name == param_name:
            param.description_localizations = localizations
            break

shop.description_localizations = get_all_localizations("shop_module.items.command.description")
_set_param_localizations(shop, "action", "shop_module.items.command.param_action")
_set_param_localizations(shop, "item", "shop_module.items.command.param_item")
_set_param_localizations(shop, "quantity", "shop_module.items.command.param_quantity")

inventory.description_localizations = get_all_localizations("shop_module.items.inventory_command.description")
_set_param_localizations(inventory, "item_type", "shop_module.items.inventory_command.param_item_type")
