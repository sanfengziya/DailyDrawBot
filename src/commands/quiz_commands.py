import discord
import asyncio
import random
import datetime
from src.db.database import get_connection
from src.utils.helpers import get_user_internal_id_with_guild_and_discord_id
from src.utils.cache import UserCache

async def quizlist(ctx, language: str = "all"):
    supabase = get_connection()

    try:
        # 根据语言参数筛选
        if language.lower() == "all":
            result = supabase.table("quiz_questions").select("category, language").execute()
        elif language.lower() in ["chinese", "english"]:
            result = supabase.table("quiz_questions").select("category, language").eq("language", language.lower()).execute()
        else:
            await ctx.send("❌ 无效的语言参数！请使用：`chinese`、`english` 或 `all`")
            return

        if not result.data:
            await ctx.send("暂无题库。")
            return

        # 按语言分组类别
        chinese_categories = set()
        english_categories = set()

        for row in result.data:
            if row["language"] == "chinese":
                chinese_categories.add(row["category"])
            else:
                english_categories.add(row["category"])

        # 构建消息
        message_parts = ["📋 **题库类别**\n"]

        if language.lower() in ["all", "chinese"] and chinese_categories:
            message_parts.append(f"🇨🇳 **中文题库：**\n{', '.join(sorted(chinese_categories))}\n")

        if language.lower() in ["all", "english"] and english_categories:
            message_parts.append(f"🇺🇸 **英文题库：**\n{', '.join(sorted(english_categories))}")

        if len(message_parts) == 1:
            await ctx.send(f"暂无 {language} 题库。")
        else:
            await ctx.send("\n".join(message_parts))

    except Exception as e:
        print(f"获取题库类别失败: {e}")
        await ctx.send("获取题库类别失败，请稍后重试。")

async def quiz(ctx, category, number):
    supabase = get_connection()
    
    try:
        result = supabase.table("quiz_questions").select("question, option_a, option_b, option_c, option_d, answer").eq("category", category).execute()
        rows = [(row["question"], row["option_a"], row["option_b"], row["option_c"], row["option_d"], row["answer"]) for row in result.data]

        if not rows:
            await ctx.send("该类别没有题目。")
            return
            
    except Exception as e:
        print(f"获取题目失败: {e}")
        await ctx.send("获取题目失败，请稍后重试。")
        return

    random.shuffle(rows)
    if number > len(rows):
        number = len(rows)
    rows = rows[:number]

    for q, o1, o2, o3, o4, ans in rows:
        await ctx.send(f"**{q}**\nA. {o1}\nB. {o2}\nC. {o3}\nD. {o4}")
        await ctx.send("🎮 游戏开始，你只有 60 秒的时间作答！")

        start = asyncio.get_event_loop().time()
        answered = False
        attempted_users = set()

        async def warn_after_delay():
            await asyncio.sleep(50)
            if not answered:
                await ctx.send("⏰ 仅剩下 10 秒！")

        warning_task = asyncio.create_task(warn_after_delay())

        while True:
            remaining = 60 - (asyncio.get_event_loop().time() - start)
            if remaining <= 0:
                break

            def check(m):
                return (
                    not m.author.bot
                    and m.channel == ctx.channel
                    and m.content.upper() in ["A", "B", "C", "D", "1", "2", "3", "4"]
                    and str(m.author.id) not in attempted_users
                )

            try:
                reply = await ctx.bot.wait_for("message", check=check, timeout=remaining)
            except asyncio.TimeoutError:
                break

            attempted_users.add(str(reply.author.id))
            txt = reply.content.upper()
            if txt in ["1", "2", "3", "4"]:
                choice_letter = ["A", "B", "C", "D"][int(txt) - 1]
            else:
                choice_letter = txt

            if choice_letter == ans:
                await ctx.send(f"✅ {reply.author.mention} 答对了！正确答案是 {ans}，奖励 10 分")

                try:
                    supabase = get_connection()

                    # 获取用户内部ID
                    user_internal_id = get_user_internal_id_with_guild_and_discord_id(ctx.guild.id, reply.author.id)

                    # 如果用户不存在，自动创建
                    if not user_internal_id:
                        create_response = supabase.table('users').insert({
                            'guild_id': ctx.guild.id,
                            'discord_user_id': reply.author.id,
                            'points': 0,
                            'last_draw_date': None,
                            'paid_draws_today': 0,
                            'last_paid_draw_date': '1970-01-01',
                            'equipped_pet_id': None,
                            'last_pet_points_update': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
                        }).execute()
                        user_internal_id = create_response.data[0]['id']

                    # 使用UserCache更新积分（与draw系统保持一致）
                    await UserCache.update_points(ctx.guild.id, reply.author.id, user_internal_id, 10)

                except Exception as e:
                    print(f"奖励积分失败: {e}")
                    
                answered = True
                break
            else:
                await ctx.send(f"❌ {reply.author.mention} 答错了！你已经没有再答的机会啦")

        if not warning_task.done():
            warning_task.cancel()

        if not answered:
            await ctx.send(f"⏰ 时间到，正确答案是 {ans}")

    await ctx.send("答题结束！")
