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
    """Get a random reward based on weighted probabilities"""
    # Create a list where each reward appears according to its probability
    reward_pool = []
    for reward in REWARD_SYSTEM:
        # Convert percentage to number of entries (multiply by 10 for precision)
        count = int(reward["probability"] * 10)
        for _ in range(count):
            reward_pool.append(reward)
    
    # Randomly select from the pool
    return random.choice(reward_pool) 