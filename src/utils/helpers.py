import datetime
import pytz
import random
from src.config.config import REWARD_SYSTEM
from src.db.database import get_connection

# 转换 UTC 到 UTC-4 时间
def now_est():
    utc_now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
    est = pytz.timezone("Etc/GMT+4")
    return utc_now.astimezone(est)

def get_weighted_reward():
    """根据加权概率获取随机奖励"""
    # 创建一个列表，其中每个奖励根据其概率出现
    reward_pool = []
    for reward in REWARD_SYSTEM:
        # 将百分比转换为条目数量（乘以10以提高精度）
        count = int(reward["probability"] * 10)
        for _ in range(count):
            reward_pool.append(reward)
    
    # 从池中随机选择
    return random.choice(reward_pool)

def get_user_internal_id(guild_id, discord_user_id):
    """获取用户在数据库中的内部ID"""
    supabase = get_connection()
    
    try:
        # 确保参数是整数类型，匹配数据库的bigint字段
        guild_id_int = int(guild_id)
        discord_user_id_int = int(discord_user_id)
        
        user_result = supabase.table("users").select("id").eq("guild_id", guild_id_int).eq("discord_user_id", discord_user_id_int).execute()
        
        if user_result.data:
            return user_result.data[0]["id"]
        else:
            return None
    except Exception as e:
        print(f"获取用户内部ID失败: {e}")
        return None

def get_guild_language(guild_id):
    """获取服务器的语言设置，如果没有则返回默认语言（英文）"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT language FROM guild_settings WHERE guild_id = %s",
        (guild_id,)
    )
    result = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    # 如果没有设置，返回默认语言（英文）
    if not result:
        return "en"
    
    return result[0]