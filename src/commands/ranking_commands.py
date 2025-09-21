import discord
from discord import File
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import os

async def ranking(ctx):
    try:
        from src.db.database import get_supabase_client
        supabase = get_supabase_client()
        
        # 获取当前服务器ID
        guild_id = str(ctx.guild.id)
        
        # 查询当前服务器排名前10的用户
        ranking_response = supabase.table('users').select('discord_user_id, points').eq('guild_id', guild_id).order('points', desc=True).limit(10).execute()
        
        if not ranking_response.data:
            await ctx.send("当前服务器还没有排名数据。")
            return
            
        rows = [(user['discord_user_id'], user['points']) for user in ranking_response.data]
        
    except Exception as e:
        await ctx.send(f"查询排名数据时出错：{str(e)}")
        return

    entries = []
    for i, (user_id, points) in enumerate(rows, start=1):
        user = await ctx.bot.fetch_user(user_id)
        avatar_bytes = await user.display_avatar.replace(size=64).read()
        avatar = Image.open(BytesIO(avatar_bytes)).convert("RGBA").resize((64, 64))
        entries.append((avatar, f"{i}. {user.name}: {points} points"))

    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    
    if os.path.exists(font_path):
        font = ImageFont.truetype(font_path, 20)
    else:
        font = ImageFont.load_default()

    padding = 20
    line_height = 85
    draw_dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    def text_width(text: str) -> int:
        box = draw_dummy.textbbox((0, 0), text, font=font)
        return box[2] - box[0]

    max_text_width = max(text_width(t) for _, t in entries)
    width = max_text_width + 140

    height = line_height * len(entries) + padding * 2
    img = Image.new("RGBA", (width, height), (245, 245, 245, 255))
    draw = ImageDraw.Draw(img)

    y = padding
    for avatar, text in entries:
        img.paste(avatar, (padding, y + 3), avatar)
        draw.text((padding + 70, y + 20), text, fill=(0, 0, 0), font=font)
        draw.line((padding, y, width - padding, y), fill=(220, 220, 220), width=1)
        y += line_height
    draw.line((padding, y, width - padding, y), fill=(220, 220, 220), width=1)

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    await ctx.send(file=File(fp=buffer, filename="ranking.png"))