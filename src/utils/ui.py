import discord
from src.utils.i18n import t

def create_embed(title: str, description: str, color: discord.Color = discord.Color.blue()) -> discord.Embed:
    """创建一个标准的嵌入消息"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )
    return embed

# 用于分页角色商店显示的视图
class RolePageView(discord.ui.View):
    def __init__(self, ctx, rows, locale):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.rows = rows
        self.index = 0
        self.message = None
        self.locale = locale

        # Localize button labels after view initialization
        if self.children:
            if len(self.children) >= 1:
                self.children[0].label = t("shop_module.roles.pagination.button_prev", locale=self.locale)
            if len(self.children) >= 2:
                self.children[1].label = t("shop_module.roles.pagination.button_next", locale=self.locale)

    async def send_initial(self):
        embed = self.get_embed(self.index)
        self.message = await self.ctx.send(embed=embed, view=self)

    def get_embed(self, index: int) -> discord.Embed:
        role_id, price = self.rows[index]
        role = self.ctx.guild.get_role(role_id)
        name = role.name if role else t("shop_module.roles.pagination.unknown_role", locale=self.locale, role_id=role_id)
        color = role.color if role and role.color.value != 0 else discord.Color.default()

        embed = discord.Embed(
            title=name,
            description=t(
                "shop_module.roles.pagination.description",
                locale=self.locale,
                price=price,
                index=index + 1,
                total=len(self.rows)
            ),
            color=color
        )
        return embed

    @discord.ui.button(label="◀️ 上一页", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message(
                t("shop_module.roles.pagination.no_permission", locale=self.locale),
                ephemeral=True
            )
        self.index = (self.index - 1) % len(self.rows)
        await interaction.response.edit_message(embed=self.get_embed(self.index), view=self)

    @discord.ui.button(label="▶️ 下一页", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message(
                t("shop_module.roles.pagination.no_permission", locale=self.locale),
                ephemeral=True
            )
        self.index = (self.index + 1) % len(self.rows)
        await interaction.response.edit_message(embed=self.get_embed(self.index), view=self)
