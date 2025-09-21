#!/usr/bin/env python3
"""
测试缺失ID检查功能
这个脚本用于验证get_missing_user_id函数是否正常工作
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.db.database import get_missing_user_id, get_connection

def test_missing_id_check():
    """测试缺失ID检查功能"""
    print("🧪 开始测试缺失ID检查功能...")
    
    try:
        # 检查当前缺失的ID
        missing_id = get_missing_user_id()
        
        if missing_id is not None:
            print(f"✅ 发现缺失的ID: {missing_id}")
            print(f"📝 下一个新用户将使用ID: {missing_id}")
        else:
            print("✅ ID 1-6 都已存在，新用户将使用自增长ID")
        
        # 显示当前1-6的ID使用情况
        print("\n📊 当前ID 1-6 的使用情况:")
        supabase = get_connection()
        
        for user_id in range(1, 7):
            response = supabase.table('users').select('id, discord_user_id, guild_id').eq('id', user_id).execute()
            if response.data:
                user_data = response.data[0]
                print(f"  ID {user_id}: ✅ 已使用 (Discord ID: {user_data.get('discord_user_id', 'N/A')})")
            else:
                print(f"  ID {user_id}: ❌ 缺失")
        
        print("\n🎉 测试完成！")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    test_missing_id_check()