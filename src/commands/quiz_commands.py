import discord
import asyncio
import random
from src.db.database import get_connection
from src.utils.helpers import get_user_internal_id_with_guild_and_discord_id

async def quizlist(ctx):
    supabase = get_connection()
    
    try:
        result = supabase.table("quiz_questions").select("category").execute()
        categories = list(set([row["category"] for row in result.data]))
        
        if categories:
            await ctx.send("📋 题库类别：" + ", ".join(categories))
        else:
            await ctx.send("暂无题库。")
            
    except Exception as e:
        print(f"获取题库类别失败: {e}")
        await ctx.send("获取题库类别失败，请稍后重试。")

async def importquiz(ctx):
    if not ctx.message.attachments:
        await ctx.send("请附加题库文件。")
        return

    attachment = ctx.message.attachments[0]
    data = await attachment.read()
    lines = data.decode("utf-8").splitlines()

    supabase = get_connection()
    count = 0
    questions_to_insert = []
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 7:
            continue
        category, question, o1, o2, o3, o4, ans = parts
        ans = ans.upper()
        if ans not in ["A", "B", "C", "D"]:
            continue
        ans_idx = ["A", "B", "C", "D"].index(ans) + 1
        
        questions_to_insert.append({
            "category": category,
            "question": question,
            "option1": o1,
            "option2": o2,
            "option3": o3,
            "option4": o4,
            "answer": ans_idx
        })
        count += 1
    
    try:
        if questions_to_insert:
            supabase.table("quiz_questions").insert(questions_to_insert).execute()
        await ctx.send(f"✅ 已导入 {count} 道题目。")
        
    except Exception as e:
        print(f"导入题目失败: {e}")
        await ctx.send("导入题目失败，请稍后重试。")

async def deletequiz(ctx, category):
    supabase = get_connection()
    
    try:
        result = supabase.table("quiz_questions").select("id, question").eq("category", category).execute()
        rows = [(row["id"], row["question"]) for row in result.data]
        
        if not rows:
            await ctx.send("该类别没有题目。")
            return

        msg_lines = [f"{i + 1}. {q}" for i, (qid, q) in enumerate(rows)]
        await ctx.send("**题目列表：**\n" + "\n".join(msg_lines))
        await ctx.send("请输入要删除的题号，以空格分隔，或输入 `取消` 终止。")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            reply = await ctx.bot.wait_for("message", check=check, timeout=300.0)
        except asyncio.TimeoutError:
            await ctx.send("操作超时，已取消。")
            return

        if reply.content.strip().lower() == "取消":
            await ctx.send("已取消。")
            return

        try:
            numbers = [int(n) for n in reply.content.strip().split()]
        except ValueError:
            await ctx.send("输入格式错误。")
            return

        ids = []
        for num in numbers:
            if 1 <= num <= len(rows):
                ids.append(rows[num - 1][0])

        if not ids:
            await ctx.send("没有有效的题号可删除。")
            return

        # 删除选中的题目
        for question_id in ids:
            supabase.table("quiz_questions").delete().eq("id", question_id).execute()
            
        await ctx.send(f"已删除 {len(ids)} 道题目。")
        
    except Exception as e:
        print(f"删除题目失败: {e}")
        await ctx.send("删除题目失败，请稍后重试。")

async def quiz(ctx, category, number):
    supabase = get_connection()
    
    try:
        result = supabase.table("quiz_questions").select("question, option1, option2, option3, option4, answer").eq("category", category).execute()
        rows = [(row["question"], row["option1"], row["option2"], row["option3"], row["option4"], row["answer"]) for row in result.data]

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
                choice = int(txt)
            else:
                choice = ["A", "B", "C", "D"].index(txt) + 1

            if choice == ans:
                letter = ["A", "B", "C", "D"][ans - 1]
                await ctx.send(f"✅ {reply.author.mention} 答对了！正确答案是 {letter}，奖励 10 分")
                
                try:
                    # 获取用户内部ID
                    user_internal_id = get_user_internal_id_with_guild_and_discord_id(ctx.guild.id, reply.author.id)
                    if not user_internal_id:
                        print(f"获取用户内部ID失败: {reply.author.id}")
                        continue
                        
                    # 获取用户当前积分
                    user_result = supabase.table("users").select("points").eq("id", user_internal_id).execute()
                    
                    if user_result.data:
                        # 用户存在，更新积分
                        current_points = user_result.data[0]["points"]
                        supabase.table("users").update({
                            "points": current_points + 10
                        }).eq("id", user_internal_id).execute()
                    else:
                        # 用户不存在，创建新记录
                        supabase.table("users").insert({
                            "guild_id": ctx.guild.id,
                            "discord_user_id": reply.author.id,
                            "points": 10,
                            "last_draw_date": "1970-01-01",
                            "paid_draws_today": 0,
                            "last_paid_draw_date": "1970-01-01"
                        }).execute()
                        
                except Exception as e:
                    print(f"奖励积分失败: {e}")
                    
                answered = True
                break
            else:
                await ctx.send(f"❌ {reply.author.mention} 答错了！你已经没有再答的机会啦")

        if not warning_task.done():
            warning_task.cancel()

        if not answered:
            letter = ["A", "B", "C", "D"][ans - 1]
            await ctx.send(f"⏰ 时间到，正确答案是 {letter}")

    await ctx.send("答题结束！")
