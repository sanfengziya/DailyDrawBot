import discord

# View for paginated role shop display
class RolePageView(discord.ui.View):
    def __init__(self, ctx, rows):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.rows = rows
        self.index = 0
        self.message = None

    async def send_initial(self):
        embed = self.get_embed(self.index)
        self.message = await self.ctx.send(embed=embed, view=self)

    def get_embed(self, index: int) -> discord.Embed:
        role_id, price = self.rows[index]
        role = self.ctx.guild.get_role(role_id)
        name = role.name if role else f"（未知角色）ID:{role_id}"
        color = role.color if role and role.color.value != 0 else discord.Color.default()

        embed = discord.Embed(
            title=name,
            description=f"价格：{price} 分\n\n第 {index + 1} / {len(self.rows)} 个",
            color=color
        )
        return embed

    @discord.ui.button(label="◀️ 上一页", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("你无法控制这个分页！", ephemeral=True)
        self.index = (self.index - 1) % len(self.rows)
        await interaction.response.edit_message(embed=self.get_embed(self.index), view=self)

    @discord.ui.button(label="▶️ 下一页", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("你无法控制这个分页！", ephemeral=True)
        self.index = (self.index + 1) % len(self.rows)
        await interaction.response.edit_message(embed=self.get_embed(self.index), view=self) 