import discord
from discord.ui import Select, View
from src.config.config import MAX_PAID_DRAWS_PER_DAY, DRAW_COST
from src.utils.i18n import get_guild_locale, t

class HelpView(View):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=180)  # 3分钟超时
        self.interaction = interaction
        self.guild_id = interaction.guild.id if interaction.guild else None
        self.locale = get_guild_locale(self.guild_id)

        # 添加系统选择下拉菜单
        self.add_item(HelpSelect(self))

class HelpSelect(Select):
    def __init__(self, view):
        super().__init__()  # 先调用父类构造函数
        self._view = view  # 使用私有变量存储view引用
        self.guild_id = view.guild_id
        self.locale = view.locale

        # 获取所有系统选项
        options = []
        section_keys = [
            ("system", "ℹ️ 系统提示"),
            ("draw", "🎲 抽奖系统"),
            ("egg", "🥚 蛋系统"),
            ("pet", "🐾 宠物系统"),
            ("shop", "🏪 杂货铺系统"),
            ("forge", "🔨 锻造系统"),
            ("roles", "🏷️ 身份组系统"),
            ("quiz", "🎮 答题系统"),
            ("blackjack", "🎰 二十一点游戏"),
            ("texas", "🃏 德州扑克"),
            ("leaderboard", "🏆 排行榜系统"),
        ]

        # 检查是否为管理员，添加管理员选项
        if self._view.interaction.user.guild_permissions.administrator:
            section_keys.append(("admin", "⚙️ Admin Commands"))

        # 添加返回主菜单选项
        section_keys.insert(0, ("home", "🏠 Main Menu"))

        for key, _ in section_keys:
            # 处理主菜单的特殊情况
            if key == "home":
                clean_name = t("help.home_menu.name", locale=self.locale).replace("🏠 ", "")
                description = t("help.home_menu.description", locale=self.locale)
                emoji = "🏠"
            else:
                display_name = t(f"help.sections.{key}.name", locale=self.locale)
                clean_name = display_name.replace("ℹ️ ", "").replace("🎲 ", "").replace("🥚 ", "").replace("🐾 ", "").replace("🏪 ", "").replace("🔨 ", "").replace("🏷️ ", "").replace("🎮 ", "").replace("🎰 ", "").replace("🏆 ", "").replace("⚙️ ", "")
                emoji = display_name.split()[0] if display_name.split() else None
                description = t("help.view_description", locale=self.locale, system_name=clean_name)

            options.append(
                discord.SelectOption(
                    label=clean_name,
                    description=description,
                    emoji=emoji,
                    value=key
                )
            )

        super().__init__(
            placeholder=t("help.select_placeholder", locale=self.locale),
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_system = self.values[0]
        await self.update_help_embed(interaction, selected_system)

    async def update_help_embed(self, interaction: discord.Interaction, system_key: str):
        """更新帮助信息显示指定系统或主菜单"""
        if system_key == "home":
            # 返回主菜单
            embed = create_welcome_embed(self._view.interaction)
        else:
            # 显示特定系统信息
            embed = discord.Embed(
                title=t("help.welcome_title", locale=self.locale),
                color=discord.Color.blue()
            )

            # 添加所选系统的详细信息
            system_name = t(f"help.sections.{system_key}.name", locale=self.locale)
            system_value = t(
                f"help.sections.{system_key}.value",
                locale=self.locale,
                max_paid_draws=MAX_PAID_DRAWS_PER_DAY,
                wheel_cost=DRAW_COST
            )

            embed.description = t("help.welcome_description", locale=self.locale)
            embed.add_field(
                name=system_name,
                value=system_value,
                inline=False
            )

            # 添加提示信息
            embed.set_footer(text=t("help.usage_tip", locale=self.locale))

        # 更新原有消息，保持视图
        await interaction.response.edit_message(embed=embed, view=self._view)

async def help_command(interaction: discord.Interaction):
    """Show help information for all commands"""
    # 创建欢迎界面
    embed = create_welcome_embed(interaction)
    view = HelpView(interaction)

    await interaction.response.send_message(embed=embed, view=view)

def create_welcome_embed(interaction: discord.Interaction):
    """创建欢迎界面的embed"""
    guild_id = interaction.guild.id if interaction.guild else None
    locale = get_guild_locale(guild_id)

    embed = discord.Embed(
        title=t("help.welcome_title", locale=locale),
        description=t("help.welcome_description", locale=locale),
        color=discord.Color.blue()
    )

    # 添加简短的系统概览
    section_keys = [
        ("draw", "🎲 抽奖系统"),
        ("egg", "🥚 蛋系统"),
        ("pet", "🐾 宠物系统"),
        ("shop", "🏪 杂货铺系统"),
        ("forge", "🔨 锻造系统"),
        ("roles", "🏷️ 身份组系统"),
        ("quiz", "🎮 答题系统"),
        ("blackjack", "🎰 二十一点游戏"),
        ("texas", "🃏 德州扑克"),
        ("leaderboard", "🏆 排行榜系统"),
    ]

    # 检查是否为管理员，添加管理员选项
    if interaction.user.guild_permissions.administrator:
        section_keys.append(("admin", "⚙️ 管理员命令"))

    # 创建概览描述
    overview = t("help.systems_overview", locale=locale) + "\n"
    for key, _ in section_keys:
        localized_name = t(f"help.sections.{key}.name", locale=locale)
        emoji = localized_name.split()[0] if localized_name.split() else "📋"
        name_clean = localized_name.replace("ℹ️ ", "").replace("🎲 ", "").replace("🥚 ", "").replace("🐾 ", "").replace("🏪 ", "").replace("🔨 ", "").replace("🏷️ ", "").replace("🎮 ", "").replace("🎰 ", "").replace("🏆 ", "").replace("⚙️ ", "")
        overview += f"• {emoji} **{name_clean}**\n"

    embed.add_field(
        name=t("help.modules_title", locale=locale),
        value=overview,
        inline=False
    )

    embed.set_footer(
        text=t(
            "help.footer",
            locale=locale,
            max_paid_draws=MAX_PAID_DRAWS_PER_DAY,
            wheel_cost=DRAW_COST
        )
    )

    return embed
