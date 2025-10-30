import os
from dotenv import load_dotenv

# 加载.env文件
load_dotenv(".env.local")

# Bot配置
TOKEN = os.getenv("TOKEN")
if TOKEN is None:
    raise RuntimeError("TOKEN environment variable not set")
    
PREFIX = os.getenv("PREFIX", "!")

# 抽奖配置
DRAW_COST = 100  # 每次抽奖的费用
MAX_PAID_DRAWS_PER_DAY = 30 # 每天允许的最大付费抽奖次数

# 多语言配置
DEFAULT_LOCALE = os.getenv("DEFAULT_LOCALE", "en-US")
# Supabase数据库配置
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if SUPABASE_KEY is None:
    raise RuntimeError("SUPABASE_KEY environment variable not set")

# 数据库配置（保持向后兼容）
DB_CONFIG = {
    "url": SUPABASE_URL,
    "key": SUPABASE_KEY,
}

# 优化的抽奖奖励系统
REWARD_SYSTEM = [
    {"points": 10, "probability": 22.0, "message": "小小心意", "message_key": "rewards.small_gift", "emoji": "🍬"},
    {"points": 20, "probability": 17.0, "message": "普通奖励", "message_key": "rewards.regular_reward", "emoji": "🎁"},
    {"points": 75, "probability": 15.0, "message": "不错哦", "message_key": "rewards.nice_reward", "emoji": "🎯"},
    {"points": 100, "probability": 20.0, "message": "运气不错", "message_key": "rewards.good_luck", "emoji": "🎪"},
    {"points": 125, "probability": 7.0, "message": "有点开心", "message_key": "rewards.happy", "emoji": "🎨"},
    {"points": 175, "probability": 4.5, "message": "较稀有", "message_key": "rewards.rare", "emoji": "🌟"},
    {"points": 200, "probability": 4.0, "message": "稀有奖励", "message_key": "rewards.very_rare", "emoji": "💫"},
    {"points": 250, "probability": 3.5, "message": "传说级运气", "message_key": "rewards.legendary", "emoji": "👑"},
    {"points": 300, "probability": 2.5, "message": "极低概率大奖", "message_key": "rewards.ultimate", "emoji": "🔥"},
    {"points": 500, "probability": 2.0, "message": "超级大奖", "message_key": "rewards.super", "emoji": "💎"},
    {"points": 666, "probability": 1.5, "message": "恶魔奖励", "message_key": "rewards.devil", "emoji": "😈"},
    {"points": 777, "probability": 0.9, "message": "幸运之神奖", "message_key": "rewards.lucky", "emoji": "✨"},
    {"points": 1000, "probability": 0.1, "message": "终极大奖", "message_key": "rewards.final", "emoji": "🏆"},
]
