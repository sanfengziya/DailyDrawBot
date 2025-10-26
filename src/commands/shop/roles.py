import discord
import asyncio
from discord import app_commands
from src.db.database import get_connection
from src.utils.ui import RolePageView
from src.utils.cache import UserCache
from src.utils.i18n import get_default_locale, get_guild_locale, get_all_localizations, t

async def addtag(ctx, price, role):
    """管理员命令：添加身份组到商店"""
    supabase = get_connection()
    locale = get_guild_locale(ctx.guild.id if ctx.guild else None)

    try:
        # 使用upsert来实现INSERT ... ON DUPLICATE KEY UPDATE的功能
        # 添加guild_id以实现服务器隔离
        supabase.table("tags").upsert({
            "guild_id": str(ctx.guild.id),
            "role_id": str(role.id),
            "price": price
        }, on_conflict="guild_id,role_id").execute()

        await ctx.send(t("shop_module.roles.add.success", locale=locale, role=role.name, price=price))
    except Exception as e:
        print(t("debug.shop.add_role_failed", locale=get_guild_locale(ctx.guild.id), error=str(e)))
        await ctx.send(t("shop_module.roles.add.error", locale=locale))

async def roleshop(ctx):
    """查看身份组商店"""
    supabase = get_connection()
    locale = get_guild_locale(ctx.guild.id if ctx.guild else None)

    try:
        # 只显示当前服务器的身份组
        result = supabase.table("tags").select("role_id, price").eq("guild_id", str(ctx.guild.id)).order("price").execute()
        rows = [(int(row["role_id"]), row["price"]) for row in result.data]

        if not rows:
            await ctx.send(t("shop_module.roles.shop.empty", locale=locale))
            return

        view = RolePageView(ctx, rows, locale)
        await view.send_initial()
    except Exception as e:
        print(t("debug.shop.get_role_list_failed", locale=get_guild_locale(ctx.guild.id), error=str(e)))
        await ctx.send(t("shop_module.roles.shop.error", locale=locale))

async def buytag(ctx, role_name):
    """购买身份组"""
    guild = ctx.guild
    role = discord.utils.get(guild.roles, name=role_name)
    locale = get_guild_locale(ctx.guild.id if ctx.guild else None)
    if not role:
        await ctx.send(t("shop_module.roles.buy.not_found", locale=locale))
        return

    supabase = get_connection()

    try:
        # 获取身份组价格(只查询当前服务器的身份组)
        tag_result = supabase.table("tags").select("price").eq("guild_id", str(ctx.guild.id)).eq("role_id", str(role.id)).execute()
        if not tag_result.data:
            await ctx.send(t("shop_module.roles.buy.not_available", locale=locale))
            return
        price = tag_result.data[0]["price"]

        # 获取用户内部ID和积分
        user_internal_id = await UserCache.get_user_id(ctx.guild.id, ctx.author.id)
        if not user_internal_id:
            await ctx.send(t("shop_module.roles.buy.user_missing", locale=locale))
            return

        current_points = await UserCache.get_points(ctx.guild.id, ctx.author.id)
        if current_points < price:
            await ctx.send(t("shop_module.roles.buy.insufficient", locale=locale))
            return

        await ctx.send(t("shop_module.roles.buy.confirm_prompt", locale=locale, role=role.name))

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            reply = await ctx.bot.wait_for("message", check=check, timeout=10.0)
            if reply.content.upper() != "Y":
                await ctx.send(t("shop_module.roles.buy.cancelled", locale=locale))
                return
        except:
            await ctx.send(t("shop_module.roles.buy.timeout", locale=locale))
            return

        # 扣除积分
        await UserCache.update_points(ctx.guild.id, ctx.author.id, user_internal_id, -price)

        await ctx.author.add_roles(role)
        await ctx.send(t("shop_module.roles.buy.success", locale=locale, role=role.name))

    except Exception as e:
        print(t("debug.shop.add_item_failed", locale=get_guild_locale(interaction.guild.id), error=str(e)))
        await ctx.send(t("shop_module.roles.buy.error", locale=locale))

async def removetag(ctx, role: discord.Role):
    """管理员命令：删除身份组商店中的某个身份组"""
    supabase = get_connection()
    locale = get_guild_locale(ctx.guild.id if ctx.guild else None)

    try:
        # 删除指定的身份组
        result = supabase.table("tags").delete().eq("guild_id", str(ctx.guild.id)).eq("role_id", str(role.id)).execute()

        if result.data:
            await ctx.send(t("shop_module.roles.remove.success", locale=locale, role=role.name))
        else:
            await ctx.send(t("shop_module.roles.remove.not_found", locale=locale, role=role.name))
    except Exception as e:
        print(f"删除身份组失败: {e}")
        await ctx.send(t("shop_module.roles.remove.error", locale=locale))

async def updatetagprice(ctx, role: discord.Role, new_price: int):
    """管理员命令：更新身份组的价格"""
    supabase = get_connection()
    locale = get_guild_locale(ctx.guild.id if ctx.guild else None)

    try:
        # 更新身份组价格
        result = supabase.table("tags").update({
            "price": new_price
        }).eq("guild_id", str(ctx.guild.id)).eq("role_id", str(role.id)).execute()

        if result.data:
            await ctx.send(t("shop_module.roles.update.success", locale=locale, role=role.name, price=new_price))
        else:
            await ctx.send(t("shop_module.roles.update.not_found", locale=locale, role=role.name))
    except Exception as e:
        print(f"更新身份组价格失败: {e}")
        await ctx.send(t("shop_module.roles.update.error", locale=locale))

async def listtags(ctx):
    """管理员命令：查看当前服务器所有已添加的身份组"""
    supabase = get_connection()
    locale = get_guild_locale(ctx.guild.id if ctx.guild else None)

    try:
        result = supabase.table("tags").select("role_id, price").eq("guild_id", str(ctx.guild.id)).order("price").execute()

        if not result.data:
            await ctx.send(t("shop_module.roles.list.empty", locale=locale))
            return

        embed = discord.Embed(
            title=t("shop_module.roles.list.title", locale=locale),
            description=t("shop_module.roles.list.description", locale=locale),
            color=discord.Color.blue()
        )

        for tag in result.data:
            role = ctx.guild.get_role(int(tag["role_id"]))
            if role:
                embed.add_field(
                    name=f"{role.name}",
                    value=t("shop_module.roles.list.price", locale=locale, price=tag['price']),
                    inline=False
                )
            else:
                embed.add_field(
                    name=t("shop_module.roles.pagination.unknown_role", locale=locale, role_id=tag['role_id']),
                    value=t("shop_module.roles.list.price_missing", locale=locale, price=tag['price']),
                    inline=False
                )

        await ctx.send(embed=embed)
    except Exception as e:
        print(t("debug.shop.get_role_list_failed", locale=get_guild_locale(ctx.guild.id), error=str(e)))
        await ctx.send(t("shop_module.roles.list.error", locale=locale))

# ========== Slash命令部分 ==========

async def tag_shop(interaction: discord.Interaction):
    """显示身份组商店（slash命令版本）"""
    supabase = get_connection()
    locale = get_guild_locale(interaction.guild.id if interaction.guild else None)

    try:
        # 只显示当前服务器的身份组
        result = supabase.table("tags").select("role_id, price").eq("guild_id", str(interaction.guild.id)).order("price").execute()
        rows = [(int(row["role_id"]), row["price"]) for row in result.data]

        if not rows:
            await interaction.response.send_message(t("shop_module.roles.shop.empty", locale=locale), ephemeral=True)
            return

        # 创建embed显示
        embed = discord.Embed(
            title=t("shop_module.roles.shop.title", locale=locale),
            description=t("shop_module.roles.shop.description", locale=locale),
            color=discord.Color.gold()
        )

        for role_id, price in rows:
            role = interaction.guild.get_role(int(role_id))
            if role:
                embed.add_field(
                    name=f"{role.name}",
                    value=t("shop_module.roles.shop.price", locale=locale, price=price),
                    inline=True
                )

        embed.set_footer(text=t("shop_module.roles.shop.footer", locale=locale))
        await interaction.response.send_message(embed=embed)

    except Exception as e:
        print(t("debug.shop.get_role_list_failed", locale=get_guild_locale(ctx.guild.id), error=str(e)))
        await interaction.response.send_message(t("shop_module.roles.shop.error", locale=locale), ephemeral=True)

async def tag_buy(interaction: discord.Interaction, role_name: str):
    """购买身份组（slash命令版本）"""
    guild = interaction.guild
    role = discord.utils.get(guild.roles, name=role_name)
    locale = get_guild_locale(guild.id if guild else None)
    if not role:
        await interaction.response.send_message(t("shop_module.roles.buy.not_found", locale=locale), ephemeral=True)
        return

    supabase = get_connection()

    try:
        # 获取身份组价格(只查询当前服务器的身份组)
        tag_result = supabase.table("tags").select("price").eq("guild_id", str(guild.id)).eq("role_id", str(role.id)).execute()
        if not tag_result.data:
            await interaction.response.send_message(t("shop_module.roles.buy.not_available", locale=locale), ephemeral=True)
            return
        price = tag_result.data[0]["price"]

        # 获取用户内部ID和积分
        user_internal_id = await UserCache.get_user_id(guild.id, interaction.user.id)
        if not user_internal_id:
            await interaction.response.send_message(t("shop_module.roles.buy.user_missing", locale=locale), ephemeral=True)
            return

        current_points = await UserCache.get_points(guild.id, interaction.user.id)
        if current_points < price:
            await interaction.response.send_message(
                t("shop_module.roles.buy.insufficient_detail", locale=locale, price=price, current=current_points),
                ephemeral=True
            )
            return

        # 确认购买
        embed = discord.Embed(
            title=t("shop_module.roles.buy.confirm_embed_title", locale=locale),
            description=t(
                "shop_module.roles.buy.confirm_embed_desc",
                locale=locale,
                role=role.name,
                price=price,
                current=current_points,
                remaining=current_points - price
            ),
            color=discord.Color.gold()
        )

        # 创建确认按钮
        class ConfirmView(discord.ui.View):
            def __init__(self, requester_id: int, locale: str):
                super().__init__(timeout=30)
                self.value = None
                self.requester_id = requester_id
                self.locale = locale

                confirm_button = discord.ui.Button(
                    label=t("shop_module.roles.buy.button_confirm", locale=self.locale),
                    style=discord.ButtonStyle.green
                )
                cancel_button = discord.ui.Button(
                    label=t("shop_module.roles.buy.button_cancel", locale=self.locale),
                    style=discord.ButtonStyle.red
                )

                async def confirm_callback(button_interaction: discord.Interaction):
                    if button_interaction.user.id != self.requester_id:
                        await button_interaction.response.send_message(
                            t("shop_module.roles.buy.not_request", locale=self.locale),
                            ephemeral=True
                        )
                        return
                    self.value = True
                    await button_interaction.response.defer()
                    self.stop()

                async def cancel_callback(button_interaction: discord.Interaction):
                    if button_interaction.user.id != self.requester_id:
                        await button_interaction.response.send_message(
                            t("shop_module.roles.buy.not_request", locale=self.locale),
                            ephemeral=True
                        )
                        return
                    self.value = False
                    await button_interaction.response.defer()
                    self.stop()

                confirm_button.callback = confirm_callback  # type: ignore
                cancel_button.callback = cancel_callback  # type: ignore

                self.add_item(confirm_button)
                self.add_item(cancel_button)

        view = ConfirmView(interaction.user.id, locale)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        # 等待用户确认
        await view.wait()

        if view.value is None:
            await interaction.edit_original_response(
                content=t("shop_module.roles.buy.timeout_edit", locale=locale),
                embed=None,
                view=None
            )
            return
        elif view.value is False:
            await interaction.edit_original_response(
                content=t("shop_module.roles.buy.cancel_edit", locale=locale),
                embed=None,
                view=None
            )
            return

        # 执行购买
        await UserCache.update_points(guild.id, interaction.user.id, user_internal_id, -price)
        await interaction.user.add_roles(role)

        success_embed = discord.Embed(
            title=t("shop_module.roles.buy.success_embed_title", locale=locale),
            description=t("shop_module.roles.buy.success_embed_desc", locale=locale, role=role.name),
            color=discord.Color.green()
        )
        await interaction.edit_original_response(content=None, embed=success_embed, view=None)

    except Exception as e:
        print(t("debug.shop.add_item_failed", locale=get_guild_locale(interaction.guild.id), error=str(e)))
        await interaction.response.send_message(t("shop_module.roles.buy.error", locale=locale), ephemeral=True)

async def tag_action_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """为tag命令的action参数提供基于服务器语言的自动补全"""
    from src.utils.i18n import t, get_guild_locale

    # 获取服务器语言设置
    server_locale = get_guild_locale(interaction.guild.id)

    actions = [
        ("shop", "shop_module.roles.slash.choice_shop"),
        ("buy", "shop_module.roles.slash.choice_buy")
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

def setup(bot):
    """注册/tag slash命令组"""

    @bot.tree.command(name="tag", description="Role shop - view and purchase server roles")
    @app_commands.describe(
        action="Select action type",
        role_name="Select role to purchase"
    )
    @app_commands.autocomplete(action=tag_action_autocomplete)
    async def tag_command(interaction: discord.Interaction, action: str, role_name: str = None):
        """统一的/tag命令入口"""
        locale = get_guild_locale(interaction.guild.id if interaction.guild else None)

        if action == "shop":
            await tag_shop(interaction)
        elif action == "buy":
            if not role_name:
                await interaction.response.send_message(t("shop_module.roles.slash.missing_name", locale=locale), ephemeral=True)
                return
            await tag_buy(interaction, role_name)

    # Apply command localizations if available
    tag_command.description_localizations = get_all_localizations("shop_module.roles.slash.action_description")
