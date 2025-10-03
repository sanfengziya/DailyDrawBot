"""
抽奖限流控制器
使用Redis实现每日抽奖次数限制和自动重置
"""
from src.db.redis_client import redis_client
from src.utils.helpers import now_est, EASTERN_TZ
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class DrawLimiter:
    """抽奖限流控制器"""

    @staticmethod
    def get_ttl_to_midnight_est() -> int:
        """
        计算到美东时间次日0点的秒数

        Returns:
            到次日0点的秒数
        """
        now = datetime.now(EASTERN_TZ)

        # 次日0点
        tomorrow_midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # 返回秒数,至少保持1秒防止边界为0
        return max(1, int((tomorrow_midnight - now).total_seconds()))

    @staticmethod
    def check_free_draw_available(guild_id: int, discord_user_id: int) -> bool:
        """
        检查今日免费抽奖是否可用

        Args:
            guild_id: 服务器ID
            discord_user_id: Discord用户ID

        Returns:
            True表示可以抽奖,False表示今天已经抽过
        """
        try:
            today = now_est().date()
            key = f'draw:free:{guild_id}:{discord_user_id}:{today}'

            # 如果key存在,说明今天已抽过
            return redis_client.exists(key) == 0
        except Exception as e:
            logger.error(f"检查免费抽奖失败: {e}")
            # Redis失败时,返回True允许抽奖(降级策略)
            return True

    @staticmethod
    def mark_free_draw_used(guild_id: int, discord_user_id: int) -> bool:
        """
        标记今日免费抽奖已使用

        Args:
            guild_id: 服务器ID
            discord_user_id: Discord用户ID

        Returns:
            是否成功标记
        """
        try:
            today = now_est().date()
            key = f'draw:free:{guild_id}:{discord_user_id}:{today}'

            # 计算到次日0点的秒数
            ttl = DrawLimiter.get_ttl_to_midnight_est()

            # 设置标记,自动过期
            redis_client.setex(key, ttl, '1')
            return True
        except Exception as e:
            logger.error(f"标记免费抽奖失败: {e}")
            return False

    @staticmethod
    def get_paid_draw_count(guild_id: int, discord_user_id: int) -> int:
        """
        获取今日付费抽奖次数

        Args:
            guild_id: 服务器ID
            discord_user_id: Discord用户ID

        Returns:
            今日已抽奖次数
        """
        try:
            today = now_est().date()
            key = f'draw:paid:{guild_id}:{discord_user_id}:{today}'

            count = redis_client.get(key)
            return int(count) if count else 0
        except Exception as e:
            logger.error(f"获取付费抽奖次数失败: {e}")
            return 0

    @staticmethod
    def increment_paid_draw(guild_id: int, discord_user_id: int, max_draws: int = 20) -> bool:
        """
        增加付费抽奖计数,返回是否成功(是否已达上限)

        Args:
            guild_id: 服务器ID
            discord_user_id: Discord用户ID
            max_draws: 每日最大抽奖次数

        Returns:
            True表示成功增加计数,False表示已达上限
        """
        try:
            today = now_est().date()
            key = f'draw:paid:{guild_id}:{discord_user_id}:{today}'

            # 使用Lua脚本确保原子性
            lua_script = """
            local key = KEYS[1]
            local max_draws = tonumber(ARGV[1])
            local ttl = tonumber(ARGV[2])

            local current = redis.call('GET', key)
            if current == false then
                current = 0
            else
                current = tonumber(current)
            end

            if current >= max_draws then
                return -1  -- 已达上限
            end

            local new_count = current + 1
            redis.call('SET', key, new_count, 'EX', ttl)
            return new_count
            """

            # 计算TTL
            ttl = DrawLimiter.get_ttl_to_midnight_est()

            # 执行脚本
            result = redis_client.eval(lua_script, 1, key, max_draws, ttl)

            return result != -1  # -1表示失败,其他表示成功
        except Exception as e:
            logger.error(f"增加付费抽奖计数失败: {e}")
            # Redis失败时,返回True允许抽奖(降级策略)
            return True

    @staticmethod
    def get_egg_pity_count(guild_id: int, discord_user_id: int) -> int:
        """
        获取蛋抽取保底计数

        Args:
            guild_id: 服务器ID
            discord_user_id: Discord用户ID

        Returns:
            当前保底计数
        """
        try:
            key = f'egg:pity:{guild_id}:{discord_user_id}'
            count = redis_client.get(key)
            return int(count) if count else 0
        except Exception as e:
            logger.error(f"获取蛋保底计数失败: {e}")
            return 0

    @staticmethod
    def increment_egg_pity(guild_id: int, discord_user_id: int) -> int:
        """
        增加蛋抽取保底计数

        Args:
            guild_id: 服务器ID
            discord_user_id: Discord用户ID

        Returns:
            增加后的保底计数
        """
        try:
            key = f'egg:pity:{guild_id}:{discord_user_id}'
            new_count = redis_client.incr(key)
            return new_count
        except Exception as e:
            logger.error(f"增加蛋保底计数失败: {e}")
            return 0

    @staticmethod
    def reset_egg_pity(guild_id: int, discord_user_id: int):
        """
        重置蛋抽取保底计数

        Args:
            guild_id: 服务器ID
            discord_user_id: Discord用户ID
        """
        try:
            key = f'egg:pity:{guild_id}:{discord_user_id}'
            redis_client.delete(key)
        except Exception as e:
            logger.error(f"重置蛋保底计数失败: {e}")
