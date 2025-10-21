-- ===================================================
-- 排行榜系统 - Supabase RPC 函数
-- ===================================================
-- 这些函数用于支持各种类型的排行榜查询
-- 包括：宠物数量、21点胜场、21点盈利
-- ===================================================

-- 1. 宠物数量排行榜
-- 统计每个用户拥有的宠物总数
CREATE OR REPLACE FUNCTION get_pet_count_ranking(
    p_guild_id BIGINT,
    p_limit INTEGER DEFAULT 30
)
RETURNS TABLE (
    discord_user_id TEXT,
    pet_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        u.discord_user_id::TEXT,
        COUNT(p.id) as pet_count
    FROM users u
    LEFT JOIN user_pets p ON u.id = p.user_id
    WHERE u.guild_id = p_guild_id
    GROUP BY u.discord_user_id
    HAVING COUNT(p.id) > 0
    ORDER BY pet_count DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- 2. 21点胜场排行榜
-- 统计每个用户的21点胜场总数
CREATE OR REPLACE FUNCTION get_blackjack_wins_ranking(
    p_guild_id BIGINT,
    p_limit INTEGER DEFAULT 30
)
RETURNS TABLE (
    discord_user_id TEXT,
    total_wins BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        u.discord_user_id::TEXT,
        COUNT(
            CASE
                WHEN bg.result IN ('win', 'blackjack') THEN 1
                ELSE NULL
            END
        ) as total_wins
    FROM users u
    LEFT JOIN blackjack_games bg ON u.id = bg.user_id
    WHERE u.guild_id = p_guild_id
    GROUP BY u.discord_user_id
    HAVING COUNT(
        CASE
            WHEN bg.result IN ('win', 'blackjack') THEN 1
            ELSE NULL
        END
    ) > 0
    ORDER BY total_wins DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- 3. 21点总盈利排行榜
-- 统计每个用户在21点游戏中的总盈利（包括负数）
CREATE OR REPLACE FUNCTION get_blackjack_profit_ranking(
    p_guild_id BIGINT,
    p_limit INTEGER DEFAULT 30
)
RETURNS TABLE (
    discord_user_id TEXT,
    total_profit BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        u.discord_user_id::TEXT,
        COALESCE(SUM(bg.profit), 0) as total_profit
    FROM users u
    LEFT JOIN blackjack_games bg ON u.id = bg.user_id
    WHERE u.guild_id = p_guild_id
    GROUP BY u.discord_user_id
    HAVING COALESCE(SUM(bg.profit), 0) > 0
    ORDER BY total_profit DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- ===================================================
-- 使用说明
-- ===================================================
-- 在 Supabase Dashboard 中执行这些函数创建语句
--
-- 测试示例：
-- SELECT * FROM get_pet_count_ranking('YOUR_GUILD_ID', 10);
-- SELECT * FROM get_blackjack_wins_ranking('YOUR_GUILD_ID', 10);
-- SELECT * FROM get_blackjack_profit_ranking('YOUR_GUILD_ID', 10);
-- ===================================================
