# DailyDrawBot
🎲 A Discord bot for daily lucky draws and point tracking.

## Features
- Daily draw system with points
- Role shop and gifting
- `!ranking` now returns an image leaderboard with avatars

=======
=======
Set the Discord bot token using an environment variable named `TOKEN` before
running the bot. If you deploy on Railway, add `TOKEN` to your service's
environment variables and Railway will pass it to the process automatically.
When running locally you can export the variable first, e.g.:

```bash
export TOKEN="YOUR_DISCORD_TOKEN"
python bot.py
```
