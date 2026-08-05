-- leak_pattern_match.sql
-- LeakCanary 报告 + hprof 报告 模式匹配查询
--
-- 用途:
--   - 解析 LeakCanary 上报的 hprof 报告
--   - 用 SQL 模式匹配识别常见泄漏场景
--   - 统计 + 归类 + 自动提单依据
--
-- 适用:
--   - 服务端解析 hprof 后入库到 ES / ClickHouse
--   - 或直接对 hprof-converted Parquet 文件查询
--
-- 配套文档:Android_Framework_Layer/Hprof/05-实战：内存监控体系搭建.md §4.3

-- ============================================================================
-- 1. 找出所有 Activity 泄漏
-- ============================================================================
-- 用法:替换 'com.example.app.HomeActivity' 为目标 Activity 类名
SELECT
    leak_id,
    class_name,
    retained_size_kb,
    reference_chain,
    -- 提取引用链中的关键节点
    REGEXP_EXTRACT(reference_chain, r'static field ([^\s→]+)', 1) AS static_field,
    REGEXP_EXTRACT(reference_chain, r'([a-zA-Z0-9_.$]+)\$[0-9]+', 1) AS inner_class,
    REGEXP_EXTRACT(reference_chain, r'(com\.example\.thirdparty\.[a-zA-Z0-9_.]+)', 1) AS third_party_sdk
FROM leak_reports
WHERE class_name LIKE '%Activity'
  AND retained_size_kb > 1000  -- > 1MB
ORDER BY retained_size_kb DESC
LIMIT 100;

-- ============================================================================
-- 2. 泄漏模式分类统计
-- ============================================================================
SELECT
    CASE
        WHEN reference_chain LIKE '%static field%' THEN 'static_field'
        WHEN reference_chain LIKE '%Handler%' OR reference_chain LIKE '%MessageQueue%' THEN 'handler_message'
        WHEN reference_chain LIKE '%WebView%' THEN 'webview'
        WHEN reference_chain LIKE '%ViewModel%' AND reference_chain LIKE '%Context%' THEN 'fragment_viewmodel'
        WHEN reference_chain LIKE '%EventBus%' THEN 'eventbus'
        WHEN reference_chain LIKE '%BroadcastReceiver%' OR reference_chain LIKE '%IntentReceiver%' THEN 'register_receiver'
        WHEN reference_chain LIKE '%HashMap%' OR reference_chain LIKE '%LruCache%' THEN 'static_collection'
        WHEN reference_chain LIKE '%Bitmap%' THEN 'bitmap_cache'
        ELSE 'unknown'
    END AS leak_pattern,
    COUNT(*) AS leak_count,
    SUM(retained_size_kb) / 1024 AS total_retained_mb,
    AVG(retained_size_kb) / 1024 AS avg_retained_mb,
    MAX(retained_size_kb) / 1024 AS max_retained_mb
FROM leak_reports
WHERE created_at > DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY leak_pattern
ORDER BY total_retained_mb DESC;

-- ============================================================================
-- 3. TOP 20 累计 retained size 泄漏
-- ============================================================================
SELECT
    class_name,
    COUNT(*) AS leak_count,
    SUM(retained_size_kb) / 1024 AS total_retained_mb,
    AVG(retained_size_kb) / 1024 AS avg_retained_mb,
    MAX(retained_size_kb) / 1024 AS max_retained_mb,
    -- 最近一次出现
    MAX(created_at) AS last_seen
FROM leak_reports
WHERE created_at > DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY class_name
HAVING SUM(retained_size_kb) > 10 * 1024  -- 累计 > 10MB
ORDER BY total_retained_mb DESC
LIMIT 20;

-- ============================================================================
-- 4. 已知泄漏 vs 未知泄漏
-- ============================================================================
SELECT
    CASE
        WHEN leak_pattern = 'unknown' THEN '未知'
        ELSE '已知'
    END AS leak_type,
    COUNT(*) AS leak_count,
    SUM(retained_size_kb) / 1024 AS total_retained_mb
FROM (
    SELECT
        CASE
            WHEN reference_chain LIKE '%static field%' THEN 'static_field'
            WHEN reference_chain LIKE '%Handler%' OR reference_chain LIKE '%MessageQueue%' THEN 'handler_message'
            WHEN reference_chain LIKE '%WebView%' THEN 'webview'
            WHEN reference_chain LIKE '%ViewModel%' AND reference_chain LIKE '%Context%' THEN 'fragment_viewmodel'
            WHEN reference_chain LIKE '%EventBus%' THEN 'eventbus'
            WHEN reference_chain LIKE '%BroadcastReceiver%' OR reference_chain LIKE '%IntentReceiver%' THEN 'register_receiver'
            WHEN reference_chain LIKE '%HashMap%' OR reference_chain LIKE '%LruCache%' THEN 'static_collection'
            WHEN reference_chain LIKE '%Bitmap%' THEN 'bitmap_cache'
            ELSE 'unknown'
        END AS leak_pattern,
        retained_size_kb
    FROM leak_reports
    WHERE created_at > DATE_SUB(NOW(), INTERVAL 7 DAY)
) t
GROUP BY leak_type;

-- ============================================================================
-- 5. 趋势分析:每周新增泄漏数
-- ============================================================================
SELECT
    DATE_TRUNC('week', created_at) AS week,
    COUNT(*) AS new_leaks,
    SUM(retained_size_kb) / 1024 AS new_retained_mb,
    -- 已知 vs 未知
    SUM(CASE WHEN leak_pattern != 'unknown' THEN 1 ELSE 0 END) AS known_leaks,
    SUM(CASE WHEN leak_pattern = 'unknown' THEN 1 ELSE 0 END) AS unknown_leaks
FROM (
    SELECT
        *,
        CASE
            WHEN reference_chain LIKE '%static field%' THEN 'static_field'
            WHEN reference_chain LIKE '%Handler%' OR reference_chain LIKE '%MessageQueue%' THEN 'handler_message'
            WHEN reference_chain LIKE '%WebView%' THEN 'webview'
            WHEN reference_chain LIKE '%ViewModel%' AND reference_chain LIKE '%Context%' THEN 'fragment_viewmodel'
            ELSE 'unknown'
        END AS leak_pattern
    FROM leak_reports
) t
WHERE created_at > DATE_SUB(NOW(), INTERVAL 90 DAY)
GROUP BY week
ORDER BY week DESC;

-- ============================================================================
-- 6. 版本对比:每个 app 版本的泄漏变化
-- ============================================================================
SELECT
    app_version,
    COUNT(*) AS leak_count,
    SUM(retained_size_kb) / 1024 AS total_retained_mb,
    -- 与上一版本对比
    LAG(SUM(retained_size_kb) / 1024) OVER (ORDER BY app_version) AS prev_version_retained_mb,
    (SUM(retained_size_kb) / 1024) - LAG(SUM(retained_size_kb) / 1024) OVER (ORDER BY app_version) AS retained_diff_mb
FROM leak_reports
WHERE created_at > DATE_SUB(NOW(), INTERVAL 60 DAY)
GROUP BY app_version
ORDER BY app_version DESC;

-- ============================================================================
-- 7. 设备 / 系统维度分析
-- ============================================================================
SELECT
    os_version,
    device_manufacturer,
    COUNT(*) AS leak_count,
    SUM(retained_size_kb) / 1024 AS total_retained_mb,
    AVG(retained_size_kb) / 1024 AS avg_retained_mb
FROM leak_reports
WHERE created_at > DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY os_version, device_manufacturer
HAVING COUNT(*) >= 5
ORDER BY leak_count DESC
LIMIT 20;

-- ============================================================================
-- 8. 告警规则:严重泄漏(应立即处理)
-- ============================================================================
SELECT
    leak_id,
    class_name,
    app_version,
    os_version,
    retained_size_kb / 1024 AS retained_mb,
    reference_chain
FROM leak_reports
WHERE
    -- P0 条件:任一满足
    (
        retained_size_kb > 100 * 1024  -- > 100MB
        OR
        -- 已知严重模式 + 大小
        (
            reference_chain LIKE '%static field%'
            AND retained_size_kb > 50 * 1024  -- > 50MB
        )
    )
    AND created_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
ORDER BY retained_size_kb DESC;

-- ============================================================================
-- 9. 重复泄漏检测:同一类名 + 相似引用链
-- ============================================================================
SELECT
    class_name,
    -- 简化引用链(去掉实例 ID)
    REGEXP_REPLACE(
        REGEXP_REPLACE(reference_chain, r'@[a-f0-9]+', ''),
        r'\$[0-9]+',
        ''
    ) AS simplified_chain,
    COUNT(*) AS occurrences,
    SUM(retained_size_kb) / 1024 AS total_retained_mb,
    MIN(created_at) AS first_seen,
    MAX(created_at) AS last_seen
FROM leak_reports
WHERE created_at > DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY class_name, simplified_chain
HAVING COUNT(*) >= 3  -- 出现 3 次以上
ORDER BY occurrences DESC;

-- ============================================================================
-- 10. 修复跟踪:已修 vs 未修
-- ============================================================================
SELECT
    CASE
        WHEN fixed_at IS NOT NULL THEN '已修'
        WHEN status = 'wont_fix' THEN '不修'
        WHEN status = 'in_progress' THEN '修复中'
        ELSE '待处理'
    END AS fix_status,
    COUNT(*) AS leak_count,
    SUM(retained_size_kb) / 1024 AS total_retained_mb,
    AVG(DATEDIFF('day', created_at, COALESCE(fixed_at, NOW()))) AS avg_age_days
FROM leak_reports
WHERE created_at > DATE_SUB(NOW(), INTERVAL 90 DAY)
GROUP BY fix_status
ORDER BY total_retained_mb DESC;