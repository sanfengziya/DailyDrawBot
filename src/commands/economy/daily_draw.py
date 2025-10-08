import discord
import asyncio
import datetime
from src.db.database import get_connection
from src.utils.helpers import now_est, get_weighted_reward
from src.config.config import WHEEL_COST, MAX_PAID_DRAWS_PER_DAY
from src.utils.cache import UserCache
from src.utils.draw_limiter import DrawLimiter

async def draw(ctx, count: int = 1):
    """抽奖命令，支持指定次数（默认为1次）。只有完成免费抽奖后才能使用多次抽奖"""
    discord_user_id = ctx.author.id
    guild_id = ctx.guild.id

    # 验证抽奖次数
    if count < 1:
        await ctx.send("❌ 抽奖次数必须大于0")
        return
    if count > 50:
        await ctx.send("❌ 单次最多只能抽50次")
        return

    try:
        supabase = get_connection()

        # 使用Redis缓存获取用户ID
        user_id = await UserCache.get_user_id(guild_id, discord_user_id)

        if user_id is None:
            # 创建新用户
            create_response = supabase.table('users').insert({
                'guild_id': ctx.guild.id,
                'discord_user_id': ctx.author.id,
                'points': 0,
                'last_draw_date': None,
                'paid_draws_today': 0,
                'last_paid_draw_date': '1970-01-01',
                'equipped_pet_id': None,
                'last_pet_points_update': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
            }).execute()
            user_id = create_response.data[0]['id']

        # 使用Redis检查免费抽奖（异步）
        first_draw = await DrawLimiter.check_free_draw_available(guild_id, discord_user_id)

        # 使用Redis获取用户积分
        points = await UserCache.get_points(guild_id, discord_user_id)

    except Exception as e:
        await ctx.send(f"查询用户数据时出错：{str(e)}")
        return

    # 如果还有免费抽奖机会，只能抽1次
    if first_draw:
        if count > 1:
            await ctx.send("❌ 请先完成今天的免费抽奖，然后才能使用多次抽奖功能")
            return
        # 当天第一次抽奖 - 免费！
        await ctx.send(f"🎉 {ctx.author.mention} 开始今天的抽奖吧！")
    else:
        # 付费抽奖
        paid_draws_today = await DrawLimiter.get_paid_draw_count(guild_id, discord_user_id)
        total_cost = count * WHEEL_COST

        # 检查付费抽奖次数是否足够
        if paid_draws_today + count > MAX_PAID_DRAWS_PER_DAY:
            remaining_draws = MAX_PAID_DRAWS_PER_DAY - paid_draws_today
            embed = discord.Embed(
                title="❌ 付费抽奖次数不足",
                description=f"你今日已付费抽奖 **{paid_draws_today}** 次\n剩余付费抽奖次数: **{remaining_draws}** 次\n你要求抽奖 **{count}** 次\n\n请减少抽奖次数或明天再来！",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        # 检查积分是否足够
        if points < total_cost:
            embed = discord.Embed(
                title="❌ 积分不足",
                description=f"抽奖 **{count}** 次需要 **{total_cost}** 积分\n当前积分: **{points}**\n还需要: **{total_cost - points}** 积分",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        # 确认抽奖
        remaining_draws = MAX_PAID_DRAWS_PER_DAY - paid_draws_today
        embed = discord.Embed(
            title="🎰 付费抽奖确认",
            description=f"抽奖次数: **{count}** 次\n" +
                       f"消耗积分: **{total_cost}**\n" +
                       f"当前积分: **{points}**\n" +
                       f"今日已付费抽奖: **{paid_draws_today}** 次\n" +
                       f"剩余付费抽奖次数: **{remaining_draws}** 次\n\n" +
                       f"发送 `Y` 确认抽奖",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

        def check(m: discord.Message) -> bool:
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await ctx.bot.wait_for("message", check=check, timeout=15)
        except asyncio.TimeoutError:
            await ctx.send("⏰ 已取消抽奖。")
            return

        if msg.content.upper() != "Y":
            await ctx.send("❌ 已取消抽奖。")
            return

    # 执行抽奖
    rewards = []
    total_points = 0
    today = now_est().date()

    for i in range(count):
        # 如果是免费抽奖，跳过扣费和计数
        if not first_draw:
            # 付费抽奖：增加计数（异步）
            increment_success = await DrawLimiter.increment_paid_draw(guild_id, discord_user_id, MAX_PAID_DRAWS_PER_DAY)
            if not increment_success:
                await ctx.send(f"❌ 第 {i+1} 次抽奖失败：已达到每日付费抽奖上限")
                break

            # 扣除积分
            try:
                await UserCache.update_points(guild_id, discord_user_id, user_id, -WHEEL_COST)
            except Exception as e:
                # 扣除积分失败，回滚计数（异步）
                from src.db.redis_client import redis_client
                today_str = now_est().date()
                paid_key = f'draw:paid:{guild_id}:{discord_user_id}:{today_str}'
                await redis_client.decr(paid_key)
                await ctx.send(f"第 {i+1} 次抽奖扣除积分时出错：{str(e)}")
                break

        # 获取奖励
        reward = get_weighted_reward()
        rewards.append(reward)
        total_points += reward["points"]

        # 增加奖励积分
        try:
            await UserCache.update_points(guild_id, discord_user_id, user_id, reward["points"])
        except Exception as e:
            await ctx.send(f"第 {i+1} 次抽奖更新积分时出错：{str(e)}")
            break

    # 更新数据库
    try:
        if first_draw:
            # 标记免费抽奖已使用（异步）
            await DrawLimiter.mark_free_draw_used(guild_id, discord_user_id)

        # 更新数据库记录
        paid_draws_today = await DrawLimiter.get_paid_draw_count(guild_id, discord_user_id)
        supabase.table('users').update({
            'last_draw_date': str(today),
            'paid_draws_today': paid_draws_today,
            'last_paid_draw_date': str(today)
        }).eq('id', user_id).execute()
    except Exception as e:
        await ctx.send(f"更新用户数据时出错：{str(e)}")

    # 显示结果
    if len(rewards) == 1:
        # 单次抽奖，显示详细结果
        reward = rewards[0]
        embed = discord.Embed(
            title=f"{reward['emoji']} 抽奖结果",
            description=f"**{reward['message']}**\n获得 **{reward['points']}** 分！",
            color=discord.Color.gold() if reward['points'] >= 300 else discord.Color.blue() if reward['points'] >= 100 else discord.Color.green()
        )

        # 为高价值奖励添加特殊效果
        if reward['points'] >= 1000:
            embed.description += "\n\n🏆 **恭喜你抽中了终极大奖！** 🏆"
            embed.color = discord.Color.purple()
        elif reward['points'] >= 777:
            embed.description += "\n\n🎉 **恭喜你抽中了幸运之神奖！** 🎉"
            embed.color = discord.Color.purple()
        elif reward['points'] >= 666:
            embed.description += "\n\n😈 **哇！你抽中了恶魔奖励！** 😈"
            embed.color = discord.Color.dark_red()
        elif reward['points'] >= 500:
            embed.description += "\n\n🔥 **太棒了！你抽中了超级大奖！** 🔥"
            embed.color = discord.Color.orange()
        elif reward['points'] >= 250:
            embed.description += "\n\n⭐ **哇！你抽中了稀有奖励！** ⭐"
            embed.color = discord.Color.gold()
    else:
        # 多次抽奖，显示汇总结果
        # 统计各奖励的数量
        reward_count = {}
        for reward in rewards:
            key = f"{reward['emoji']} {reward['message']}"
            if key not in reward_count:
                reward_count[key] = {'count': 0, 'points': reward['points']}
            reward_count[key]['count'] += 1

        # 构建结果描述
        result_lines = []
        for key, data in sorted(reward_count.items(), key=lambda x: x[1]['points'], reverse=True):
            result_lines.append(f"{key} x{data['count']} (每个{data['points']}分)")

        embed = discord.Embed(
            title=f"🎰 {len(rewards)}连抽结果",
            description="\n".join(result_lines) + f"\n\n**总计获得: {total_points} 分**",
            color=discord.Color.gold()
        )

        # 检查是否有高价值奖励
        max_reward = max(rewards, key=lambda x: x['points'])
        if max_reward['points'] >= 500:
            embed.description += f"\n\n🎉 **最高奖励: {max_reward['emoji']} {max_reward['message']} ({max_reward['points']}分)**"

    await ctx.send(embed=embed)
