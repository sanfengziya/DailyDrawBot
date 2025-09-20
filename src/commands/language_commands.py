import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Optional

from src.config.config import YOUR_GUILD_ID
from src.db.database import get_connection
from src.utils.helpers import get_guild_language
from src.config.languages import AVAILABLE_LANGUAGES, get_text

class LanguageSelect(discord.ui.Select):
    def __init__(self, bot):
        self.bot = bot
        options = [
            discord.SelectOption(
                label=AVAILABLE_LANGUAGES[lang_code], 
                value=lang_code,
                description=f"Set bot language to {AVAILABLE_LANGUAGES[lang_code]}"
            ) for lang_code in AVAILABLE_LANGUAGES
        ]
        super().__init__(placeholder="Select language / 选择语言", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        # 检查权限
        if not interaction.user.guild_permissions.administrator:
            current_lang = get_guild_language(interaction.guild_id)
            await interaction.response.send_message(
                get_text("common", "permission_denied", current_lang),
                ephemeral=True
            )
            return

        selected_language = self.values[0]
        
        # 更新数据库中的语言设置
        supabase = get_connection()
        
        try:
            # 检查是否已有该服务器的语言设置
            result = supabase.table("guild_settings").select("*").eq("guild_id", str(interaction.guild_id)).execute()
            
            if result.data:
                # 更新现有记录
                supabase.table("guild_settings").update({
                    "language": selected_language
                }).eq("guild_id", str(interaction.guild_id)).execute()
            else:
                # 插入新记录
                supabase.table("guild_settings").insert({
                    "guild_id": str(interaction.guild_id),
                    "language": selected_language
                }).execute()
        except Exception as e:
            print(f"语言设置更新失败: {e}")
            await interaction.response.send_message(
                "语言设置更新失败，请稍后重试。",
                ephemeral=True
            )
            return
        
        # 获取选定语言的名称
        language_name = AVAILABLE_LANGUAGES[selected_language]
        
        # 使用选定语言的文本回复
        await interaction.response.send_message(
            get_text("language", "language_changed", selected_language, lang_name=language_name),
            ephemeral=True
        )

class LanguageView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=60)
        self.add_item(LanguageSelect(bot))

@app_commands.command(name="language", description="Change the bot's language / 更改机器人的语言")
@app_commands.guild_only()
async def language_command(interaction: discord.Interaction):
    # 检查权限
    if not interaction.user.guild_permissions.administrator:
        current_lang = get_guild_language(interaction.guild_id)
        await interaction.response.send_message(
            get_text("common", "permission_denied", current_lang),
            ephemeral=True
        )
        return
    
    # 显示语言选择菜单
    current_lang = get_guild_language(interaction.guild_id)
    current_language_name = AVAILABLE_LANGUAGES[current_lang]
    
    embed = discord.Embed(
        title=get_text("language", "select_language", current_lang),
        description=get_text("language", "current_language", current_lang, lang_name=current_language_name),
        color=discord.Color.blue()
    )
    
    await interaction.response.send_message(
        embed=embed,
        view=LanguageView(interaction.client),
        ephemeral=True
    )

# 注册命令到bot
def setup(bot):
    bot.tree.add_command(language_command)