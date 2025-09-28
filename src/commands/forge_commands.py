import discord
from discord.ext import commands
from discord import app_commands
from src.utils.ui import create_embed
from src.utils.helpers import get_user_internal_id

class ForgeCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 锻造配方配置
    FORGE_RECIPES = {
        'C_TO_R': {'ratio': 10, 'points': 100},
        'R_TO_SR': {'ratio': 8, 'points': 200},
        'SR_TO_SSR': {'ratio': 5, 'points': 500}
    }

    # 稀有度映射
    RARITY_MAPPING = {
        'C': '普通',
        'R': '稀有',
        'SR': '史诗',
        'SSR': '传说'
    }

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
            print(f"获取用户碎片库存失败: {e}")
            return {}

    def calculate_max_crafts(self, from_rarity, to_rarity, fragments, user_points):
        """计算最大可合成数量"""
        recipe_key = f"{from_rarity}_TO_{to_rarity}"
        if recipe_key not in self.FORGE_RECIPES:
            return 0, "无效的合成配方"

        recipe = self.FORGE_RECIPES[recipe_key]
        required_fragments = recipe['ratio']
        required_points = recipe['points']

        # 检查碎片数量
        available_fragments = fragments.get(from_rarity, 0)
        if available_fragments < required_fragments:
            return 0, f"碎片不足，需要 {required_fragments} 个 {self.RARITY_MAPPING[from_rarity]} 碎片"

        # 基于碎片数量计算最大合成次数
        max_by_fragments = available_fragments // required_fragments

        # 基于积分计算最大合成次数
        max_by_points = user_points // required_points if required_points > 0 else max_by_fragments

        # 取较小值
        max_crafts = min(max_by_fragments, max_by_points)

        if max_crafts == 0:
            if max_by_fragments == 0:
                return 0, f"碎片不足，需要 {required_fragments} 个 {self.RARITY_MAPPING[from_rarity]} 碎片"
            else:
                return 0, f"积分不足，需要 {required_points} 积分"

        return max_crafts, None

    def execute_forge(self, user_id, from_rarity, to_rarity, quantity):
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
                return False, "用户数据不存在"

            current_points = user_response.data[0]['points']

            # 获取当前碎片数量
            fragments_response = supabase.table('user_pet_fragments').select('amount').eq('user_id', user_id).eq('rarity', from_rarity).execute()
            if not fragments_response.data:
                return False, f"没有 {self.RARITY_MAPPING[from_rarity]} 碎片"

            current_fragments = fragments_response.data[0]['amount']

            # 验证资源是否足够
            if current_fragments < total_fragments_needed:
                return False, f"碎片不足，需要 {total_fragments_needed} 个，只有 {current_fragments} 个"

            if current_points < total_points_needed:
                return False, f"积分不足，需要 {total_points_needed} 积分，只有 {current_points} 积分"

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

            return True, f"成功合成 {quantity} 个 {self.RARITY_MAPPING[to_rarity]} 碎片"

        except Exception as e:
            print(f"执行合成操作失败: {e}")
            return False, f"合成失败: {str(e)}"

# 主锻造命令
@app_commands.command(name="forge", description="🔨 锻造台 - 合成宠物碎片")
@app_commands.describe(
    action="选择操作类型",
    from_rarity="源稀有度（要消耗的碎片）",
    to_rarity="目标稀有度（要获得的碎片）",
    quantity="合成次数（默认1次）"
)
@app_commands.choices(action=[
    app_commands.Choice(name="查看锻造台", value="view"),
    app_commands.Choice(name="合成碎片", value="craft")
])
@app_commands.choices(from_rarity=[
    app_commands.Choice(name="🤍 普通(C)", value="C"),
    app_commands.Choice(name="💙 稀有(R)", value="R"),
    app_commands.Choice(name="💜 史诗(SR)", value="SR")
])
@app_commands.choices(to_rarity=[
    app_commands.Choice(name="💙 稀有(R)", value="R"),
    app_commands.Choice(name="💜 史诗(SR)", value="SR"),
    app_commands.Choice(name="💛 传说(SSR)", value="SSR")
])
@app_commands.guild_only()
async def forge(interaction: discord.Interaction, action: str, from_rarity: str = None, to_rarity: str = None, quantity: int = 1):
    """锻造台主命令"""
    if action == "view":
        await handle_forge_view(interaction)
    elif action == "craft":
        await handle_forge_craft(interaction, from_rarity, to_rarity, quantity)
    else:
        embed = create_embed("❌ 错误", "无效的操作类型！", discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def handle_forge_view(interaction: discord.Interaction):
    """处理查看锻造台"""
    try:
        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed("❌ 错误", "用户不存在，请先使用抽卡功能注册！", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 获取用户积分
        from src.db.database import get_supabase_client
        supabase = get_supabase_client()
        user_response = supabase.table('users').select('points').eq('id', user_internal_id).execute()

        if not user_response.data:
            embed = create_embed("❌ 错误", "无法获取用户数据！", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        user_points = user_response.data[0]['points']

        # 获取用户碎片库存
        forge_commands = ForgeCommands(None)
        fragments = forge_commands.get_user_fragments(user_internal_id)

        # 构建显示内容
        description = f"{interaction.user.mention} 的锻造台\n\n"

        # 显示碎片库存
        if fragments:
            description += "**📦 碎片库存：**\n"
            rarity_order = ['SSR', 'SR', 'R', 'C']
            for rarity in rarity_order:
                if rarity in fragments:
                    color = ForgeCommands.RARITY_COLORS[rarity]
                    name = ForgeCommands.RARITY_MAPPING[rarity]
                    amount = fragments[rarity]
                    description += f"{color} {name}碎片：{amount} 个\n"
        else:
            description += "**📦 碎片库存：** 无\n"

        description += f"\n💰 **当前积分：** {user_points}\n\n"

        # 显示合成规则
        description += "**🔨 合成规则：**\n"
        description += "• C碎片 → R碎片：10:1 + 100积分\n"
        description += "• R碎片 → SR碎片：8:1 + 200积分\n"
        description += "• SR碎片 → SSR碎片：5:1 + 500积分\n\n"

        # 显示使用说明
        description += "**📋 使用方法：**\n"
        description += "`/forge action:合成碎片 from_rarity:C to_rarity:R quantity:1`\n"
        description += "例如：将10个C碎片合成1个R碎片\n\n"

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
                description += "**✅ 可进行的合成：**\n"
                description += " | ".join(available_crafts)
            else:
                description += "**❌ 暂无可进行的合成**\n需要更多碎片才能进行合成！"
        else:
            description += "**❌ 没有碎片**\n分解宠物可以获得碎片！"

        embed = create_embed("🔨 锻造台", description, discord.Color.gold())
        await interaction.response.send_message(embed=embed)

    except Exception as e:
        print(f"查看锻造台错误: {e}")
        embed = create_embed("❌ 错误", "锻造台暂时不可用，请稍后再试！", discord.Color.red())
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)

async def handle_forge_craft(interaction: discord.Interaction, from_rarity: str, to_rarity: str, quantity: int):
    """处理合成碎片"""
    try:
        # 获取用户内部ID
        user_internal_id = get_user_internal_id(interaction)
        if not user_internal_id:
            embed = create_embed("❌ 错误", "用户不存在，请先使用抽卡功能注册！", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 验证参数
        if not from_rarity or not to_rarity:
            embed = create_embed("❌ 错误", "请指定源稀有度和目标稀有度！", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if quantity < 1:
            embed = create_embed("❌ 错误", "合成次数必须大于0！", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 验证合成路径
        valid_paths = [('C', 'R'), ('R', 'SR'), ('SR', 'SSR')]
        if (from_rarity, to_rarity) not in valid_paths:
            embed = create_embed("❌ 错误", "无效的合成路径！只能按照 C→R→SR→SSR 的顺序合成。", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 获取用户数据
        from src.db.database import get_supabase_client
        supabase = get_supabase_client()
        user_response = supabase.table('users').select('points').eq('id', user_internal_id).execute()

        if not user_response.data:
            embed = create_embed("❌ 错误", "无法获取用户数据！", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        user_points = user_response.data[0]['points']

        # 获取用户碎片库存
        forge_commands = ForgeCommands(None)
        fragments = forge_commands.get_user_fragments(user_internal_id)

        # 计算最大可合成数量
        max_crafts, error_msg = forge_commands.calculate_max_crafts(from_rarity, to_rarity, fragments, user_points)

        if max_crafts == 0:
            embed = create_embed("❌ 无法合成", error_msg, discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 检查请求数量是否可行
        if quantity > max_crafts:
            embed = create_embed(
                "❌ 数量超限",
                f"最多只能合成 {max_crafts} 次，但你请求了 {quantity} 次！",
                discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 执行合成
        success, message = forge_commands.execute_forge(user_internal_id, from_rarity, to_rarity, quantity)

        if success:
            # 获取合成信息用于显示
            recipe_key = f"{from_rarity}_TO_{to_rarity}"
            recipe = ForgeCommands.FORGE_RECIPES[recipe_key]

            from_name = ForgeCommands.RARITY_MAPPING[from_rarity]
            to_name = ForgeCommands.RARITY_MAPPING[to_rarity]
            from_color = ForgeCommands.RARITY_COLORS[from_rarity]
            to_color = ForgeCommands.RARITY_COLORS[to_rarity]

            total_fragments_consumed = recipe['ratio'] * quantity
            total_points_consumed = recipe['points'] * quantity

            description = f"🎉 {interaction.user.mention} 合成成功！\n\n"
            description += f"**合成结果：**\n"
            description += f"{from_color} {from_name}碎片 → {to_color} {to_name}碎片\n\n"
            description += f"**消耗：**\n"
            description += f"• {from_color} {from_name}碎片：{total_fragments_consumed} 个\n"
            description += f"• 💰 积分：{total_points_consumed} 点\n\n"
            description += f"**获得：**\n"
            description += f"• {to_color} {to_name}碎片：{quantity} 个"

            embed = create_embed("🔨 锻造成功", description, discord.Color.green())
        else:
            embed = create_embed("❌ 合成失败", message, discord.Color.red())

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        print(f"合成碎片错误: {e}")
        embed = create_embed("❌ 错误", f"合成过程中发生错误：{str(e)}", discord.Color.red())
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)


def setup(bot):
    """注册斜杠命令"""
    bot.tree.add_command(forge)