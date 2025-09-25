"""
宠物喂食系统核心功能
包含经验计算、等级管理、饱食度管理等功能
"""

import random
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from enum import Enum

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
    async def purchase_food(user_id: int, food_template_id: int, quantity: int = 1) -> tuple[bool, list]:
        """
        购买食物

        Args:
            user_id: 用户内部ID
            food_template_id: 食物模板ID
            quantity: 购买数量

        Returns:
            tuple: (success, message)
        """
        from src.db.database import get_supabase_client
        from datetime import date

        supabase = get_supabase_client()
        today = date.today()

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
        'C': 0.45,    # 48%
        'R': 0.35,    # 40%
        'SR': 0.15,   # 10%
        'SSR': 0.5   # 2%
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
            if not all(key in template for key in ['id', 'name', 'rarity', 'flavor', 'price', 'base_xp']):
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
        used_flavors = set()
        generation_attempts = 0
        max_attempts = 50  # 防止无限循环

        # 生成5个商品，尽量保证口味多样性
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

            # 从该稀有度中选择食粮
            available_foods = rarity_groups.get(selected_rarity, [])
            if not available_foods:
                continue

            # 优先选择新口味
            new_flavor_foods = [f for f in available_foods if f['flavor'] not in used_flavors]
            if new_flavor_foods:
                selected_food = random.choice(new_flavor_foods)
            else:
                selected_food = random.choice(available_foods)

            # 验证选中的食粮
            if not selected_food.get('id'):
                print(f"⚠️ 跳过无效的食粮数据: {selected_food}")
                continue

            selected_items.append({
                'food_template_id': selected_food['id'],
                'food_data': selected_food
            })

            used_flavors.add(selected_food['flavor'])
            print(f"✅ 选择了{selected_rarity}级食粮: {selected_food['name']} ({selected_food['flavor']})")

        if len(selected_items) != FoodShopManager.DAILY_ITEMS_COUNT:
            print(f"⚠️ 商品生成不完整，期望{FoodShopManager.DAILY_ITEMS_COUNT}个，实际{len(selected_items)}个，尝试次数: {generation_attempts}")
            if len(selected_items) == 0:
                return []

        print(f"🎯 商品生成完成，共{len(selected_items)}个商品，口味种类: {len(used_flavors)}")
        return selected_items

    @staticmethod
    def refresh_daily_shop():
        """刷新每日杂货铺目录（原子性操作，避免商店清空）"""
        from src.db.database import get_supabase_client
        from datetime import date

        supabase = get_supabase_client()
        today = date.today()
        today_str = today.isoformat()

        try:
            print(f"🏪 开始刷新杂货铺 - {today_str}")

            # 1. 生成新目录条目并验证
            new_items = FoodShopManager.generate_daily_shop_items()

            if not new_items:
                print("❌ 商品生成失败，跳过刷新以保护现有商店数据")
                return []

            # 2. 构建新目录数据并验证完整性
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

            # 3. 备份当前商店数据（用于回滚）
            backup_response = supabase.table('daily_shop_catalog').select('*').eq('refresh_date', today_str).execute()
            backup_data = backup_response.data if backup_response.data else []
            print(f"📦 备份了{len(backup_data)}条现有商店数据")

            # 4. 原子性更新：先删除再插入
            try:
                # 删除今日旧目录
                delete_result = supabase.table('daily_shop_catalog').delete().eq('refresh_date', today_str).execute()
                print(f"🗑️ 清理旧目录完成，删除了{len(delete_result.data) if delete_result.data else 0}条记录")

                # 插入新目录
                insert_result = supabase.table('daily_shop_catalog').insert(catalog_rows).execute()

                if not insert_result.data or len(insert_result.data) != len(catalog_rows):
                    raise Exception(f"插入失败：期望{len(catalog_rows)}条，实际{len(insert_result.data) if insert_result.data else 0}条")

                print(f"✅ 新目录插入成功，共{len(insert_result.data)}种商品")
                print("🏪 杂货铺刷新完成！")

            except Exception as db_error:
                print(f"❌ 数据库操作失败: {db_error}")

                # 尝试回滚：恢复备份数据
                if backup_data:
                    try:
                        print("🔄 尝试回滚到备份数据...")
                        supabase.table('daily_shop_catalog').insert(backup_data).execute()
                        print("✅ 回滚成功，商店数据已恢复")
                        return []  # 返回空列表表示刷新失败但已回滚
                    except Exception as rollback_error:
                        print(f"❌ 回滚失败: {rollback_error}")

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
                print(f"   {i}. {food_data['rarity']} - {food_data['name']} ({food_data['flavor']}) - {food_data['price']}积分")
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

def get_pet_feeding_info(pet_id: int) -> Optional[Dict]:
    """获取宠物喂食相关信息"""
    from src.db.database import get_supabase_client

    supabase = get_supabase_client()

    # 获取宠物信息
    response = supabase.table('user_pets').select('''
        id, user_id, level, xp_current, xp_total,
        favorite_flavor, dislike_flavor, satiety, last_feeding,
        pet_templates(name, rarity)
    ''').eq('id', pet_id).execute()

    if not response.data:
        return None

    pet_data = response.data[0]

    # 计算等级信息
    level, current_level_xp, next_level_requirement = FeedingSystem.calculate_current_level_xp(pet_data['xp_total'])

    return {
        'id': pet_data['id'],
        'user_id': pet_data['user_id'],
        'name': pet_data['pet_templates']['name'],
        'rarity': pet_data['pet_templates']['rarity'],
        'level': level,
        'xp_current': current_level_xp,
        'xp_total': pet_data['xp_total'],
        'xp_next_level': next_level_requirement,
        'favorite_flavor': pet_data['favorite_flavor'],
        'dislike_flavor': pet_data['dislike_flavor'],
        'satiety': pet_data['satiety'],
        'last_feeding': pet_data['last_feeding']
    }

def feed_pet(pet_id: int, food_template_id: int) -> Dict:
    """
    执行宠物喂食
    返回喂食结果信息
    """
    from src.db.database import get_supabase_client

    supabase = get_supabase_client()

    # 获取宠物信息
    pet_info = get_pet_feeding_info(pet_id)
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
        'food_name': food_data['name'],
        'pet_name': pet_info['name']
    }