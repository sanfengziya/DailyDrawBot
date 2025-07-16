import os
from urllib.parse import urlparse
from dotenv import load_dotenv

# 加载.env文件
load_dotenv()

# Bot配置
TOKEN = os.getenv("TOKEN")
if TOKEN is None:
    raise RuntimeError("TOKEN environment variable not set")
    
YOUR_GUILD_ID = int(os.getenv("YOUR_GUILD_ID", "0"))
if YOUR_GUILD_ID == 0:
    raise RuntimeError("YOUR_GUILD_ID environment variable not set")
PREFIX = os.getenv("PREFIX", "!")

# 抽奖配置
WHEEL_COST = int(os.getenv("WHEEL_COST", "100"))
MAX_PAID_DRAWS_PER_DAY = int(os.getenv("MAX_PAID_DRAWS_PER_DAY", "10"))

# 数据库配置
MYSQL_URL = os.getenv("MYSQL_URL")
if MYSQL_URL is None:
    raise RuntimeError("MYSQL_URL environment variable not set")
url = urlparse(MYSQL_URL)
DB_CONFIG = {
    "host": url.hostname,
    "port": url.port,
    "user": url.username,
    "password": url.password,
    "database": url.path[1:],
}

# 优化的抽奖奖励系统
REWARD_SYSTEM = [
    {"points": 10, "probability": 22.0, "message": "小小心意", "emoji": "🍬"},
    {"points": 20, "probability": 17.0, "message": "普通奖励", "emoji": "🎁"},
    {"points": 75, "probability": 13.0, "message": "不错哦", "emoji": "🎯"},
    {"points": 100, "probability": 12.0, "message": "运气不错", "emoji": "🎪"},
    {"points": 125, "probability": 5.0, "message": "有点开心", "emoji": "🎨"},
    {"points": 175, "probability": 4.5, "message": "较稀有", "emoji": "🌟"},
    {"points": 200, "probability": 4.0, "message": "稀有奖励", "emoji": "💫"},
    {"points": 250, "probability": 3.5, "message": "传说级运气", "emoji": "👑"},
    {"points": 300, "probability": 2.5, "message": "极低概率大奖", "emoji": "🔥"},
    {"points": 500, "probability": 2.0, "message": "超级大奖", "emoji": "💎"},
    {"points": 666, "probability": 1.5, "message": "恶魔奖励", "emoji": "😈"},
    {"points": 777, "probability": 0.9, "message": "幸运之神奖", "emoji": "✨"},
    {"points": 1000, "probability": 0.1, "message": "终极大奖", "emoji": "🏆"},
] 