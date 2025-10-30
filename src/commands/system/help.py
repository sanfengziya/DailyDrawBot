import discord
from src.config.config import MAX_PAID_DRAWS_PER_DAY, DRAW_COST
from src.utils.i18n import get_guild_locale, t

async def help_command(interaction: discord.Interaction):
    """Show help information for all commands"""
    

    embed = create_help_embed(interaction)
    
    await interaction.response.send_message(embed=embed)

def create_help_embed(interaction: discord.Interaction):
    """Create a localized help embed."""
    guild_id = interaction.guild.id if interaction.guild else None
    locale = get_guild_locale(guild_id)

    embed = discord.Embed(
        title=t("help.title", locale=locale),
        description=t("help.description", locale=locale),
        color=discord.Color.blue()
    )

    section_keys = [
        "system",
        "draw",
        "egg",
        "pet",
        "shop",
        "forge",
        "roles",
        "quiz",
        "blackjack",
        "leaderboard",
    ]

    for key in section_keys:
        embed.add_field(
            name=t(f"help.sections.{key}.name", locale=locale),
            value=t(
                f"help.sections.{key}.value",
                locale=locale,
                max_paid_draws=MAX_PAID_DRAWS_PER_DAY,
                wheel_cost=DRAW_COST
            ),
            inline=False
        )

    if interaction.user.guild_permissions.administrator:
        embed.add_field(
            name=t("help.sections.admin.name", locale=locale),
            value=t("help.sections.admin.value", locale=locale),
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
