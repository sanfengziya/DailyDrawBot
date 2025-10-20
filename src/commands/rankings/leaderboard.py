import discord
from discord import File
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import os
from src.utils.ranking import RankingManager

async def ranking(ctx):
    try:
        # 获取当前服务器ID
        guild_id = ctx.guild.id

        # 获取更多排名数据以应对部分用户已离开服务器的情况
        rows = await RankingManager.get_top_rankings(guild_id, limit=30)

        if not rows:
            # 如果Redis没有数据,从数据库初始化
            await RankingManager.initialize_ranking(guild_id)
            rows = await RankingManager.get_top_rankings(guild_id, limit=30)

            if not rows:
                await ctx.send("当前服务器还没有排名数据。")
                return

    except Exception as e:
        await ctx.send(f"查询排名数据时出错：{str(e)}")
        return

    entries = []
    rank = 1
    for user_id, points in rows:
        # 检查用户是否仍在服务器中
        try:
            member = await ctx.guild.fetch_member(user_id)
            if member:
                avatar_bytes = await member.display_avatar.replace(size=64).read()
                avatar = Image.open(BytesIO(avatar_bytes)).convert("RGBA").resize((64, 64))
                entries.append((avatar, f"{rank}. {member.name}: {points} points"))
                rank += 1

                # 已经收集够10个在服务器中的成员，停止
                if len(entries) >= 10:
                    break
        except discord.NotFound:
            # 用户不在服务器中，跳过
            continue
        except Exception:
            # 其他错误也跳过该用户
            continue

    if not entries:
        await ctx.send("当前服务器中没有符合条件的成员数据。")
        return

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