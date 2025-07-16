import datetime
import pytz
import random
from src.config.config import REWARD_SYSTEM

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