# DailyDrawBot
🎲 A Discord bot for daily lucky draws and point tracking.

## Features
- Daily draw system with points
- Role shop and gifting
- Timed quiz system with `!quiz`, `!importquiz` and `!quizlist`
- `!ranking` now returns an image leaderboard with avatars

Set the Discord bot token using an environment variable named `TOKEN` before
running the bot. Database access now requires a MySQL connection string passed
via the `MYSQL_URL` environment variable. If you deploy on Railway, both
variables can be configured in your service's environment settings and will be
provided to the bot process automatically.
When running locally you can export the variable first, e.g.:

```bash
export TOKEN="YOUR_DISCORD_TOKEN"
export MYSQL_URL="mysql://user:pass@host:port/dbname"
python bot.py
```

### Quiz question format
Provide a text file where each line represents a question. Fields are separated by a vertical bar `|` in the following order:

```
category|question|optionA|optionB|optionC|optionD|answer
```

The `answer` field should be the letter `A`, `B`, `C` or `D` indicating the correct option.

Use `!quiz <category> <number>` to start a timed quiz. Questions appear one at a time with 60 seconds to answer. The first user to answer correctly earns 10 points.
