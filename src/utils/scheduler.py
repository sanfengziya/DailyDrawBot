"""
定时任务调度器
处理饱食度重置和杂货铺刷新等定时任务
"""

import asyncio
import datetime
from typing import Optional
from src.utils.feeding_system import FoodShopManager
from src.utils.helpers import now_est

class FeedingScheduler:
    """喂食系统定时任务调度器"""

    def __init__(self, bot=None):
        self.bot = bot
        self.running = False
        self.task: Optional[asyncio.Task] = None

    async def start(self):
        """启动定时任务"""
        if self.running:
            return

        self.running = True
        self.task = asyncio.create_task(self._scheduler_loop())
        print("🕐 饱食度重置和杂货铺刷新定时任务已启动")

    async def stop(self):
        """停止定时任务"""
        if not self.running:
            return

        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        print("🕐 定时任务已停止")

    async def _scheduler_loop(self):
        """主定时循环"""
        while self.running:
            try:
                # 获取当前美东时间
                current_est = now_est()

                # 检查是否到达重置时间点
                await self._check_satiety_reset(current_est)
                await self._check_shop_refresh(current_est)

                # 等待1分钟再次检查
                await asyncio.sleep(60)

            except Exception as e:
                print(f"定时任务执行错误: {e}")
                await asyncio.sleep(60)  # 出错后等待1分钟再重试

    async def _check_satiety_reset(self, current_time: datetime.datetime):
        """检查并执行饱食度重置"""
        # 重置时间点：美东时间0点和12点
        if (current_time.hour == 0 and current_time.minute == 0) or \
           (current_time.hour == 12 and current_time.minute == 0):

            # 避免重复执行（给1分钟的缓冲时间）
            last_reset_key = f"satiety_reset_{current_time.strftime('%Y%m%d_%H')}"
            if hasattr(self, '_last_reset_times') and last_reset_key in self._last_reset_times:
                return

            if not hasattr(self, '_last_reset_times'):
                self._last_reset_times = set()

            self._last_reset_times.add(last_reset_key)

            await self._reset_all_pet_satiety()
            print(f"🍽️ 执行饱食度重置 - {current_time.strftime('%Y-%m-%d %H:%M')} EST")

    async def _check_shop_refresh(self, current_time: datetime.datetime):
        """检查并执行杂货铺刷新"""
        # 刷新时间：美东时间每天0点
        if current_time.hour == 0 and current_time.minute == 0:

            # 避免重复执行
            last_refresh_key = f"shop_refresh_{current_time.strftime('%Y%m%d')}"
            if hasattr(self, '_last_refresh_times') and last_refresh_key in self._last_refresh_times:
                return

            if not hasattr(self, '_last_refresh_times'):
                self._last_refresh_times = set()

            self._last_refresh_times.add(last_refresh_key)

            await self._refresh_daily_shop()
            print(f"🏪 执行杂货铺刷新 - {current_time.strftime('%Y-%m-%d %H:%M')} EST")

    async def _reset_all_pet_satiety(self):
        """重置所有宠物的饱食度"""
        try:
            from src.db.database import get_supabase_client

            supabase = get_supabase_client()
            current_time = datetime.datetime.now(datetime.timezone.utc)

            # 重置所有宠物的饱食度为0
            result = supabase.table('user_pets').update({
                'satiety': 0,
                'last_feeding': None  # 也重置最后喂食时间
            }).neq('id', 0).execute()  # 更新所有宠物

            affected_count = len(result.data) if result.data else 0
            print(f"✅ 重置了 {affected_count} 只宠物的饱食度")

        except Exception as e:
            print(f"❌ 重置饱食度时出错: {e}")

    async def _refresh_daily_shop(self):
        """刷新每日杂货铺"""
        try:
            # 使用FoodShopManager刷新商店
            new_items = FoodShopManager.refresh_daily_shop()
            item_count = len(new_items) if new_items else 0
            print(f"✅ 杂货铺已刷新，共 {item_count} 种商品")

        except Exception as e:
            print(f"❌ 刷新杂货铺时出错: {e}")

    async def force_satiety_reset(self):
        """手动强制重置饱食度（用于测试）"""
        await self._reset_all_pet_satiety()

    async def force_shop_refresh(self):
        """手动强制刷新杂货铺（用于测试）"""
        await self._refresh_daily_shop()

# 全局调度器实例
_global_scheduler: Optional[FeedingScheduler] = None

def get_scheduler() -> FeedingScheduler:
    """获取全局调度器实例"""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = FeedingScheduler()
    return _global_scheduler

async def start_feeding_scheduler(bot=None):
    """启动喂食系统定时任务"""
    scheduler = get_scheduler()
    scheduler.bot = bot
    await scheduler.start()

async def stop_feeding_scheduler():
    """停止喂食系统定时任务"""
    scheduler = get_scheduler()
    await scheduler.stop()

# 管理员命令函数
async def admin_reset_satiety():
    """管理员手动重置饱食度"""
    scheduler = get_scheduler()
    await scheduler.force_satiety_reset()

async def admin_refresh_shop():
    """管理员手动刷新杂货铺"""
    scheduler = get_scheduler()
    await scheduler.force_shop_refresh()

def get_next_reset_times():
    """获取下次重置时间信息"""
    current_est = now_est()

    # 计算下次饱食度重置时间
    today = current_est.replace(hour=0, minute=0, second=0, microsecond=0)
    noon_today = current_est.replace(hour=12, minute=0, second=0, microsecond=0)
    midnight_tomorrow = today + datetime.timedelta(days=1)

    next_satiety_reset = None
    if current_est < noon_today:
        next_satiety_reset = noon_today
    elif current_est < midnight_tomorrow:
        next_satiety_reset = midnight_tomorrow
    else:
        next_satiety_reset = midnight_tomorrow

    # 计算下次杂货铺刷新时间
    if current_est.hour >= 0:
        next_shop_refresh = today + datetime.timedelta(days=1)
    else:
        next_shop_refresh = today

    return {
        'next_satiety_reset': next_satiety_reset,
        'next_shop_refresh': next_shop_refresh,
        'current_est_time': current_est
    }
