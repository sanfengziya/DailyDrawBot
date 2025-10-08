import discord
import asyncio
from discord import app_commands
from src.db.database import get_connection
from src.utils.ui import RolePageView
from src.utils.cache import UserCache

async def addtag(ctx, price, role):
    """管理员命令：添加身份组到商店"""
    supabase = get_connection()

    try:
        # 使用upsert来实现INSERT ... ON DUPLICATE KEY UPDATE的功能
        # 添加guild_id以实现服务器隔离
        supabase.table("tags").upsert({
            "guild_id": str(ctx.guild.id),
            "role_id": str(role.id),
            "price": price
        }, on_conflict="guild_id,role_id").execute()

        await ctx.send(f"已添加身份组 `{role.name}`，价格为 {price} 分。")
    except Exception as e:
        print(f"添加身份组失败: {e}")
        await ctx.send("添加身份组失败，请稍后重试。")

async def roleshop(ctx):
    """查看身份组商店"""
    supabase = get_connection()

    try:
        # 只显示当前服务器的身份组
        result = supabase.table("tags").select("role_id, price").eq("guild_id", str(ctx.guild.id)).order("price").execute()
        rows = [(row["role_id"], row["price"]) for row in result.data]

        if not rows:
            await ctx.send("当前没有可购买的身份组。")
            return

        view = RolePageView(ctx, rows)
        await view.send_initial()
    except Exception as e:
        print(f"获取身份组列表失败: {e}")
        await ctx.send("获取身份组列表失败，请稍后重试。")

async def buytag(ctx, role_name):
    """购买身份组"""
    guild = ctx.guild
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        await ctx.send("未找到该身份组。")
        return

    supabase = get_connection()

    try:
        # 获取身份组价格(只查询当前服务器的身份组)
        tag_result = supabase.table("tags").select("price").eq("guild_id", str(ctx.guild.id)).eq("role_id", str(role.id)).execute()
        if not tag_result.data:
            await ctx.send("该身份组不可购买。")
            return
        price = tag_result.data[0]["price"]

        # 获取用户内部ID和积分
        user_internal_id = await UserCache.get_user_id(ctx.guild.id, ctx.author.id)
        if not user_internal_id:
            await ctx.send("用户信息获取失败，请稍后重试。")
            return

        current_points = await UserCache.get_points(ctx.guild.id, ctx.author.id)
        if current_points < price:
            await ctx.send("你的分数不足。")
            return

        await ctx.send(f"你确定要购买 `{role.name}` 吗？请在 10 秒内回复 `Y`。")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            reply = await ctx.bot.wait_for("message", check=check, timeout=10.0)
            if reply.content.upper() != "Y":
                await ctx.send("已取消购买。")
                return
        except:
            await ctx.send("超时，已取消购买。")
            return

        # 扣除积分
        await UserCache.update_points(ctx.guild.id, ctx.author.id, user_internal_id, -price)

        await ctx.author.add_roles(role)
        await ctx.send(f"✅ 你已购买并获得 `{role.name}` 身份组。")

    except Exception as e:
        print(f"购买身份组失败: {e}")
        await ctx.send("购买身份组失败，请稍后重试。")

async def removetag(ctx, role: discord.Role):
    """管理员命令：删除身份组商店中的某个身份组"""
    supabase = get_connection()

    try:
        # 删除指定的身份组
        result = supabase.table("tags").delete().eq("guild_id", str(ctx.guild.id)).eq("role_id", str(role.id)).execute()

        if result.data:
            await ctx.send(f"✅ 已从商店中移除身份组 `{role.name}`。")
        else:
            await ctx.send(f"❌ 未找到身份组 `{role.name}`，可能它不在商店中。")
    except Exception as e:
        print(f"删除身份组失败: {e}")
        await ctx.send("删除身份组失败，请稍后重试。")

async def updatetagprice(ctx, role: discord.Role, new_price: int):
    """管理员命令：更新身份组的价格"""
    supabase = get_connection()

    try:
        # 更新身份组价格
        result = supabase.table("tags").update({
            "price": new_price
        }).eq("guild_id", str(ctx.guild.id)).eq("role_id", str(role.id)).execute()

        if result.data:
            await ctx.send(f"✅ 已将身份组 `{role.name}` 的价格更新为 {new_price} 分。")
        else:
            await ctx.send(f"❌ 未找到身份组 `{role.name}`，请先使用 `!addtag` 添加。")
    except Exception as e:
        print(f"更新身份组价格失败: {e}")
        await ctx.send("更新身份组价格失败，请稍后重试。")

async def listtags(ctx):
    """管理员命令：查看当前服务器所有已添加的身份组"""
    supabase = get_connection()

    try:
        result = supabase.table("tags").select("role_id, price").eq("guild_id", str(ctx.guild.id)).order("price").execute()

        if not result.data:
            await ctx.send("❌ 当前服务器还没有添加任何身份组。")
            return

        embed = discord.Embed(
            title="🏷️ 服务器身份组商店列表",
            description="以下是当前服务器已添加的所有身份组：",
            color=discord.Color.blue()
        )

        for tag in result.data:
            role = ctx.guild.get_role(int(tag["role_id"]))
            if role:
                embed.add_field(
                    name=f"{role.name}",
                    value=f"💰 价格: {tag['price']} 分",
                    inline=False
                )
            else:
                embed.add_field(
                    name=f"未知身份组 (ID: {tag['role_id']})",
                    value=f"💰 价格: {tag['price']} 分 ⚠️ 身份组可能已被删除",
                    inline=False
                )

        await ctx.send(embed=embed)
    except Exception as e:
        print(f"获取身份组列表失败: {e}")
        await ctx.send("获取身份组列表失败，请稍后重试。")

# ========== Slash命令部分 ==========

async def tag_shop(interaction: discord.Interaction):
    """显示身份组商店（slash命令版本）"""
    supabase = get_connection()

    try:
        # 只显示当前服务器的身份组
        result = supabase.table("tags").select("role_id, price").eq("guild_id", str(interaction.guild.id)).order("price").execute()
        rows = [(row["role_id"], row["price"]) for row in result.data]

        if not rows:
            await interaction.response.send_message("当前没有可购买的身份组。", ephemeral=True)
            return

        # 创建embed显示
        embed = discord.Embed(
            title="🏷️ 身份组商店",
            description="以下是可购买的身份组：",
            color=discord.Color.gold()
        )

        for role_id, price in rows:
            role = interaction.guild.get_role(int(role_id))
            if role:
                embed.add_field(
                    name=f"{role.name}",
                    value=f"💰 {price} 分",
                    inline=True
                )

        embed.set_footer(text="使用 /tag action:购买 role_name:身份组名称 来购买")
        await interaction.response.send_message(embed=embed)

    except Exception as e:
        print(f"获取身份组列表失败: {e}")
        await interaction.response.send_message("获取身份组列表失败，请稍后重试。", ephemeral=True)

async def tag_buy(interaction: discord.Interaction, role_name: str):
    """购买身份组（slash命令版本）"""
    guild = interaction.guild
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        await interaction.response.send_message("❌ 未找到该身份组。", ephemeral=True)
        return

    supabase = get_connection()

    try:
        # 获取身份组价格(只查询当前服务器的身份组)
        tag_result = supabase.table("tags").select("price").eq("guild_id", str(guild.id)).eq("role_id", str(role.id)).execute()
        if not tag_result.data:
            await interaction.response.send_message("❌ 该身份组不可购买。", ephemeral=True)
            return
        price = tag_result.data[0]["price"]

        # 获取用户内部ID和积分
        user_internal_id = await UserCache.get_user_id(guild.id, interaction.user.id)
        if not user_internal_id:
            await interaction.response.send_message("❌ 用户信息获取失败，请稍后重试。", ephemeral=True)
            return

        current_points = await UserCache.get_points(guild.id, interaction.user.id)
        if current_points < price:
            await interaction.response.send_message(f"❌ 你的积分不足！需要 {price} 分，当前只有 {current_points} 分。", ephemeral=True)
            return

        # 确认购买
        embed = discord.Embed(
            title="🛒 购买确认",
            description=f"你确定要购买 `{role.name}` 吗？\n\n💰 价格: {price} 分\n💳 你的积分: {current_points} 分\n📊 剩余积分: {current_points - price} 分",
            color=discord.Color.gold()
        )

        # 创建确认按钮
        class ConfirmView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=30)
                self.value = None

            @discord.ui.button(label="确认购买", style=discord.ButtonStyle.green)
            async def confirm(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if button_interaction.user.id != interaction.user.id:
                    await button_interaction.response.send_message("❌ 这不是你的购买请求！", ephemeral=True)
                    return
                self.value = True
                self.stop()

            @discord.ui.button(label="取消", style=discord.ButtonStyle.red)
            async def cancel(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if button_interaction.user.id != interaction.user.id:
                    await button_interaction.response.send_message("❌ 这不是你的购买请求！", ephemeral=True)
                    return
                self.value = False
                self.stop()

        view = ConfirmView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        # 等待用户确认
        await view.wait()

        if view.value is None:
            await interaction.edit_original_response(content="⏰ 购买超时已取消。", embed=None, view=None)
            return
        elif view.value is False:
            await interaction.edit_original_response(content="❌ 已取消购买。", embed=None, view=None)
            return

        # 执行购买
        await UserCache.update_points(guild.id, interaction.user.id, user_internal_id, -price)
        await interaction.user.add_roles(role)

        success_embed = discord.Embed(
            title="✅ 购买成功",
            description=f"你已成功购买并获得 `{role.name}` 身份组！",
            color=discord.Color.green()
        )
        await interaction.edit_original_response(content=None, embed=success_embed, view=None)

    except Exception as e:
        print(f"购买身份组失败: {e}")
        await interaction.response.send_message("❌ 购买身份组失败，请稍后重试。", ephemeral=True)

def setup(bot):
    """注册/tag slash命令组"""

    @bot.tree.command(name="tag", description="身份组商店相关操作")
    @app_commands.describe(
        action="选择操作",
        role_name="身份组名称（购买时使用）"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="商店 - 查看可购买的身份组", value="shop"),
        app_commands.Choice(name="购买 - 购买指定身份组", value="buy")
    ])
    async def tag_command(interaction: discord.Interaction, action: app_commands.Choice[str], role_name: str = None):
        """统一的/tag命令入口"""

        if action.value == "shop":
            await tag_shop(interaction)
        elif action.value == "buy":
            if not role_name:
                await interaction.response.send_message("❌ 购买身份组时必须提供身份组名称！", ephemeral=True)
                return
            await tag_buy(interaction, role_name)
