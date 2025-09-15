import mysql.connector
import datetime
from src.config.config import DB_CONFIG

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)

# 初始化数据库，如果表不存在就创建
def init_db() -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            points INT DEFAULT 0,
            last_draw DATE,
            last_wheel DATE DEFAULT '1970-01-01',
            paid_draws_today INT DEFAULT 0,
            last_paid_draw_date DATE DEFAULT '1970-01-01'
        )
        """
    )
    c.execute("SHOW COLUMNS FROM users LIKE 'last_wheel'")
    if not c.fetchone():
        c.execute(
            "ALTER TABLE users ADD COLUMN last_wheel DATE DEFAULT '1970-01-01'"
        )
    
    c.execute("SHOW COLUMNS FROM users LIKE 'paid_draws_today'")
    if not c.fetchone():
        c.execute(
            "ALTER TABLE users ADD COLUMN paid_draws_today INT DEFAULT 0"
        )
    
    c.execute("SHOW COLUMNS FROM users LIKE 'last_paid_draw_date'")
    if not c.fetchone():
        c.execute(
            "ALTER TABLE users ADD COLUMN last_paid_draw_date DATE DEFAULT '1970-01-01'"
        )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS tags (
            role_id BIGINT PRIMARY KEY,
            price INT NOT NULL
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS quiz_questions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            category VARCHAR(255) NOT NULL,
            question TEXT NOT NULL,
            option1 TEXT NOT NULL,
            option2 TEXT NOT NULL,
            option3 TEXT NOT NULL,
            option4 TEXT NOT NULL,
            answer TINYINT NOT NULL
        )
        """
    )
    # 创建服务器设置表，用于存储语言偏好
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id BIGINT PRIMARY KEY,
            language VARCHAR(10) DEFAULT 'en'
        )
        """
    )
    
    # 玩家蛋库存表
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS player_eggs (
            egg_id INT AUTO_INCREMENT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            egg_code VARCHAR(10) NOT NULL COMMENT '蛋的类型代码（C/R/SR/SSR）',
            status ENUM('待孵化','孵化中','已完成','已领取') DEFAULT '待孵化' COMMENT '蛋的状态',
            start_time DATETIME NULL COMMENT '开始孵化时间',
            end_time DATETIME NULL COMMENT '孵化结束时间',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_user_id (user_id),
            INDEX idx_status (status),
            INDEX idx_egg_code (egg_code)
        )
        """
    )
    
    # 6. 宠物表
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS pets (
            pet_id INT AUTO_INCREMENT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            pet_name VARCHAR(100) NOT NULL,
            rarity VARCHAR(10) NOT NULL COMMENT '稀有度（C/R/SR/SSR）',
            stars INT DEFAULT 0 COMMENT '星级',
            max_stars INT NOT NULL COMMENT '最大星级',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_user_id (user_id),
            INDEX idx_rarity (rarity)
        )
        """
    )
    
    # 7. 宠物模板表
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS pet_templates (
            id INT AUTO_INCREMENT PRIMARY KEY,
            pet_name VARCHAR(100) NOT NULL COMMENT '宠物名称',
            rarity VARCHAR(10) NOT NULL COMMENT '稀有度（C/R/SR/SSR）',
            INDEX idx_rarity (rarity)
        )
        """
    )
    
    # 8. 宠物碎片表
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS pet_fragments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            rarity VARCHAR(10) NOT NULL COMMENT '碎片稀有度（C/R/SR/SSR）',
            amount INT DEFAULT 0 COMMENT '碎片数量',
            UNIQUE KEY unique_user_rarity (user_id, rarity),
            INDEX idx_user_id (user_id)
        )
        """
    )
    
    # 抽蛋概率配置表
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS egg_draw_probabilities (
            id INT AUTO_INCREMENT PRIMARY KEY,
            rarity VARCHAR(10) NOT NULL COMMENT '蛋稀有度（C/R/SR/SSR）',
            probability DECIMAL(5,2) NOT NULL COMMENT '概率（百分比，如70.00表示70%）',
            UNIQUE KEY unique_rarity (rarity)
        )
        """
    )
    
    # 蛋孵化概率配置表
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS egg_hatch_probabilities (
            id INT AUTO_INCREMENT PRIMARY KEY,
            egg_rarity VARCHAR(10) NOT NULL COMMENT '蛋的稀有度（C/R/SR/SSR）',
            pet_rarity VARCHAR(10) NOT NULL COMMENT '孵化出的宠物稀有度（C/R/SR/SSR）',
            probability DECIMAL(5,2) NOT NULL COMMENT '概率（百分比）',
            UNIQUE KEY unique_egg_pet_rarity (egg_rarity, pet_rarity),
            INDEX idx_egg_rarity (egg_rarity)
        )
        """
    )
    
    
    conn.commit()
    c.close()
    conn.close()