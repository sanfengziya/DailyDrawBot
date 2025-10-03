"""
排行榜管理器
使用Redis Sorted Set实现高性能排行榜
"""
from src.db.redis_client import redis_client
from src.db.database import get_connection
import logging

logger = logging.getLogger(__name__)


class RankingManager:
    """排行榜管理器"""

    @staticmethod
    async def initialize_ranking(guild_id: int):
        """
        初始化排行榜(从数据库加载)

        Args:
            guild_id: 服务器ID
        """
        try:
            supabase = get_connection()
            result = supabase.table('users').select('discord_user_id, points').eq('guild_id', guild_id).execute()

            ranking_key = f'ranking:{guild_id}'

            # 批量写入Sorted Set
            if result.data:
                mapping = {str(row['discord_user_id']): row['points'] for row in result.data}
                redis_client.zadd(ranking_key, mapping)
                logger.info(f"初始化排行榜成功: guild_id={guild_id}, 用户数={len(mapping)}")
                return True
            return False
        except Exception as e:
            logger.error(f"初始化排行榜失败: {e}")
            return False

    @staticmethod
    def get_top_rankings(guild_id: int, limit: int = 10) -> list:
        """
        获取Top N排行榜

        Args:
            guild_id: 服务器ID
            limit: 返回前N名

        Returns:
            [(discord_user_id, points), ...] 排行榜列表
        """
        try:
            ranking_key = f'ranking:{guild_id}'

            # ZREVRANGE: 按分数从高到低
            rankings = redis_client.zrevrange(ranking_key, 0, limit - 1, withscores=True)

            # 返回: [(discord_user_id, points), ...]
            return [(int(user_id), int(score)) for user_id, score in rankings]
        except Exception as e:
            logger.error(f"获取排行榜失败: {e}")
            return []

    @staticmethod
    def get_user_rank(guild_id: int, discord_user_id: int) -> int:
        """
        获取用户排名(1-based)

        Args:
            guild_id: 服务器ID
            discord_user_id: Discord用户ID

        Returns:
            用户排名,如果不在榜单返回-1
        """
        try:
            ranking_key = f'ranking:{guild_id}'

            # ZREVRANK: 获取排名(0-based)
            rank = redis_client.zrevrank(ranking_key, str(discord_user_id))

            return rank + 1 if rank is not None else -1  # 不在榜单返回-1
        except Exception as e:
            logger.error(f"获取用户排名失败: {e}")
            return -1

    @staticmethod
    def update_user_score(guild_id: int, discord_user_id: int, points: int):
        """
        更新用户积分到排行榜

        Args:
            guild_id: 服务器ID
            discord_user_id: Discord用户ID
            points: 新的积分值
        """
        try:
            ranking_key = f'ranking:{guild_id}'
            redis_client.zadd(ranking_key, {str(discord_user_id): points})
        except Exception as e:
            logger.error(f"更新排行榜失败: {e}")

    @staticmethod
    def get_user_score(guild_id: int, discord_user_id: int) -> int:
        """
        从排行榜获取用户积分

        Args:
            guild_id: 服务器ID
            discord_user_id: Discord用户ID

        Returns:
            用户积分,如果不存在返回0
        """
        try:
            ranking_key = f'ranking:{guild_id}'
            score = redis_client.zscore(ranking_key, str(discord_user_id))
            return int(score) if score is not None else 0
        except Exception as e:
            logger.error(f"获取排行榜积分失败: {e}")
            return 0
