"""
缓存工具类
提供用户积分和ID映射的缓存功能
"""
import asyncio
import logging
from typing import Optional

from src.db.redis_client import redis_client
from src.db.database import get_connection

logger = logging.getLogger(__name__)


class UserCache:
    """用户数据缓存层"""

    # 标记Supabase是否支持atomic_update_points RPC,避免反复失败日志
    _rpc_supported: Optional[bool] = None

    @staticmethod
    async def get_user_id(guild_id: int, discord_user_id: int) -> int:
        """
        获取用户内部ID(带缓存)

        Args:
            guild_id: 服务器ID
            discord_user_id: Discord用户ID

        Returns:
            用户内部ID,如果不存在返回None
        """
        cache_key = f'user:id:{guild_id}:{discord_user_id}'

        try:
            # 1. 尝试从Redis获取（异步）
            cached_id = await redis_client.get(cache_key)
            if cached_id is not None:
                return int(cached_id)
        except Exception as e:
            logger.warning(f"Redis查询失败,降级到数据库: {e}")

        # 2. 缓存未命中,查询数据库
        supabase = get_connection()
        result = supabase.table('users').select('id').eq('guild_id', guild_id).eq('discord_user_id', discord_user_id).execute()

        if not result.data:
            return None

        user_id = result.data[0]['id']

        # 3. 写入缓存(24小时有效)
        try:
            await redis_client.setex(cache_key, 86400, user_id)
        except Exception as e:
            logger.error(f"Redis写入失败: {e}")

        return user_id

    @staticmethod
    async def get_points(guild_id: int, discord_user_id: int) -> int:
        """
        获取用户积分(带缓存)

        Args:
            guild_id: 服务器ID
            discord_user_id: Discord用户ID

        Returns:
            用户积分,如果用户不存在返回0
        """
        cache_key = f'user:points:{guild_id}:{discord_user_id}'

        try:
            # 1. 尝试从Redis获取（异步）
            cached_points = await redis_client.get(cache_key)
            if cached_points is not None:
                return int(cached_points)
        except Exception as e:
            logger.warning(f"Redis查询失败,降级到数据库: {e}")

        # 2. 缓存未命中,查询数据库
        supabase = get_connection()
        result = supabase.table('users').select('points').eq('guild_id', guild_id).eq('discord_user_id', discord_user_id).execute()

        if not result.data:
            return 0

        points = result.data[0]['points']

        # 3. 写入缓存(1小时有效)
        try:
            await redis_client.setex(cache_key, 3600, points)
        except Exception as e:
            logger.error(f"Redis写入失败: {e}")

        return points

    @staticmethod
    async def update_points(guild_id: int, discord_user_id: int, user_id: int, delta: int) -> int:
        """
        更新用户积分(同步更新缓存和数据库)

        使用数据库原子操作避免并发问题

        Args:
            guild_id: 服务器ID
            discord_user_id: Discord用户ID
            user_id: 用户内部ID
            delta: 积分变化量(正数为增加,负数为减少)

        Returns:
            更新后的积分值
        """
        supabase = get_connection()

        new_points = None

        # 1. 尽量使用RPC完成原子更新
        if UserCache._rpc_supported is not False:
            try:
                rpc_result = supabase.rpc('atomic_update_points', {
                    'p_user_id': user_id,
                    'p_delta': delta
                }).execute()

                if rpc_result.data and len(rpc_result.data) > 0 and 'new_points' in rpc_result.data[0]:
                    new_points = rpc_result.data[0]['new_points']
                    UserCache._rpc_supported = True
                else:
                    raise ValueError(f"RPC调用返回空结果: user_id={user_id}")
            except Exception as rpc_error:
                if UserCache._rpc_supported is not False:
                    logger.warning(f"RPC调用失败,降级到CAS更新: {rpc_error}")
                UserCache._rpc_supported = False

        # 2. RPC不可用时,使用CAS重试避免并发丢失
        if new_points is None:
            max_attempts = 5
            for attempt in range(1, max_attempts + 1):
                result = supabase.table('users').select('points').eq('id', user_id).execute()

                if not result.data:
                    raise ValueError(f"用户不存在: user_id={user_id}")

                current_points = result.data[0]['points']
                candidate_points = max(0, current_points + delta)

                update_result = supabase.table('users').update({
                    'points': candidate_points
                }).eq('id', user_id).eq('points', current_points).execute()

                if update_result.data:
                    new_points = candidate_points
                    break

                if attempt == max_attempts:
                    raise ValueError(f"积分更新冲突过多,请稍后重试: user_id={user_id}")

                # 等待片刻再尝试,让其他事务完成
                await asyncio.sleep(0.05)

        # 2. 更新缓存（异步）
        cache_key = f'user:points:{guild_id}:{discord_user_id}'
        try:
            await redis_client.setex(cache_key, 3600, new_points)
        except Exception as e:
            logger.error(f"Redis更新失败: {e}")
            # 缓存失败不影响业务,记录日志即可

        # 3. 更新排行榜(如果已实现)
        try:
            ranking_key = f'ranking:{guild_id}'
            await redis_client.zadd(ranking_key, {str(discord_user_id): new_points})
        except Exception as e:
            logger.error(f"排行榜更新失败: {e}")

        return new_points

    @staticmethod
    async def invalidate_points_cache(guild_id: int, discord_user_id: int):
        """
        使积分缓存失效

        Args:
            guild_id: 服务器ID
            discord_user_id: Discord用户ID
        """
        cache_key = f'user:points:{guild_id}:{discord_user_id}'
        try:
            await redis_client.delete(cache_key)
        except Exception as e:
            logger.error(f"删除缓存失败: {e}")

    @staticmethod
    async def invalidate_user_id_cache(guild_id: int, discord_user_id: int):
        """
        使用户ID映射缓存失效

        Args:
            guild_id: 服务器ID
            discord_user_id: Discord用户ID
        """
        cache_key = f'user:id:{guild_id}:{discord_user_id}'
        try:
            await redis_client.delete(cache_key)
        except Exception as e:
            logger.error(f"删除缓存失败: {e}")
