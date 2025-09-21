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

def get_user_internal_id(interaction):
    """获取用户在数据库中的内部ID"""
    supabase = get_connection()
    
    try:
        # 确保参数是整数类型，匹配数据库的bigint字段
        guild_id_int = int(interaction.guild.id)
        discord_user_id_int = int(interaction.user.id)
        
        user_result = supabase.table("users").select("id").eq("guild_id", guild_id_int).eq("discord_user_id", discord_user_id_int).execute()
        
        if user_result.data:
            return user_result.data[0]["id"]
        else:
            return None
    except Exception as e:
        print(f"获取用户内部ID失败: {e}")
        return None

async def get_user_data_with_validation(interaction, fields="id", ephemeral=True):
    """
    获取用户数据并验证用户是否存在
    
    Args:
        interaction: Discord交互对象
        fields: 要获取的字段，可以是字符串或逗号分隔的字符串
        ephemeral: 错误消息是否为私密消息
    
    Returns:
        tuple: (user_data, success) - 如果成功返回(user_data, True)，失败返回(None, False)
    """
    supabase = get_connection()
    discord_user_id = interaction.user.id
    guild_id = str(interaction.guild.id)
    
    try:
        user_response = supabase.table("users").select(fields).eq("discord_user_id", discord_user_id).eq("guild_id", guild_id).execute()
        
        if not user_response.data:
            await interaction.response.send_message("你还没有注册，请先使用其他功能来创建账户！", ephemeral=ephemeral)
            return None, False
            
        user_data = user_response.data[0]
        return user_data, True
        
    except Exception as e:
        print(f"获取用户数据失败: {e}")
        await interaction.response.send_message("系统错误，请稍后再试！", ephemeral=ephemeral)
        return None, False

def get_user_data_sync(interaction, fields="id"):
    """
    同步获取用户数据，不发送响应消息
    
    Args:
        interaction: Discord交互对象
        fields: 要获取的字段，可以是字符串或逗号分隔的字符串
    
    Returns:
        tuple: (user_data, success, error_msg) - 成功返回(user_data, True, None)，失败返回(None, False, error_msg)
    """
    supabase = get_connection()
    discord_user_id = interaction.user.id
    guild_id = str(interaction.guild.id)
    
    try:
        user_response = supabase.table("users").select(fields).eq("discord_user_id", discord_user_id).eq("guild_id", guild_id).execute()
        
        if not user_response.data:
            return None, False, "你还没有注册，请先使用其他功能来创建账户！"
            
        user_data = user_response.data[0]
        return user_data, True, None
        
    except Exception as e:
        print(f"获取用户数据失败: {e}")
        return None, False, "系统错误，请稍后再试！"

async def get_user_id_with_validation_ctx(ctx, target_user=None):
    """
    通过ctx获取用户ID并验证用户存在性
    
    Args:
        ctx: Discord命令上下文
        target_user: 目标用户，如果为None则使用ctx.author
    
    Returns:
        tuple: (user_id, success) - 用户ID和是否成功
    """
    try:
        from src.db.database import get_connection
        supabase = get_connection()
        
        user = target_user if target_user else ctx.author
        discord_user_id = user.id
        guild_id = ctx.guild.id
        
        # 查询用户ID
        user_response = supabase.table('users').select('id').eq('discord_user_id', discord_user_id).eq('guild_id', guild_id).execute()
        
        if not user_response.data:
            await ctx.send(f"用户 {user.mention} 还没有注册，请先使用抽奖功能。")
            return None, False
        
        user_id = user_response.data[0]['id']
        return user_id, True
        
    except Exception as e:
        await ctx.send(f"获取用户信息时出错：{str(e)}")
        return None, False