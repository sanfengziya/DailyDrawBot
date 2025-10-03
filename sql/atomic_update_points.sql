-- 原子性积分更新函数
-- 解决并发更新积分时的丢失更新问题

CREATE OR REPLACE FUNCTION atomic_update_points(
    p_user_id INTEGER,
    p_delta INTEGER
)
RETURNS TABLE(new_points INTEGER) AS $$
BEGIN
    -- 使用单个UPDATE语句原子性更新并返回新值
    -- GREATEST确保积分不会为负数
    RETURN QUERY
    UPDATE users
    SET points = GREATEST(0, points + p_delta)
    WHERE id = p_user_id
    RETURNING points;
END;
$$ LANGUAGE plpgsql;

-- 使用示例:
-- SELECT * FROM atomic_update_points(42, 100);  -- 增加100积分
-- SELECT * FROM atomic_update_points(42, -50);  -- 减少50积分

-- 回滚函数 (如果需要删除):
-- DROP FUNCTION IF EXISTS atomic_update_points(INTEGER, INTEGER);
