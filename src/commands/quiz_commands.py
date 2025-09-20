import discord
import asyncio
import random
from src.db.database import get_connection

async def quizlist(ctx):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT DISTINCT category FROM quiz_questions")
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    if rows:
        await ctx.send("📋 题库类别：" + ", ".join(rows))
    else:
        await ctx.send("暂无题库。")

async def importquiz(ctx):
    if not ctx.message.attachments:
        await ctx.send("请附加题库文件。")
        return

    attachment = ctx.message.attachments[0]
    data = await attachment.read()
    lines = data.decode("utf-8").splitlines()

    conn = get_connection()
    c = conn.cursor()
    count = 0
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
        c.execute(
            "INSERT INTO quiz_questions (category, question, option1, option2, option3, option4, answer) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (category, question, o1, o2, o3, o4, ans_idx),
        )
        count += 1
    conn.commit()
    conn.close()
    await ctx.send(f"✅ 已导入 {count} 道题目。")

async def deletequiz(ctx, category):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, question FROM quiz_questions WHERE category = %s", (category,))
    rows = c.fetchall()
    if not rows:
        conn.close()
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
        conn.close()
        return

    if reply.content.strip().lower() == "取消":
        await ctx.send("已取消。")
        conn.close()
        return

    try:
        numbers = [int(n) for n in reply.content.strip().split()]
    except ValueError:
        await ctx.send("输入格式错误。")
        conn.close()
        return

    ids = []
    for num in numbers:
        if 1 <= num <= len(rows):
            ids.append(rows[num - 1][0])

    if not ids:
        await ctx.send("没有有效的题号可删除。")
        conn.close()
        return

    format_strings = ",".join(["%s"] * len(ids))
    c.execute(f"DELETE FROM quiz_questions WHERE id IN ({format_strings})", ids)
    conn.commit()
    conn.close()
    await ctx.send(f"已删除 {len(ids)} 道题目。")

async def quiz(ctx, category, number):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT question, option1, option2, option3, option4, answer FROM quiz_questions WHERE category = %s",
        (category,),
    )
    rows = c.fetchall()
    conn.close()

    if not rows:
        await ctx.send("该类别没有题目。")
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
                conn = get_connection()
                c = conn.cursor()
                c.execute(
                    "INSERT INTO users (user_id, points, last_draw) VALUES (%s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE points = points + VALUES(points)",
                    (str(reply.author.id), 10, "1970-01-01"),
                )
                conn.commit()
                conn.close()
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