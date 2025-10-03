"""
Redis客户端模块
提供Redis连接池和单例客户端实例
"""
import redis
from redis import ConnectionPool
import os
from dotenv import load_dotenv

load_dotenv()


class RedisClient:
    """Redis客户端单例类"""
    _instance = None
    _pool = None
    _client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._initialize_pool()
        return cls._instance

    @classmethod
    def _initialize_pool(cls):
        """初始化Redis连接池"""
        redis_url = os.getenv('REDIS_URL')

        if redis_url:
            # 使用Redis URL连接 (Redis Cloud)
            cls._pool = ConnectionPool.from_url(
                redis_url,
                decode_responses=True,  # 自动解码为字符串
                max_connections=50,
                socket_timeout=5,
                socket_connect_timeout=5
            )
        else:
            # 使用单独的配置参数
            cls._pool = ConnectionPool(
                host=os.getenv('REDIS_HOST', 'localhost'),
                port=int(os.getenv('REDIS_PORT', 6379)),
                password=os.getenv('REDIS_PASSWORD'),
                db=int(os.getenv('REDIS_DB', 0)),
                decode_responses=True,
                max_connections=50,
                socket_timeout=5,
                socket_connect_timeout=5
            )

    def get_connection(self):
        """获取Redis连接"""
        if self._client is None:
            self._client = redis.Redis(connection_pool=self._pool)
        return self._client


# 全局单例实例
_redis_instance = RedisClient()
redis_client = _redis_instance.get_connection()


def get_redis_client():
    """获取Redis客户端实例"""
    return redis_client
