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
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS wheel_rewards (
            id INT AUTO_INCREMENT PRIMARY KEY,
            points INT NOT NULL,
            description VARCHAR(255) NOT NULL
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
    
    conn.commit()
    c.close()
    conn.close() 