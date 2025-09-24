import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Dict
from datetime import date
from src.utils.ui import create_embed
from src.utils.helpers import get_user_internal_id, get_user_internal_id_with_guild_and_discord_id

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


async def get_today_shop_items() -> List[Dict]:
    """获取今日商店商品列表"""
    from src.db.database import get_supabase_client

    supabase = get_supabase_client()
    today = date.today()

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
            'name': ft['name'],
            'rarity': ft['rarity'],
            'flavor': ft['flavor'],
            'price': ft['price'],
            'xp_bonus': ft['base_xp'],
            'xp_flow': ft.get('xp_flow', 0),
            'description': ft.get('description', '')
        })

    return shop_items

def get_shop_menu_embed(shop_items, user_points: int, food_purchased_today: int = 0):
    """创建商店菜单embed（仅显示，不含购买功能）"""

    from src.utils.feeding_system import FeedingSystem
    max_purchases = FeedingSystem.MAX_DAILY_FOOD_PURCHASES

    embed = create_embed(
        "🏪 杂货铺",
        f"🎯 今日特选食粮 🎯\n\n💰 你的积分： {user_points}\n🛒 今日已购买： {food_purchased_today}/{max_purchases} 份",
        discord.Color.blue()
    )

    if not shop_items:
        embed.description += "\n\n📦 今日暂无商品，请明天再来！\n\n📝 购买说明\n• 食粮用于喂养宠物获得经验\n• 每人每日最多购买10份食粮\n营业时间：全天24小时 | 每日0点刷新商品"
        return embed

    items_text = ""
    for item in shop_items:
        rarity_heart = RARITY_COLORS.get(item['rarity'], '⚪')
        flavor_emoji = FLAVOR_EMOJIS.get(item['flavor'], '❓')
        xp_flow = item.get('xp_flow', 0)
        description = item.get('description', '')

        items_text += (
            f"\n{rarity_heart} {item['name']} {flavor_emoji}\n"
            f"💫 稀有度：{item['rarity']}\n"
            f"🏷️ 价格：{item['price']} 积分\n"
            f"✨ 基础经验：{item['xp_bonus']} (±{xp_flow})\n"
        )

        # 添加描述信息（如果存在）
        if description:
            items_text += f"📖 {description}\n"

    embed.description += f"\n{items_text}\n📝 购买说明\n• 食粮用于喂养宠物获得经验\n• 每人每日最多购买{max_purchases}份食粮\n\n营业时间：全天24小时 | 每日0点刷新商品"

    # 保留购买提示
    embed.set_footer(text="💡 使用 /shop buy <商品名> <数量> 进行购买")

    return embed

async def item_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> List[app_commands.Choice[str]]:
    """为商品名称提供自动补全选项"""
    try:
        # 获取今日商品列表
        today_items = await get_today_shop_items()

        # 过滤匹配当前输入的商品
        choices = []
        for item in today_items:
            item_name = item['name']
            rarity_emoji = RARITY_COLORS.get(item['rarity'], '⚪')
            flavor_emoji = FLAVOR_EMOJIS.get(item['flavor'], '❓')

            # 如果当前输入为空或商品名包含当前输入，则添加到选项中
            if not current or current.lower() in item_name.lower():
                choice_name = f"{rarity_emoji} {item_name} {flavor_emoji} - {item['price']}积分"
                choices.append(app_commands.Choice(name=choice_name, value=item_name))

        # 最多返回25个选项（Discord限制）
        return choices[:25]
    except Exception:
        # 如果出错，返回空列表
        return []

@app_commands.command(name="shop", description="🏪 杂货铺")
@app_commands.guild_only()
@app_commands.describe(
    action="操作类型",
    item="要购买的食粮名称（仅购买时需要）",
    quantity="购买数量（默认为1）"
)
@app_commands.choices(action=[
    app_commands.Choice(name="查看商品", value="menu"),
    app_commands.Choice(name="购买", value="buy")
])
@app_commands.autocomplete(item=item_autocomplete)
async def shop(interaction: discord.Interaction, action: str, item: str = None, quantity: int = 1):
    """杂货铺主命令"""
    # 先defer响应避免超时
    await interaction.response.defer()

    # 获取用户内部ID
    user_internal_id = get_user_internal_id_with_guild_and_discord_id(
        guild_id=interaction.guild.id,
        discord_user_id=interaction.user.id
    )
    if not user_internal_id:
        embed = create_embed("❌ 错误", "用户不存在，请先使用抽卡功能注册！", discord.Color.red())
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    if action == "menu":
        # 获取今日商品（按服务器）
        today_items = await get_today_shop_items()

        # 获取用户积分和购买限制信息
        from src.db.database import get_supabase_client
        from datetime import date
        supabase = get_supabase_client()
        user_points = 0
        food_purchased_today = 0
        today = date.today()

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
        embed = get_shop_menu_embed(today_items, user_points, food_purchased_today)
        await interaction.followup.send(embed=embed)

    elif action == "buy":
        if not item:
            embed = create_embed("❌ 错误", "购买时必须指定商品名称！", discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # 验证数量
        if quantity <= 0:
            embed = create_embed("❌ 错误", "购买数量必须大于0！", discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if quantity > 99:
            embed = create_embed("❌ 错误", "单次购买数量不能超过99个！", discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # 获取今日商品
        today_items = await get_today_shop_items()

        # 查找指定商品
        target_item = None
        for shop_item in today_items:
            if shop_item['name'].lower() == item.lower():
                target_item = shop_item
                break

        if not target_item:
            embed = create_embed(
                "❌ 商品不存在",
                f"今日杂货铺没有名为 **{item}** 的商品！\n请使用 `/shop menu` 查看可购买的商品。",
                discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return


        # 直接执行购买逻辑
        from src.utils.feeding_system import FeedingSystem

        success, purchase_info = await FeedingSystem.purchase_food(
            user_internal_id,
            target_item['food_template_id'],
            quantity
        )

        if success:
            embed = create_embed(
                "✅ 购买成功",
                f"成功购买 {purchase_info[0]} 个 {RARITY_COLORS.get(target_item['rarity'])} **{target_item['name']}** {FLAVOR_EMOJIS.get(target_item['flavor'])}！\n花费 {purchase_info[1]} 积分，剩余 {purchase_info[2]} 积分。\n今日已购买 {purchase_info[3]}/{FeedingSystem.MAX_DAILY_FOOD_PURCHASES} 份食粮。",
                discord.Color.green()
            )
        else:
            embed = create_embed(
                "❌ 购买失败",
                purchase_info,
                discord.Color.red()
            )

        await interaction.followup.send(embed=embed)

    else:
        embed = create_embed("❌ 错误", "无效的操作类型！", discord.Color.red())
        await interaction.followup.send(embed=embed, ephemeral=True)

@app_commands.command(name="inventory", description="查看你的食粮库存")
@app_commands.guild_only()
@app_commands.describe(item_type="查看的物品类型")
@app_commands.choices(item_type=[
    app_commands.Choice(name="food", value="food")
])
async def inventory(interaction: discord.Interaction, item_type: str = "food"):
    """查看库存命令"""
    # 先defer响应避免超时
    await interaction.response.defer()

    if item_type != "food":
        await interaction.followup.send("❌ 目前只支持查看食粮库存！", ephemeral=True)
        return

    # 获取用户内部ID
    user_internal_id = get_user_internal_id_with_guild_and_discord_id(
        guild_id=interaction.guild.id,
        discord_user_id=interaction.user.id
    )
    if not user_internal_id:
        embed = create_embed("❌ 错误", "用户不存在，请先使用抽卡功能注册！", discord.Color.red())
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
            "🎒 我的食粮库存",
            f"{interaction.user.mention} 你的食粮库存是空的！\n\n去杂货铺买点食粮来喂养宠物吧！",
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
                'name': food_template['name'],
                'rarity': food_template['rarity'],
                'flavor': food_template['flavor'],
                'quantity': item['quantity'],
                'xp_bonus': food_template['base_xp'],
                'description': food_template.get('description', '')
            })

    # 按稀有度排序
    rarity_order = {'SSR': 0, 'SR': 1, 'R': 2, 'C': 3}
    inventory_data.sort(key=lambda x: rarity_order.get(x['rarity'], 4))

    # 创建库存展示
    description = f"{interaction.user.mention} 的食粮库存："

    for item in inventory_data:
        rarity_emoji = RARITY_COLORS.get(item['rarity'], '⚪')
        flavor_emoji = FLAVOR_EMOJIS.get(item['flavor'], '❓')
        item_description = item.get('description', '')

        description += f"\n{rarity_emoji} **{item['name']}** {flavor_emoji} × {item['quantity']}"
        description += f"\n   ✨ 经验: +{item['xp_bonus']}"

        # 添加描述信息（如果存在）
        if item_description:
            description += f"\n   📖 {item_description}"

        description += "\n"

    embed = create_embed(
        "🎒 我的食粮库存",
        description,
        discord.Color.blue()
    )

    total_items = sum([item['quantity'] for item in inventory_data])
    embed.set_footer(text=f"总计 {len(inventory_data)} 种食粮，{total_items} 个")

    await interaction.followup.send(embed=embed)

def setup(bot):
    """注册斜杠命令"""
    bot.tree.add_command(shop)
    bot.tree.add_command(inventory)