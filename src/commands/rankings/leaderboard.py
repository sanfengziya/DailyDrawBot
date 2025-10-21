import discord
from discord import File
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import os
from src.utils.ranking import RankingManager

def create_circle_avatar(avatar_img, size=80):
    """将头像裁剪为圆形"""
    mask = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)

    avatar_circle = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    avatar_circle.paste(avatar_img, (0, 0))
    avatar_circle.putalpha(mask)

    return avatar_circle

def create_gradient_background(width, height):
    """创建渐变背景"""
    base = Image.new('RGB', (width, height), '#1a1a2e')
    overlay = Image.new('RGB', (width, height), '#16213e')

    # 创建渐变效果
    for y in range(height):
        alpha = int(255 * (y / height))
        for x in range(width):
            r1, g1, b1 = base.getpixel((x, 0))
            r2, g2, b2 = overlay.getpixel((x, 0))
            r = int(r1 + (r2 - r1) * alpha / 255)
            g = int(g1 + (g2 - g1) * alpha / 255)
            b = int(b1 + (b2 - b1) * alpha / 255)
            base.putpixel((x, y), (r, g, b))

    return base

def draw_rounded_rectangle(draw, xy, radius, fill, outline=None, width=1):
    """绘制圆角矩形"""
    x1, y1, x2, y2 = xy

    # 绘制圆角
    draw.pieslice([x1, y1, x1 + radius * 2, y1 + radius * 2], 180, 270, fill=fill, outline=outline, width=width)
    draw.pieslice([x2 - radius * 2, y1, x2, y1 + radius * 2], 270, 360, fill=fill, outline=outline, width=width)
    draw.pieslice([x1, y2 - radius * 2, x1 + radius * 2, y2], 90, 180, fill=fill, outline=outline, width=width)
    draw.pieslice([x2 - radius * 2, y2 - radius * 2, x2, y2], 0, 90, fill=fill, outline=outline, width=width)

    # 绘制矩形部分
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill, outline=outline, width=width)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill, outline=outline, width=width)

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
                avatar_bytes = await member.display_avatar.replace(size=128).read()
                avatar = Image.open(BytesIO(avatar_bytes)).convert("RGBA").resize((80, 80))
                entries.append({
                    'rank': rank,
                    'avatar': avatar,
                    'name': member.name,
                    'points': points
                })
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

    # 字体设置
    font_path = "src/res/Comic Sans MS.ttf"
    if os.path.exists(font_path):
        title_font = ImageFont.truetype(font_path, 32)
        name_font = ImageFont.truetype(font_path, 18)
        points_font = ImageFont.truetype(font_path, 14)
        rank_font = ImageFont.truetype(font_path, 16)
    else:
        title_font = name_font = points_font = rank_font = ImageFont.load_default()

    # 图片尺寸
    width = 700
    card_height = 100
    card_spacing = 15
    padding = 40
    title_height = 80

    height = title_height + padding * 2 + (card_height + card_spacing) * len(entries)

    # 创建渐变背景
    img = create_gradient_background(width, height)
    draw = ImageDraw.Draw(img)

    # 绘制标题
    title = "LEADERBOARD"
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    title_x = (width - title_width) // 2
    draw.text((title_x, padding), title, fill='#FFD700', font=title_font)

    # 排名文字格式
    rank_suffix = {1: 'st', 2: 'nd', 3: 'rd'}

    # 绘制每个排名卡片
    y = padding + title_height
    for entry in entries:
        rank = entry['rank']
        avatar = entry['avatar']
        name = entry['name']
        points = entry['points']

        # 前三名使用特殊颜色
        if rank == 1:
            card_color = '#2E3440'  # 金色调
            text_color = '#FFD700'
            rank_color = '#FFD700'
        elif rank == 2:
            card_color = '#2E3440'  # 银色调
            text_color = '#C0C0C0'
            rank_color = '#C0C0C0'
        elif rank == 3:
            card_color = '#2E3440'  # 铜色调
            text_color = '#CD7F32'
            rank_color = '#CD7F32'
        else:
            card_color = '#2E3440'
            text_color = '#ECEFF4'
            rank_color = '#88C0D0'

        # 绘制卡片背景（圆角矩形）
        card_x1 = padding
        card_y1 = y
        card_x2 = width - padding
        card_y2 = y + card_height
        draw_rounded_rectangle(draw, (card_x1, card_y1, card_x2, card_y2), 15, card_color)

        # 绘制排名
        rank_text = str(rank)
        rank_bbox = draw.textbbox((0, 0), rank_text, font=rank_font)
        rank_width = rank_bbox[2] - rank_bbox[0]
        rank_x = card_x1 + 25
        rank_y = card_y1 + (card_height - (rank_bbox[3] - rank_bbox[1])) // 2
        draw.text((rank_x, rank_y), rank_text, fill=rank_color, font=rank_font)

        # 绘制圆形头像
        circle_avatar = create_circle_avatar(avatar, 80)
        avatar_x = rank_x + rank_width + 20
        avatar_y = card_y1 + 10
        img.paste(circle_avatar, (avatar_x, avatar_y), circle_avatar)

        # 绘制用户名
        name_x = avatar_x + 90
        name_y = card_y1 + 20
        # 限制用户名长度
        if len(name) > 15:
            name = name[:15] + '...'
        draw.text((name_x, name_y), name, fill=text_color, font=name_font)

        # 绘制积分
        points_text = f"{points:,} points"
        points_x = name_x
        points_y = card_y1 + 55
        draw.text((points_x, points_y), points_text, fill='#88C0D0', font=points_font)

        y += card_height + card_spacing

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    await ctx.send(file=File(fp=buffer, filename="ranking.png"))