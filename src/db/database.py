from supabase import create_client, Client
from src.config.config import DB_CONFIG
import datetime
from typing import Optional, Dict, Any, List

# 全局Supabase客户端实例
_supabase_client: Optional[Client] = None

def get_connection() -> Client:
    """
    获取Supabase客户端连接
    返回Supabase客户端实例，保持与原MySQL接口的兼容性
    """
    global _supabase_client
    
    if _supabase_client is None:
        _supabase_client = create_client(
            DB_CONFIG["url"], 
            DB_CONFIG["key"]
        )
    
    return _supabase_client

def get_supabase_client() -> Client:
    """
    获取Supabase客户端的别名函数
    """
    return get_connection()

# 注意：init_db函数已移除，因为Supabase中的表结构已经存在
# 如果需要初始化数据，请使用Supabase的迁移功能

class SupabaseHelper:
    """
    Supabase数据库操作辅助类
    提供常用的数据库操作方法
    """
    
    def __init__(self):
        self.client = get_connection()
    
    def execute_query(self, table: str, operation: str = "select", **kwargs) -> Any:
        """
        执行数据库查询操作
        
        Args:
            table: 表名
            operation: 操作类型 (select, insert, update, delete)
            **kwargs: 查询参数
        
        Returns:
            查询结果
        """
        try:
            if operation == "select":
                query = self.client.table(table).select(kwargs.get("columns", "*"))
                
                # 添加过滤条件
                if "filters" in kwargs:
                    for filter_condition in kwargs["filters"]:
                        query = query.filter(
                            filter_condition["column"],
                            filter_condition["operator"],
                            filter_condition["value"]
                        )
                
                # 添加排序
                if "order" in kwargs:
                    query = query.order(kwargs["order"]["column"], desc=kwargs["order"].get("desc", False))
                
                # 添加限制
                if "limit" in kwargs:
                    query = query.limit(kwargs["limit"])
                
                return query.execute()
            
            elif operation == "insert":
                return self.client.table(table).insert(kwargs.get("data", {})).execute()
            
            elif operation == "update":
                query = self.client.table(table).update(kwargs.get("data", {}))
                
                # 添加过滤条件
                if "filters" in kwargs:
                    for filter_condition in kwargs["filters"]:
                        query = query.filter(
                            filter_condition["column"],
                            filter_condition["operator"],
                            filter_condition["value"]
                        )
                
                return query.execute()
            
            elif operation == "delete":
                query = self.client.table(table)
                
                # 添加过滤条件
                if "filters" in kwargs:
                    for filter_condition in kwargs["filters"]:
                        query = query.filter(
                            filter_condition["column"],
                            filter_condition["operator"],
                            filter_condition["value"]
                        )
                
                return query.delete().execute()
            
            else:
                raise ValueError(f"不支持的操作类型: {operation}")
                
        except Exception as e:
            print(f"数据库操作错误: {e}")
            raise

# 创建全局辅助实例
db_helper = SupabaseHelper()

# 为了保持向后兼容性，提供一些常用的数据库操作函数
def execute_sql(query: str, params: Optional[Dict] = None) -> Any:
    """
    执行原始SQL查询（通过Supabase RPC）
    注意：这需要在Supabase中创建相应的数据库函数
    """
    try:
        client = get_connection()
        # 对于复杂的SQL查询，建议使用Supabase的RPC功能
        # 或者将查询拆分为多个简单的操作
        print(f"警告: 直接SQL查询需要通过Supabase RPC实现: {query}")
        return None
    except Exception as e:
        print(f"SQL执行错误: {e}")
        raise

def get_user_data(user_id: str) -> Optional[Dict]:
    """
    获取用户数据（旧版本，保持向后兼容）
    """
    try:
        result = db_helper.execute_query(
            "users",
            "select",
            filters=[{"column": "user_id", "operator": "eq", "value": user_id}]
        )
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"获取用户数据错误: {e}")
        return None

def get_user_by_guild_and_discord_id(guild_id: str, discord_user_id: str) -> Optional[Dict]:
    """
    根据guild_id和discord_user_id获取用户数据
    """
    try:
        result = db_helper.execute_query(
            "users",
            "select",
            filters=[
                {"column": "guild_id", "operator": "eq", "value": guild_id},
                {"column": "discord_user_id", "operator": "eq", "value": discord_user_id}
            ]
        )
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"获取用户数据错误: {e}")
        return None

def update_user_points(user_id: str, points: int) -> bool:
    """
    更新用户积分
    """
    try:
        result = db_helper.execute_query(
            "users",
            "update",
            data={"points": points},
            filters=[{"column": "user_id", "operator": "eq", "value": user_id}]
        )
        return len(result.data) > 0
    except Exception as e:
        print(f"更新用户积分错误: {e}")
        return False

def create_user_if_not_exists(user_id: str) -> bool:
    """
    如果用户不存在则创建用户（旧版本，保持向后兼容）
    """
    try:
        # 先检查用户是否存在
        existing_user = get_user_data(user_id)
        if existing_user:
            return True
        
        # 创建新用户
        result = db_helper.execute_query(
            "users",
            "insert",
            data={
                "user_id": user_id,
                "points": 0,
                "last_draw_date": None,
                "paid_draws_today": 0,
                "last_paid_draw_date": "1970-01-01",
                "equipped_pet_id": None,
                "last_pet_points_update": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
            }
        )
        return len(result.data) > 0
    except Exception as e:
        print(f"创建用户错误: {e}")
        return False

def create_user_by_guild_and_discord_id(guild_id: str, discord_user_id: str) -> Optional[Dict]:
    """
    根据guild_id和discord_user_id创建或获取用户
    如果有相同的discord_user_id但不同的guild_id，会创建新的记录
    """
    try:
        # 先检查用户是否存在
        existing_user = get_user_by_guild_and_discord_id(guild_id, discord_user_id)
        if existing_user:
            return existing_user
        
        # 创建新用户
        result = db_helper.execute_query(
            "users",
            "insert",
            data={
                "guild_id": guild_id,
                "discord_user_id": discord_user_id,
                "points": 0,
                "last_draw_date": None,
                "paid_draws_today": 0,
                "last_paid_draw_date": "1970-01-01",
                "equipped_pet_id": None,
                "last_pet_points_update": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
            }
        )
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"创建用户错误: {e}")
        return None