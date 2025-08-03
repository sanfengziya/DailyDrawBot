# 语言配置文件
# 这个文件包含了所有支持的语言和它们的翻译文本

# 可用语言列表
AVAILABLE_LANGUAGES = {
    "en": "English",
    "zh": "中文"
}

# 语言文本字典
# 这里存储了所有需要翻译的文本
TRANSLATIONS = {
    # 通用文本
    "common": {
        "en": {
            "error": "An error occurred",
            "success": "Success",
            "permission_denied": "You need administrator permissions to use this command",
            "not_enough_points": "You don't have enough points",
            "invalid_input": "Invalid input"
        },
        "zh": {
            "error": "发生错误",
            "success": "成功",
            "permission_denied": "你需要管理员权限来使用此命令",
            "not_enough_points": "你没有足够的积分",
            "invalid_input": "无效输入"
        }
    },
    
    # 语言设置相关文本
    "language": {
        "en": {
            "language_changed": "Bot language has been changed to {lang_name}",
            "current_language": "Current language: {lang_name}",
            "select_language": "Select a language",
            "language_name": "English"
        },
        "zh": {
            "language_changed": "机器人语言已更改为{lang_name}",
            "current_language": "当前语言：{lang_name}",
            "select_language": "选择一种语言",
            "language_name": "中文"
        }
    },
    
    # 抽奖相关文本
    "draw": {
        "en": {
            "daily_draw": "Daily Draw",
            "draw_success": "You drew {points} points! {message}",
            "draw_cooldown": "You can draw again in {hours} hours and {minutes} minutes",
            "draw_reset": "Draw reset for {user}",
            "all_draws_reset": "All draws have been reset",
            "confirm_reset_all": "Are you sure you want to reset all draws? Type `!resetall confirm` to confirm",
            "database_fixed": "Database has been fixed"
        },
        "zh": {
            "daily_draw": "每日抽奖",
            "draw_success": "你抽到了 {points} 点积分！{message}",
            "draw_cooldown": "你可以在 {hours} 小时 {minutes} 分钟后再次抽奖",
            "draw_reset": "已重置 {user} 的抽奖",
            "all_draws_reset": "所有抽奖已重置",
            "confirm_reset_all": "你确定要重置所有抽奖吗？输入 `!resetall confirm` 确认",
            "database_fixed": "数据库已修复"
        }
    },
    
    # 积分和角色相关文本
    "points_and_roles": {
        "en": {
            "points_check": "{user} has {points} points",
            "points_given": "Given {points} points to {user}",
            "points_set": "Set {user}'s points to {points}",
            "points_gift": "You gifted {points} points to {user}",
            "role_shop": "Role Shop",
            "role_added": "Role {role} added to shop for {price} points",
            "role_purchased": "You purchased the {role} role for {price} points",
            "role_not_found": "Role not found"
        },
        "zh": {
            "points_check": "{user} 有 {points} 点积分",
            "points_given": "已给予 {user} {points} 点积分",
            "points_set": "已将 {user} 的积分设置为 {points}",
            "points_gift": "你赠送了 {points} 点积分给 {user}",
            "role_shop": "角色商店",
            "role_added": "角色 {role} 已添加到商店，价格为 {price} 点积分",
            "role_purchased": "你以 {price} 点积分购买了 {role} 角色",
            "role_not_found": "未找到角色"
        }
    },
    
    # 排行榜相关文本
    "ranking": {
        "en": {
            "ranking_title": "Points Ranking",
            "ranking_description": "Top users by points",
            "rank_display": "#{rank} - {user}: {points} points"
        },
        "zh": {
            "ranking_title": "积分排行榜",
            "ranking_description": "按积分排名的用户",
            "rank_display": "#{rank} - {user}: {points} 点积分"
        }
    },
    
    # 帮助命令相关文本
    "help": {
        "en": {
            "help_title": "Bot Commands",
            "help_description": "List of available commands",
            "command_description": "{command}: {description}"
        },
        "zh": {
            "help_title": "机器人命令",
            "help_description": "可用命令列表",
            "command_description": "{command}: {description}"
        }
    }
}

def get_text(category, key, language, **kwargs):
    """
    获取指定语言的文本
    
    参数:
        category: 文本类别
        key: 文本键
        language: 语言代码
        **kwargs: 格式化参数
        
    返回:
        格式化后的文本字符串
    """
    # 如果语言不存在，使用英语作为后备
    if language not in TRANSLATIONS[category]:
        language = "en"
        
    # 获取文本
    text = TRANSLATIONS[category][language].get(key, TRANSLATIONS[category]["en"].get(key, f"Missing text: {category}.{key}"))
    
    # 应用格式化参数
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            # 如果格式化失败，返回原始文本
            pass
            
    return text 