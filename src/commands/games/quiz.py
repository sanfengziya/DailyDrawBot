import discord
import asyncio
import random
import datetime
from src.db.database import get_connection
from src.utils.helpers import get_user_internal_id_with_guild_and_discord_id
from src.utils.cache import UserCache
from src.utils.i18n import get_guild_locale, t

async def quizlist(ctx, language: str = "all"):
    supabase = get_connection()
    locale = get_guild_locale(ctx.guild.id if ctx.guild else None)

    language_key = language.lower()
    valid_languages = {"all", "chinese", "english"}

    try:
        # 根据语言参数筛选
        if language_key == "all":
            result = supabase.table("quiz_questions").select("category, language").execute()
        elif language_key in valid_languages:
            result = (
                supabase
                .table("quiz_questions")
                .select("category, language")
                .eq("language", language_key)
                .execute()
            )
        else:
            options = ", ".join(sorted(valid_languages))
            await ctx.send(t("quiz.list.invalid_language", locale=locale, options=options))
            return

        if not result.data:
            await ctx.send(t("quiz.list.no_data", locale=locale))
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
        message_parts = [t("quiz.list.header", locale=locale)]

        if language_key in ["all", "chinese"] and chinese_categories:
            message_parts.append(
                t(
                    "quiz.list.section_chinese",
                    locale=locale,
                    categories=", ".join(sorted(chinese_categories))
                )
            )

        if language_key in ["all", "english"] and english_categories:
            message_parts.append(
                t(
                    "quiz.list.section_english",
                    locale=locale,
                    categories=", ".join(sorted(english_categories))
                )
            )

        if len(message_parts) == 1:
            language_label = t(
                f"quiz.list.language_label.{language_key}",
                locale=locale,
                default=language_key
            )
            await ctx.send(t("quiz.list.none_for_language", locale=locale, language=language_label))
        else:
            await ctx.send("\n".join(message_parts))

    except Exception as e:
        print(f"获取题库类别失败: {e}")
        await ctx.send(t("quiz.list.error", locale=locale))

async def quiz(ctx, category, number):
    supabase = get_connection()
    locale = get_guild_locale(ctx.guild.id if ctx.guild else None)

    try:
        # 先尝试完全匹配
        result = supabase.table("quiz_questions").select("question, option_a, option_b, option_c, option_d, answer, category").eq("category", category).execute()

        # 如果没有完全匹配，尝试模糊匹配（category:xxx）
        if not result.data:
            result = supabase.table("quiz_questions").select("question, option_a, option_b, option_c, option_d, answer, category").like("category", f"{category}:%").execute()

            if result.data:
                # 获取所有匹配的子类别
                matched_categories = list(set([row["category"] for row in result.data]))
                await ctx.send(t("quiz.match.found", locale=locale, categories=", ".join(matched_categories)))

        rows = [(row["question"], row["option_a"], row["option_b"], row["option_c"], row["option_d"], row["answer"]) for row in result.data]

        if not rows:
            await ctx.send(t("quiz.match.none", locale=locale, category=category))
            return
            
    except Exception as e:
        print(f"获取题目失败: {e}")
        await ctx.send(t("quiz.match.error", locale=locale))
        return

    random.shuffle(rows)
    if number > len(rows):
        number = len(rows)
    rows = rows[:number]

    for idx, (q, o1, o2, o3, o4, ans) in enumerate(rows, 1):
        await ctx.send(
            t(
                "quiz.game.question",
                locale=locale,
                index=idx,
                total=len(rows),
                question=q,
                a=o1,
                b=o2,
                c=o3,
                d=o4
            )
        )

        start = asyncio.get_event_loop().time()
        answered = False
        attempted_users = set()

        async def warn_after_delay():
            await asyncio.sleep(50)
            if not answered:
                await ctx.send(t("quiz.game.warning", locale=locale))

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
                await ctx.send(
                    t(
                        "quiz.game.correct",
                        locale=locale,
                        mention=reply.author.mention,
                        answer=ans
                    )
                )

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
                    await UserCache.update_points(ctx.guild.id, reply.author.id, user_internal_id, 20)

                except Exception as e:
                    print(f"奖励积分失败: {e}")
                    
                answered = True
                break
            else:
                await ctx.send(
                    t(
                        "quiz.game.wrong",
                        locale=locale,
                        mention=reply.author.mention
                    )
                )

        if not warning_task.done():
            warning_task.cancel()

        if not answered:
            await ctx.send(t("quiz.game.timeout", locale=locale, answer=ans))

    await ctx.send(t("quiz.game.end", locale=locale))
