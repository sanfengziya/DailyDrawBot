# DailyDrawBot
🎲 A Discord bot for daily lucky draws and point tracking.

## Features
- Daily draw system with points
- Role shop and gifting
- Timed quiz system with `!quiz`, `!importquiz` and `!quizlist`
- `!ranking` now returns an image leaderboard with avatars

Set the Discord bot token using an environment variable named `TOKEN` before
running the bot. If you deploy on Railway, add `TOKEN` to your service's
environment variables and Railway will pass it to the process automatically.
When running locally you can export the variable first, e.g.:

```bash
export TOKEN="YOUR_DISCORD_TOKEN"
python bot.py
```

### Quiz question format
Provide a text file where each line represents a question. Fields are separated by a vertical bar `|` in the following order:

```
category|question|optionA|optionB|optionC|optionD|answer
```

The `answer` field should be the letter `A`, `B`, `C` or `D` indicating the correct option.

Use `!quiz <category> <number>` to start a timed quiz. Questions appear one at a time with 60 seconds to answer. The first user to answer correctly earns 10 points.
