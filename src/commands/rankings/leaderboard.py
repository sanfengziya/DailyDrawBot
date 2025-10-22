import discord
from discord import File, app_commands
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import os
from src.utils.ranking import RankingManager
from src.db.database import get_connection

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

async def get_ranking_data(guild_id: int, type: str, limit: int = 30):
    """
    获取不同类型的排行榜数据

    Args:
        guild_id: 服务器ID
        type: 排行榜类型
        limit: 返回数量限制

    Returns:
        list: [(user_id, value), ...] 格式的排行榜数据
    """
    supabase = get_connection()

    try:
        if type == "points":
            # 积分排行榜（使用Redis缓存）
            rows = await RankingManager.get_top_rankings(guild_id, limit=limit)
            if not rows:
                await RankingManager.initialize_ranking(guild_id)
                rows = await RankingManager.get_top_rankings(guild_id, limit=limit)
            return rows

        elif type == "pets":
            # 宠物数量排行榜
            result = supabase.rpc('get_pet_count_ranking', {
                'p_guild_id': guild_id,
                'p_limit': limit
            }).execute()

            if result.data:
                return [(int(row['discord_user_id']), row['pet_count']) for row in result.data]
            return []

        elif type == "hatched_eggs":
            # 已孵化蛋数量排行榜
            result = supabase.rpc('get_hatched_eggs_ranking', {
                'p_guild_id': guild_id,
                'p_limit': limit
            }).execute()

            if result.data:
                return [(int(row['discord_user_id']), row['hatched_count']) for row in result.data]
            return []

        elif type == "blackjack_wins":
            # 21点胜场排行榜
            result = supabase.rpc('get_blackjack_wins_ranking', {
                'p_guild_id': guild_id,
                'p_limit': limit
            }).execute()

            if result.data:
                return [(int(row['discord_user_id']), row['total_wins']) for row in result.data]
            return []

        return []

    except Exception as e:
        print(f"获取排行榜数据出错：{str(e)}")
        return []

def get_ranking_config(type: str):
    """
    获取排行榜配置信息

    Returns:
        dict: {'title': 标题, 'value_label': 数值标签, 'value_format': 格式化函数}
    """
    configs = {
        "points": {
            "title": "POINTS LEADERBOARD",
            "value_label": "points",
            "value_format": lambda x: f"{x:,} points"
        },
        "pets": {
            "title": "PETS LEADERBOARD",
            "value_label": "pets",
            "value_format": lambda x: f"{x} pets"
        },
        "hatched_eggs": {
            "title": "HATCHED EGGS LEADERBOARD",
            "value_label": "hatched eggs",
            "value_format": lambda x: f"{x} eggs"
        },
        "blackjack_wins": {
            "title": "BLACKJACK WINS",
            "value_label": "wins",
            "value_format": lambda x: f"{x} wins"
        }
    }

    return configs.get(type, configs["points"])

async def leaderboard(interaction: discord.Interaction, type: str = "points"):
    # 延迟响应，因为生成图片可能需要时间
    await interaction.response.defer()

    try:
        # 获取当前服务器ID
        guild_id = interaction.guild.id

        # 获取排行榜配置
        config = get_ranking_config(type)

        # 获取更多排名数据以应对部分用户已离开服务器的情况
        rows = await get_ranking_data(guild_id, type, limit=30)

        if not rows:
            await interaction.followup.send(f"当前服务器还没有{config['value_label']}排名数据。")
            return

    except Exception as e:
        await interaction.followup.send(f"查询排名数据时出错：{str(e)}")
        return

    entries = []
    rank = 1
    for user_id, value in rows:
        # 检查用户是否仍在服务器中
        try:
            member = await interaction.guild.fetch_member(user_id)
            if member:
                avatar_bytes = await member.display_avatar.replace(size=128).read()
                avatar = Image.open(BytesIO(avatar_bytes)).convert("RGBA").resize((80, 80))
                entries.append({
                    'rank': rank,
                    'avatar': avatar,
                    'name': member.name,
                    'value': value
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
        await interaction.followup.send("当前服务器中没有符合条件的成员数据。")
        return

    # 字体设置
    font_paths = {
        'title': "src/res/Comic Sans MS.ttf",
        'name': "src/res/SnellRoundhand.ttc",
        'points': "src/res/Arial Rounded Bold.ttf"
    }

    # 尝试加载自定义字体，如果失败则使用默认字体
    try:
        title_font = ImageFont.truetype(font_paths['title'], 32) if os.path.exists(font_paths['title']) else ImageFont.load_default()
        name_font = ImageFont.truetype(font_paths['name'], 18) if os.path.exists(font_paths['name']) else ImageFont.load_default()
        points_font = ImageFont.truetype(font_paths['points'], 14) if os.path.exists(font_paths['points']) else ImageFont.load_default()
        rank_font = ImageFont.truetype(font_paths['title'], 16) if os.path.exists(font_paths['name']) else ImageFont.load_default()
    except Exception:
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
    title = config['title']
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    title_x = (width - title_width) // 2
    draw.text((title_x, padding), title, fill='#FFD700', font=title_font)

    # 绘制每个排名卡片
    y = padding + title_height
    for entry in entries:
        rank = entry['rank']
        avatar = entry['avatar']
        name = entry['name']
        value = entry['value']

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
        name_x = avatar_x + 100
        name_y = card_y1 + 20
        # 限制用户名长度
        if len(name) > 15:
            name = name[:15] + '...'
        draw.text((name_x, name_y), name, fill=text_color, font=name_font)

        # 绘制数值（积分/宠物数量/战力等）
        value_text = config['value_format'](value)
        value_x = name_x
        value_y = card_y1 + 60
        draw.text((value_x, value_y), value_text, fill='#88C0D0', font=points_font)

        y += card_height + card_spacing

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    await interaction.followup.send(file=File(fp=buffer, filename="ranking.png"))

def setup(bot):
    """注册斜杠命令"""
    @bot.tree.command(name="leaderboard", description="查看服务器排行榜")
    @app_commands.describe(
        type="选择排行榜类型"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="points", value="points"),
        app_commands.Choice(name="pets", value="pets"),
        app_commands.Choice(name="hatched eggs", value="hatched_eggs"),
        app_commands.Choice(name="blackjack wins", value="blackjack_wins")
    ])
    async def leaderboard_command(interaction: discord.Interaction, type: str = "points"):
        await leaderboard(interaction, type)