"""
宠物喂食系统核心功能
包含经验计算、等级管理、饱食度管理等功能
"""

import random
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from enum import Enum
from src.utils.i18n import get_localized_food_name, get_localized_pet_name, get_default_locale

class FlavorType(Enum):
    """口味类型枚举"""
    SWEET = "SWEET"
    SALTY = "SALTY"
    SOUR = "SOUR"
    SPICY = "SPICY"
    UMAMI = "UMAMI"

class RarityType(Enum):
    """稀有度类型枚举"""
    C = "C"
    R = "R"
    SR = "SR"
    SSR = "SSR"

class FeedingSystem:
    """宠物喂食系统主类"""

    # 口味匹配倍数配置
    FLAVOR_MATCH_MULTIPLIER = 1.3      # 口味匹配时经验倍数 (+30%)
    FLAVOR_DISLIKE_MULTIPLIER = 0.9    # 讨厌口味时经验惩罚 (-10%)

    # 饱食度配置
    SATIETY_MIN_GAIN = 5    # 每次喂食最少增加饱食度
    SATIETY_MAX_GAIN = 8    # 每次喂食最多增加饱食度
    SATIETY_MAX = 100       # 最大饱食度

    # 购买限制配置
    MAX_DAILY_FOOD_PURCHASES = 30  # 每日最大食粮购买数量

    # 经验等级计算参数
    XP_BASE = 20           # 基础经验需求
    XP_GROWTH_POW = 1.45    # 成长指数
    XP_STEP = 2            # 步进值

    @staticmethod
    def calculate_level_xp_requirement(current_level: int) -> int:
        """
        计算从当前等级升级到下一等级所需的经验值
        例如：输入1，返回从1级升到2级需要的经验
        基于公式: XP_Require(current_level) = Base * ((current_level+1)^GrowthPow) + Step * current_level
        """
        if current_level < 1:
            return 0

        base = FeedingSystem.XP_BASE
        growth_pow = FeedingSystem.XP_GROWTH_POW
        step = FeedingSystem.XP_STEP

        return round(base * (current_level ** growth_pow) + step * current_level)

    @staticmethod
    def calculate_total_xp_for_level(level: int) -> int:
        """计算达到某等级的累计总经验需求"""
        if level <= 1:
            return 0

        total = 0
        # 从1级开始，累加每次升级所需的经验
        for current_level in range(1, level):
            total += FeedingSystem.calculate_level_xp_requirement(current_level)
        return total

    @staticmethod
    def calculate_level_from_total_xp(total_xp: int) -> int:
        """根据总经验计算当前等级"""
        if total_xp < 0:
            return 1

        level = 1
        accumulated_xp = 0

        while True:
            # 检查从当前等级升级到下一等级需要的经验
            next_level_xp = FeedingSystem.calculate_level_xp_requirement(level)

            # 如果总经验不足以升级到下一级，返回当前等级
            if accumulated_xp + next_level_xp > total_xp:
                break

            # 否则累加经验并升级
            accumulated_xp += next_level_xp
            level += 1

            # 防止无限循环
            if level > 200:  # 假设最大等级为200
                break

        return level

    @staticmethod
    def calculate_current_level_xp(total_xp: int) -> Tuple[int, int, int]:
        """
        根据总经验计算当前等级信息
        返回: (当前等级, 当前等级已获得经验, 升到下一级还需要的经验)
        """
        level = FeedingSystem.calculate_level_from_total_xp(total_xp)

        # 计算到达当前等级所需的总经验
        level_start_xp = FeedingSystem.calculate_total_xp_for_level(level)

        # 当前等级已获得的经验
        current_level_xp = total_xp - level_start_xp

        # 升级到下一等级需要的总经验（输入当前等级）
        next_level_total_requirement = FeedingSystem.calculate_level_xp_requirement(level)

        # 还需要的经验 = 升级总需求 - 当前已有经验
        remaining_xp = max(0, next_level_total_requirement - current_level_xp)

        return level, current_level_xp, next_level_total_requirement

    @staticmethod
    def calculate_feeding_xp(food_base_xp: int, food_xp_flow: int,
                           pet_favorite_flavor: Optional[str],
                           pet_dislike_flavor: Optional[str],
                           food_flavor: str) -> int:
        """
        计算喂食获得的经验值
        包含基础经验 + 浮动经验 + 口味匹配修正
        """
        # 基础经验 + 随机浮动
        base_xp = food_base_xp + random.randint(-food_xp_flow, food_xp_flow)
        base_xp = max(1, base_xp)  # 确保至少获得1点经验

        # 口味匹配修正
        multiplier = 1.0
        if pet_favorite_flavor and food_flavor == pet_favorite_flavor:
            multiplier = FeedingSystem.FLAVOR_MATCH_MULTIPLIER
        elif pet_dislike_flavor and food_flavor == pet_dislike_flavor:
            multiplier = FeedingSystem.FLAVOR_DISLIKE_MULTIPLIER

        final_xp = round(base_xp * multiplier)
        return max(1, final_xp)  # 确保至少获得1点经验

    @staticmethod
    def calculate_satiety_gain() -> int:
        """计算饱食度增加值（随机5-8）"""
        return random.randint(FeedingSystem.SATIETY_MIN_GAIN, FeedingSystem.SATIETY_MAX_GAIN)

    @staticmethod
    def is_satiety_full(current_satiety: int, satiety_gain: int) -> bool:
        """检查饱食度是否会超过上限"""
        return current_satiety + satiety_gain > FeedingSystem.SATIETY_MAX

    @staticmethod
    def apply_satiety_gain(current_satiety: int, satiety_gain: int) -> int:
        """应用饱食度增加，不超过上限"""
        return min(current_satiety + satiety_gain, FeedingSystem.SATIETY_MAX)

    @staticmethod
    async def purchase_food(user_id: int, food_template_id: int, quantity: int = 1, guild_id: int = None, discord_user_id: int = None) -> tuple[bool, list]:
        """
        购买食物

        Args:
            user_id: 用户内部ID
            food_template_id: 食物模板ID
            quantity: 购买数量
            guild_id: 服务器ID（用于缓存清除）
            discord_user_id: Discord用户ID（用于缓存清除）

        Returns:
            tuple: (success, message)
        """
        from src.db.database import get_supabase_client
        from datetime import datetime
        from zoneinfo import ZoneInfo

        supabase = get_supabase_client()
        today = datetime.now(ZoneInfo("America/New_York")).date()

        try:
            # 1. 获取食物信息
            food_response = supabase.table('food_templates').select('*').eq('id', food_template_id).execute()
            if not food_response.data:
                return False, "食物不存在！"

            food_data = food_response.data[0]
            total_price = food_data['price'] * quantity

            # 2. 检查用户积分和购买限制
            user_response = supabase.table('users').select(
                'points, food_purchased_today, last_food_purchase_date'
            ).eq('id', user_id).execute()
            if not user_response.data:
                return False, "用户不存在！"

            user_data = user_response.data[0]
            user_points = user_data['points']
            food_purchased_today = user_data['food_purchased_today'] or 0
            last_food_purchase_date = user_data['last_food_purchase_date']

            # 检查积分
            if user_points < total_price:
                return False, f"积分不足！需要 {total_price} 积分，你只有 {user_points} 积分。"

            # 检查是否跨天重置购买数量
            if last_food_purchase_date != today.isoformat():
                food_purchased_today = 0

            # 检查每日购买限制
            if food_purchased_today + quantity > FeedingSystem.MAX_DAILY_FOOD_PURCHASES:
                remaining = FeedingSystem.MAX_DAILY_FOOD_PURCHASES - food_purchased_today
                return False, f"每日食粮购买限制！今日已购买 {food_purchased_today} 份，最多购买 {FeedingSystem.MAX_DAILY_FOOD_PURCHASES} 份。还可购买 {remaining} 份。"

            # 3. 检查商品是否在今日目录中
            catalog_response = supabase.table('daily_shop_catalog').select('food_template_id').eq(
                'refresh_date', today.isoformat()
            ).eq('food_template_id', food_template_id).execute()

            if not catalog_response.data:
                return False, "今日商店中没有此商品！"

            # 4. 执行交易
            # 扣除积分并更新购买计数
            supabase.table('users').update({
                'points': user_points - total_price,
                'food_purchased_today': food_purchased_today + quantity,
                'last_food_purchase_date': today.isoformat()
            }).eq('id', user_id).execute()

            # 清除积分缓存，确保check命令显示最新数据
            if guild_id and discord_user_id:
                from src.utils.cache import UserCache
                await UserCache.invalidate_points_cache(guild_id, discord_user_id)

            # 添加到用户库存
            # 检查用户是否已有此食物
            inventory_response = supabase.table('user_food_inventory').select('quantity').eq(
                'user_id', user_id
            ).eq('food_template_id', food_template_id).execute()

            if inventory_response.data:
                # 增加数量
                current_quantity = inventory_response.data[0]['quantity']
                supabase.table('user_food_inventory').update({
                    'quantity': current_quantity + quantity
                }).eq('user_id', user_id).eq('food_template_id', food_template_id).execute()
            else:
                # 新增记录
                supabase.table('user_food_inventory').insert({
                    'user_id': user_id,
                    'food_template_id': food_template_id,
                    'quantity': quantity
                }).execute()

            return True, (quantity, total_price, user_points - total_price, food_purchased_today + quantity)

        except Exception as e:
            print(f"购买食物时出错: {e}")
            return False, "购买失败，系统错误！"

class SatietyManager:
    """饱食度管理类"""

    @staticmethod
    def should_reset_satiety(last_reset_time: Optional[datetime]) -> bool:
        """
        检查是否需要重置饱食度
        重置时间点：美东时间 00:00 和 12:00
        """
        if not last_reset_time:
            return True

        # 获取当前美东时间
        from src.utils.helpers import now_est
        current_time = now_est()

        # 获取今天的重置时间点
        today_midnight = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        today_noon = current_time.replace(hour=12, minute=0, second=0, microsecond=0)

        # 检查是否跨过了重置时间点
        if last_reset_time < today_midnight and current_time >= today_midnight:
            return True
        if last_reset_time < today_noon and current_time >= today_noon:
            return True

        return False

    @staticmethod
    def get_next_reset_time() -> datetime:
        """获取下一次重置时间"""
        from src.utils.helpers import now_est
        current_time = now_est()

        # 今天的重置时间点
        today_midnight = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        today_noon = current_time.replace(hour=12, minute=0, second=0, microsecond=0)

        # 如果当前时间在午夜到中午之间，下次重置是今天中午
        if current_time < today_noon:
            return today_noon
        # 否则下次重置是明天午夜
        else:
            from datetime import timedelta
            tomorrow_midnight = today_midnight + timedelta(days=1)
            return tomorrow_midnight

class FoodShopManager:
    """杂货铺管理类"""

    # 稀有度分布配置
    RARITY_DISTRIBUTION = {
        'C': 0.40,    # 40%
        'R': 0.30,    # 30%
        'SR': 0.20,   # 20%
        'SSR': 0.10   # 10%
    }

    # 每日商品数量
    DAILY_ITEMS_COUNT = 5

    @staticmethod
    def generate_daily_shop_items() -> List[Dict]:
        """
        生成当日杂货铺商品列表
        返回食粮模板ID列表，增强错误处理和验证
        """
        try:
            print("🔄 开始生成杂货铺商品...")
            from src.db.database import get_supabase_client
            supabase = get_supabase_client()

            # 获取所有食粮模板
            response = supabase.table('food_templates').select('*').execute()
            if not response.data:
                print("❌ 数据库中无食粮模板数据")
                return []

            food_templates = response.data
            print(f"📦 获取到{len(food_templates)}个食粮模板")

        except Exception as e:
            print(f"❌ 获取食粮模板时出错: {e}")
            return []

        # 验证食粮模板完整性
        valid_templates = []
        for template in food_templates:
            if not all(key in template for key in ['id', 'cn_name', 'en_name', 'rarity', 'flavor', 'price', 'base_xp']):
                print(f"⚠️ 跳过不完整的食粮模板: {template.get('id', 'Unknown')}")
                continue
            valid_templates.append(template)

        if len(valid_templates) < FoodShopManager.DAILY_ITEMS_COUNT:
            print(f"❌ 有效食粮模板不足，需要{FoodShopManager.DAILY_ITEMS_COUNT}个，只有{len(valid_templates)}个")
            return []

        # 按稀有度分组并验证
        rarity_groups = {
            'C': [f for f in valid_templates if f['rarity'] == 'C'],
            'R': [f for f in valid_templates if f['rarity'] == 'R'],
            'SR': [f for f in valid_templates if f['rarity'] == 'SR'],
            'SSR': [f for f in valid_templates if f['rarity'] == 'SSR']
        }

        # 检查每个稀有度是否至少有1个商品
        empty_rarities = [rarity for rarity, items in rarity_groups.items() if not items]
        if empty_rarities:
            print(f"⚠️ 以下稀有度没有可用商品: {empty_rarities}")

        print(f"📊 稀有度分布: C={len(rarity_groups['C'])}, R={len(rarity_groups['R'])}, SR={len(rarity_groups['SR'])}, SSR={len(rarity_groups['SSR'])}")

        selected_items = []
        generation_attempts = 0
        max_attempts = 50  # 防止无限循环

        # 记录已选择的食粮ID，避免重复
        selected_food_ids = set()

        # 生成5个商品，确保每个食物模板只被选择一次
        while len(selected_items) < FoodShopManager.DAILY_ITEMS_COUNT and generation_attempts < max_attempts:
            generation_attempts += 1

            # 根据概率选择稀有度
            rand = random.random()
            cumulative = 0
            selected_rarity = 'C'

            for rarity, prob in FoodShopManager.RARITY_DISTRIBUTION.items():
                cumulative += prob
                if rand <= cumulative:
                    selected_rarity = rarity
                    break

            # 从该稀有度中选择食粮，排除已选择的
            available_foods = [f for f in rarity_groups.get(selected_rarity, []) if f['id'] not in selected_food_ids]
            if not available_foods:
                print(f"⚠️ {selected_rarity}级食粮已全部选择，跳过此稀有度")
                continue

            # 随机选择食粮
            selected_food = random.choice(available_foods)

            # 验证选中的食粮
            if not selected_food.get('id'):
                print(f"⚠️ 跳过无效的食粮数据: {selected_food}")
                continue

            # 添加到已选择集合
            selected_food_ids.add(selected_food['id'])
            selected_items.append({
                'food_template_id': selected_food['id'],
                'food_data': selected_food
            })

            print(f"✅ 选择了{selected_rarity}级食粮: {get_localized_food_name(selected_food, get_default_locale())} ({selected_food['flavor']})")

        if len(selected_items) != FoodShopManager.DAILY_ITEMS_COUNT:
            print(f"⚠️ 商品生成不完整，期望{FoodShopManager.DAILY_ITEMS_COUNT}个，实际{len(selected_items)}个，尝试次数: {generation_attempts}")
            if len(selected_items) == 0:
                return []

        # 统计口味分布
        flavor_counts = {}
        for item in selected_items:
            flavor = item['food_data']['flavor']
            flavor_counts[flavor] = flavor_counts.get(flavor, 0) + 1

        flavor_distribution = ", ".join([f"{flavor}({count}个)" for flavor, count in flavor_counts.items()])
        print(f"🎯 商品生成完成，共{len(selected_items)}个商品，口味分布: {flavor_distribution}")
        return selected_items

    @staticmethod
    def refresh_daily_shop():
        """刷新每日杂货铺目录（原子性操作，避免商店清空）"""
        from src.db.database import get_supabase_client
        from datetime import datetime
        from zoneinfo import ZoneInfo

        supabase = get_supabase_client()
        today = datetime.now(ZoneInfo("America/New_York")).date()
        today_str = today.isoformat()

        try:
            print(f"🏪 开始刷新杂货铺 - {today_str}")

            # 1. 首先检查今日是否已有商店数据，避免重复刷新
            existing_response = supabase.table('daily_shop_catalog').select('*').eq('refresh_date', today_str).execute()
            existing_count = len(existing_response.data) if existing_response.data else 0

            if existing_count > 0:
                print(f"⚠️ 今日商店已存在 {existing_count} 个商品，跳过刷新以避免重复")
                return []

            # 2. 生成新目录条目并验证
            new_items = FoodShopManager.generate_daily_shop_items()

            if not new_items:
                print("❌ 商品生成失败，跳过刷新以保护现有商店数据")
                return []

            # 3. 构建新目录数据并验证完整性
            catalog_rows = []
            for item in new_items:
                if not item.get('food_template_id'):
                    print(f"❌ 商品数据不完整，跳过刷新: {item}")
                    return []

                catalog_rows.append({
                    'refresh_date': today_str,
                    'food_template_id': item['food_template_id']
                })

            if len(catalog_rows) != FoodShopManager.DAILY_ITEMS_COUNT:
                print(f"❌ 商品数量不足，期望{FoodShopManager.DAILY_ITEMS_COUNT}个，实际{len(catalog_rows)}个，跳过刷新")
                return []

            print(f"✅ 商品生成成功，共{len(catalog_rows)}种商品")

            # 4. 使用 UPSERT 操作避免冲突
            try:
                # 使用 upsert 替代 delete+insert，避免竞态条件
                # ON CONFLICT (refresh_date, food_template_id) DO UPDATE 只更新现有记录
                upsert_result = supabase.table('daily_shop_catalog').upsert(
                    catalog_rows,
                    on_conflict='refresh_date,food_template_id'
                ).execute()

                if not upsert_result.data or len(upsert_result.data) != len(catalog_rows):
                    raise Exception(f"upsert失败：期望{len(catalog_rows)}条，实际{len(upsert_result.data) if upsert_result.data else 0}条")

                print(f"✅ 商店目录更新成功，共{len(upsert_result.data)}种商品")
                print("🏪 杂货铺刷新完成！")

            except Exception as db_error:
                print(f"❌ 数据库操作失败: {db_error}")
                raise db_error

            return new_items

        except Exception as e:
            print(f"❌ 杂货铺刷新失败: {e}")
            return []

    @staticmethod
    def test_shop_refresh():
        """测试杂货铺刷新功能（用于调试）"""
        print("🧪 开始测试杂货铺刷新功能...")

        # 测试商品生成
        print("\n1. 测试商品生成...")
        items = FoodShopManager.generate_daily_shop_items()
        if items:
            print(f"✅ 商品生成测试通过，生成了{len(items)}个商品")
            for i, item in enumerate(items, 1):
                food_data = item['food_data']
                print(f"   {i}. {food_data['rarity']} - {get_localized_food_name(food_data, get_default_locale())} ({food_data['flavor']}) - {food_data['price']}积分")
        else:
            print("❌ 商品生成测试失败")
            return False

        # 测试完整刷新流程
        print("\n2. 测试完整刷新流程...")
        try:
            result = FoodShopManager.refresh_daily_shop()
            if result:
                print(f"✅ 完整刷新测试通过，刷新了{len(result)}个商品")
                return True
            else:
                print("⚠️ 刷新返回空结果，可能是保护机制触发")
                return False
        except Exception as e:
            print(f"❌ 完整刷新测试失败: {e}")
            return False

def get_pet_feeding_info(pet_id: int, locale: str = None) -> Optional[Dict]:
    """获取宠物喂食相关信息"""
    from src.db.database import get_supabase_client

    supabase = get_supabase_client()

    # 获取宠物信息
    response = supabase.table('user_pets').select('''
        id, user_id, level, xp_current, xp_total,
        favorite_flavor, dislike_flavor, satiety, last_feeding,
        pet_templates(id, en_name, cn_name, rarity)
    ''').eq('id', pet_id).execute()

    if not response.data:
        return None

    pet_data = response.data[0]

    # 计算等级信息
    level, current_level_xp, next_level_requirement = FeedingSystem.calculate_current_level_xp(pet_data['xp_total'])

    # 获取本地化的宠物名称
    if locale is None:
        locale = get_default_locale()
    pet_template_data = pet_data['pet_templates']
    pet_name = get_localized_pet_name(pet_template_data, locale)

    return {
        'id': pet_data['id'],
        'user_id': pet_data['user_id'],
        'name': pet_name,
        'rarity': pet_template_data['rarity'],
        'level': level,
        'xp_current': current_level_xp,
        'xp_total': pet_data['xp_total'],
        'xp_next_level': next_level_requirement,
        'favorite_flavor': pet_data['favorite_flavor'],
        'dislike_flavor': pet_data['dislike_flavor'],
        'satiety': pet_data['satiety'],
        'last_feeding': pet_data['last_feeding']
    }

def feed_pet(pet_id: int, food_template_id: int, locale: str = None) -> Dict:
    """
    执行宠物喂食
    返回喂食结果信息
    
    Args:
        pet_id: 宠物ID
        food_template_id: 食粮模板ID
        locale: 语言环境代码
    """
    from src.db.database import get_supabase_client

    supabase = get_supabase_client()

    # 使用传入的locale或默认locale
    if locale is None:
        locale = get_default_locale()

    # 获取宠物信息
    pet_info = get_pet_feeding_info(pet_id, locale)
    if not pet_info:
        return {'success': False, 'message': '宠物不存在'}

    # 检查饱食度
    if pet_info['satiety'] >= FeedingSystem.SATIETY_MAX:
        return {'success': False, 'message': '宠物已经吃饱了，无法继续喂食'}

    # 获取食粮信息
    food_response = supabase.table('food_templates').select('*').eq('id', food_template_id).execute()
    if not food_response.data:
        return {'success': False, 'message': '食粮不存在'}

    food_data = food_response.data[0]

    # 计算经验值
    xp_gained = FeedingSystem.calculate_feeding_xp(
        food_data['base_xp'],
        food_data['xp_flow'],
        pet_info['favorite_flavor'],
        pet_info['dislike_flavor'],
        food_data['flavor']
    )

    # 计算饱食度增加
    satiety_gain = FeedingSystem.calculate_satiety_gain()
    new_satiety = FeedingSystem.apply_satiety_gain(pet_info['satiety'], satiety_gain)

    # 计算新的总经验和等级
    new_total_xp = pet_info['xp_total'] + xp_gained
    new_level, new_current_xp, new_next_requirement = FeedingSystem.calculate_current_level_xp(new_total_xp)

    # 更新数据库
    current_time = datetime.now(timezone.utc)
    update_data = {
        'xp_total': new_total_xp,
        'xp_current': new_current_xp,  # 更新当前等级经验
        'level': new_level,
        'satiety': new_satiety,
        'last_feeding': current_time.isoformat()
    }

    supabase.table('user_pets').update(update_data).eq('id', pet_id).execute()

    # 检查是否升级
    level_up = new_level > pet_info['level']

    # 口味匹配信息
    flavor_bonus = ""
    if pet_info['favorite_flavor'] and food_data['flavor'] == pet_info['favorite_flavor']:
        flavor_bonus = "favorite"
    elif pet_info['dislike_flavor'] and food_data['flavor'] == pet_info['dislike_flavor']:
        flavor_bonus = "dislike"
    
    return {
        'success': True,
        'xp_gained': xp_gained,
        'satiety_gained': satiety_gain,
        'new_level': new_level,
        'new_satiety': new_satiety,
        'new_total_xp': new_total_xp,
        'level_up': level_up,
        'flavor_bonus': flavor_bonus,
        'food_name': get_localized_food_name(food_data, locale),
        'pet_name': pet_info['name']
    }

class AutoFeedingSystem:
    """一键喂食系统"""

    # 喂食模式枚举
    MODE_OPTIMAL_XP = "optimal_xp"
    MODE_FLAVOR_MATCH = "flavor_match"
    MODE_ECONOMIC = "economic"
    MODE_CLEAR_INVENTORY = "clear_inventory"

    @staticmethod
    def calculate_food_score(food_item: dict, pet_preferences: dict, mode: str) -> float:
        """
        计算食粮评分
        评分 = 基础分数 + 口味匹配加分 + 经验效率分数 - 稀有度惩罚
        """
        base_score = food_item['base_xp']

        # 口味匹配加分
        flavor_bonus = 0
        if food_item['flavor'] == pet_preferences.get('favorite'):
            flavor_bonus = base_score * 0.3  # 匹配偏好+30%
        elif food_item['flavor'] == pet_preferences.get('dislike'):
            flavor_bonus = -base_score * 0.5  # 厌恶口味大幅扣分

        # 经验效率分数（经验/价格比）
        efficiency_score = base_score / max(food_item['price'], 1)

        # 稀有度惩罚（避免浪费高级食粮）
        rarity_penalty = {'C': 0, 'R': -5, 'SR': -15, 'SSR': -30}
        rarity_malus = rarity_penalty.get(food_item['rarity'], 0)

        # 根据模式调整评分
        if mode == AutoFeedingSystem.MODE_OPTIMAL_XP:
            # 最优经验模式：重视经验和口味匹配
            total_score = base_score + flavor_bonus + efficiency_score * 8 + rarity_malus
        elif mode == AutoFeedingSystem.MODE_FLAVOR_MATCH:
            # 口味匹配模式：重视口味匹配，轻视效率
            if food_item['flavor'] == pet_preferences.get('favorite'):
                total_score = base_score * 2 + flavor_bonus + efficiency_score * 2
            elif food_item['flavor'] == pet_preferences.get('dislike'):
                total_score = -1000  # 严重惩罚厌恶口味
            else:
                total_score = base_score + efficiency_score * 2 + rarity_malus
        elif mode == AutoFeedingSystem.MODE_ECONOMIC:
            # 节约模式：重视性价比，惩罚稀有食粮
            total_score = efficiency_score * 15 + rarity_malus * 2 + flavor_bonus * 0.5
        elif mode == AutoFeedingSystem.MODE_CLEAR_INVENTORY:
            # 清空库存模式：优先数量多的食粮
            quantity_bonus = food_item.get('quantity', 0) * 5
            total_score = quantity_bonus + efficiency_score * 5 + flavor_bonus
        else:
            # 默认模式
            total_score = base_score + flavor_bonus + efficiency_score * 10 + rarity_malus

        return total_score

    @staticmethod
    def get_user_food_inventory(user_id: int) -> list:
        """获取用户食粮库存"""
        from src.db.database import get_supabase_client

        supabase = get_supabase_client()

        response = supabase.table('user_food_inventory').select('''
            quantity,
            food_templates(*)
        ''').eq('user_id', user_id).gt('quantity', 0).execute()

        inventory = []
        for item in response.data:
            food_data = item['food_templates']
            food_data['quantity'] = item['quantity']
            inventory.append(food_data)

        return inventory

    @staticmethod
    def select_optimal_foods(inventory: list, pet_preferences: dict, mode: str, max_feeds: int = None) -> list:
        """
        选择最优食粮组合
        返回: [(food_data, quantity), ...]
        """
        if not inventory:
            return []

        # 计算每种食粮的评分
        scored_foods = []
        for food in inventory:
            score = AutoFeedingSystem.calculate_food_score(food, pet_preferences, mode)
            scored_foods.append((food, score))

        # 按评分排序（从高到低）
        scored_foods.sort(key=lambda x: x[1], reverse=True)

        # 选择食粮进行喂食
        selected_foods = []
        remaining_feeds = max_feeds if max_feeds else float('inf')

        for food, score in scored_foods:
            if remaining_feeds <= 0:
                break

            if score <= 0:  # 跳过评分为负的食粮
                continue

            available_quantity = food['quantity']
            use_quantity = min(available_quantity, remaining_feeds)

            if use_quantity > 0:
                selected_foods.append((food, use_quantity))
                remaining_feeds -= use_quantity

        return selected_foods

    @staticmethod
    def calculate_feeding_needs(current_satiety: int, target_satiety: int = None) -> int:
        """计算达到目标饱食度需要的喂食次数"""
        if target_satiety is None:
            target_satiety = FeedingSystem.SATIETY_MAX

        if current_satiety >= target_satiety:
            return 0

        # 每次喂食平均增加饱食度（取中位数）
        avg_satiety_gain = (FeedingSystem.SATIETY_MIN_GAIN + FeedingSystem.SATIETY_MAX_GAIN) / 2

        needed_satiety = target_satiety - current_satiety
        feeds_needed = math.ceil(needed_satiety / avg_satiety_gain)

        return feeds_needed

    @staticmethod
    def auto_feed_pet(user_id: int, pet_id: int, mode: str = MODE_OPTIMAL_XP, max_feeds: int = None, locale: str = None) -> dict:
        """
        一键喂食宠物

        Args:
            user_id: 用户ID
            pet_id: 宠物ID
            mode: 喂食模式
            max_feeds: 最大喂食次数，None表示喂到饱
            locale: 语言环境代码

        Returns:
            dict: 喂食结果
        """
        from src.db.database import get_supabase_client

        # 使用传入的locale或默认locale
        if locale is None:
            locale = get_default_locale()

        # 获取宠物信息
        pet_info = get_pet_feeding_info(pet_id, locale)
        if not pet_info:
            return {'success': False, 'message': '宠物不存在！'}

        if pet_info['user_id'] != user_id:
            return {'success': False, 'message': '这只宠物不属于你！'}

        # 检查饱食度
        if pet_info['satiety'] >= FeedingSystem.SATIETY_MAX:
            return {'success': False, 'message': '宠物已经吃饱了！'}

        # 计算需要的喂食次数
        if max_feeds is None:
            max_feeds = AutoFeedingSystem.calculate_feeding_needs(pet_info['satiety'])

        if max_feeds <= 0:
            return {'success': False, 'message': '不需要喂食！'}

        # 获取食粮库存
        inventory = AutoFeedingSystem.get_user_food_inventory(user_id)
        if not inventory:
            return {'success': False, 'message': '没有可用的食粮！'}

        # 选择最优食粮组合
        pet_preferences = {
            'favorite': pet_info.get('favorite_flavor'),
            'dislike': pet_info.get('dislike_flavor')
        }

        selected_foods = AutoFeedingSystem.select_optimal_foods(
            inventory, pet_preferences, mode, max_feeds
        )

        if not selected_foods:
            return {'success': False, 'message': '没有合适的食粮可以使用！'}

        # 执行批量喂食
        try:
            result = AutoFeedingSystem.execute_batch_feeding(
                user_id, pet_id, selected_foods, pet_info, locale
            )
            return result
        except Exception as e:
            return {'success': False, 'message': f'喂食过程中出错：{str(e)}'}

    @staticmethod
    def execute_batch_feeding(user_id: int, pet_id: int, selected_foods: list, pet_info: dict, locale: str = None) -> dict:
        """执行批量喂食操作"""
        # 使用传入的locale或默认locale
        if locale is None:
            locale = get_default_locale()
        from src.db.database import get_supabase_client

        supabase = get_supabase_client()

        # 统计信息
        total_xp_gained = 0
        total_satiety_gained = 0
        total_feeds = 0
        foods_used = []
        original_level = pet_info['level']
        original_satiety = pet_info['satiety']
        original_total_xp = pet_info['xp_total']

        current_satiety = original_satiety
        current_total_xp = original_total_xp

        # 依次使用选中的食粮
        for food_data, use_quantity in selected_foods:
            for _ in range(use_quantity):
                # 检查饱食度是否已满
                if current_satiety >= FeedingSystem.SATIETY_MAX:
                    break

                # 计算这次喂食的收益
                xp_gained = FeedingSystem.calculate_feeding_xp(
                    food_data['base_xp'],
                    food_data['xp_flow'],
                    pet_info.get('favorite_flavor'),
                    pet_info.get('dislike_flavor'),
                    food_data['flavor']
                )

                satiety_gained = FeedingSystem.calculate_satiety_gain()
                current_satiety = FeedingSystem.apply_satiety_gain(current_satiety, satiety_gained)
                current_total_xp += xp_gained

                # 累计统计
                total_xp_gained += xp_gained
                total_satiety_gained += satiety_gained
                total_feeds += 1

                # 记录使用的食粮
                foods_used.append({
                    'name': get_localized_food_name(food_data, locale),
                    'flavor': food_data['flavor'],
                    'rarity': food_data['rarity'],
                    'xp_gained': xp_gained,
                    'flavor_match': food_data['flavor'] == pet_info.get('favorite_flavor')
                })

                # 扣除食粮库存
                inventory_response = supabase.table('user_food_inventory').select('quantity').eq('user_id', user_id).eq('food_template_id', food_data['id']).execute()

                if inventory_response.data:
                    current_quantity = inventory_response.data[0]['quantity']
                    new_quantity = current_quantity - 1

                    if new_quantity > 0:
                        supabase.table('user_food_inventory').update({'quantity': new_quantity}).eq('user_id', user_id).eq('food_template_id', food_data['id']).execute()
                    else:
                        supabase.table('user_food_inventory').delete().eq('user_id', user_id).eq('food_template_id', food_data['id']).execute()

                # 如果饱食度满了就停止
                if current_satiety >= FeedingSystem.SATIETY_MAX:
                    break

        # 计算新等级
        new_level, new_current_xp, new_next_requirement = FeedingSystem.calculate_current_level_xp(current_total_xp)

        # 更新宠物数据
        current_time = datetime.now(timezone.utc)
        update_data = {
            'xp_total': current_total_xp,
            'xp_current': new_current_xp,
            'level': new_level,
            'satiety': current_satiety,
            'last_feeding': current_time.isoformat()
        }

        supabase.table('user_pets').update(update_data).eq('id', pet_id).execute()

        # 检查是否升级
        level_up = new_level > original_level

        # 统计食粮使用情况
        food_summary = {}
        for food in foods_used:
            key = f"{food['name']}"
            if key not in food_summary:
                food_summary[key] = {
                    'count': 0,
                    'xp': 0,
                    'flavor_matches': 0,
                    'rarity': food['rarity'],
                    'flavor': food['flavor']
                }
            food_summary[key]['count'] += 1
            food_summary[key]['xp'] += food['xp_gained']
            if food['flavor_match']:
                food_summary[key]['flavor_matches'] += 1

        return {
            'success': True,
            'total_feeds': total_feeds,
            'total_xp_gained': total_xp_gained,
            'total_satiety_gained': total_satiety_gained,
            'original_level': original_level,
            'new_level': new_level,
            'original_satiety': original_satiety,
            'new_satiety': current_satiety,
            'level_up': level_up,
            'food_summary': food_summary,
            'pet_name': pet_info['name']
        }