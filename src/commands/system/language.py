"""Language configuration commands."""

from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.utils.i18n import (
    SUPPORTED_LOCALES,
    format_supported_locales,
    get_all_localizations,
    get_guild_locale,
    get_locale_label,
    is_supported,
    set_guild_locale,
    t,
)


def _apply_language_change(guild_id: int, locale: Optional[str]):
    """Return tuple(success, key, params, response_locale)."""
    current_locale = get_guild_locale(guild_id)

    if not locale:
        return False, "language.current", {"language": get_locale_label(current_locale)}, current_locale

    normalized = locale.strip()
    if not is_supported(normalized):
        return (
            False,
            "language.unsupported",
            {"locale": normalized, "codes": format_supported_locales()},
            current_locale,
        )

    if normalized == current_locale:
        return False, "language.unchanged", {"language": get_locale_label(current_locale)}, current_locale

    updated = set_guild_locale(guild_id, normalized)
    if updated:
        return True, "language.updated", {"language": get_locale_label(normalized)}, normalized

    return False, "common.unknown_error", {}, current_locale


async def set_language_prefix(ctx: commands.Context, locale: Optional[str] = None) -> None:
    """Prefix command handler for !setlanguage."""
    if ctx.guild is None:
        await ctx.send(t("language.guild_only", locale=None))
        return

    if not ctx.author.guild_permissions.administrator:
        await ctx.send(t("language.missing_permissions", locale=get_guild_locale(ctx.guild.id)))
        return

    success, key, params, response_locale = _apply_language_change(ctx.guild.id, locale)
    message = t(key, locale=response_locale, **params)

    if key in {"language.current", "language.unsupported"}:
        prompt = t(
            "language.prompt_supported",
            locale=response_locale,
            codes=format_supported_locales(),
        )
        message = f"{message}\n{prompt}"

    await ctx.send(message)


def build_locale_choice_list():
    choices = []
    for meta in SUPPORTED_LOCALES.values():
        display_name = f"{meta.label} ({meta.code})"
        choices.append(app_commands.Choice(name=display_name, value=meta.code))
    return choices


# Late import to avoid circular dependency at module load
from src.utils.i18n import get_default_locale  # noqa: E402


@app_commands.command(name="language", description="Set the server language")
@app_commands.describe(locale="Locale code to apply")
@app_commands.choices(locale=build_locale_choice_list())
@app_commands.guild_only()
async def language_command(interaction: discord.Interaction, locale: app_commands.Choice[str]):
    """Slash command to set server language."""
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message(
            t("language.guild_only", locale=get_default_locale()),
            ephemeral=True,
        )
        return

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            t("language.missing_permissions", locale=get_guild_locale(guild.id)),
            ephemeral=True,
        )
        return

    selected_locale = locale.value
    success, key, params, response_locale = _apply_language_change(guild.id, selected_locale)
    message = t(key, locale=response_locale, **params)

    await interaction.response.send_message(message, ephemeral=True)


def setup(bot: commands.Bot) -> None:
    """Register slash command on the bot."""
    # Ensure localized metadata for the language command itself
    name_loc = get_all_localizations("commands.language.name")
    desc_loc = get_all_localizations("commands.language.description")
    if name_loc:
        language_command.name_localizations = name_loc
    if desc_loc:
        language_command.description_localizations = desc_loc

    # Register the language command
    bot.tree.add_command(language_command)
