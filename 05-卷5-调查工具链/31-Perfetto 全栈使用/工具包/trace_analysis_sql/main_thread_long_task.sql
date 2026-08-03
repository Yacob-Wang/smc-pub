-- main_thread_long_task.sql
-- 用途:从 Perfetto trace 中找主线程长任务
-- 适用:卡顿分析、冷启动耗时退化分析
-- 用法:trace_processor --query-file main_thread_long_task.sql trace.pftrace

-- ========== 阈值可调:主线程长任务(默认 > 16ms = 一帧) ==========
-- 16ms 是 Android 60Hz 一帧时间,卡顿阈值通常用 16ms / 33ms(30Hz)
-- 输入 jank 严重时用 50ms 或 100ms

-- 主线程 ID(替换 com.example.app 为你的 app)
WITH main_thread AS (
  SELECT tid
  FROM thread
  WHERE name = 'main'
    AND pid = (
      SELECT pid FROM process WHERE name = 'com.example.app'
    )
),
long_tasks AS (
  SELECT
    s.ts,
    s.dur / 1000.0 AS duration_us,
    s.dur / 1000000.0 AS duration_ms,
    s.name AS task_name,
    s.depth
  FROM slice s
  JOIN main_thread m USING(tid)
  WHERE
    -- 自定义阈值(单位 ns):16ms = 16_000_000 ns
    s.dur > 16000000
    AND s.name NOT LIKE 'Choreographer#doFrame%'  -- 排除帧本身
)
SELECT
  -- 时间换算(相对 trace 开始时间,秒)
  (ts - (SELECT MIN(ts) FROM slice)) / 1000000000.0 AS time_offset_s,
  duration_ms,
  task_name
FROM long_tasks
ORDER BY duration_ms DESC
LIMIT 30;

-- ========== 任务耗时分布(P50 / P90 / P99) ==========
WITH main_thread AS (
  SELECT tid FROM thread
  WHERE name = 'main'
    AND pid = (SELECT pid FROM process WHERE name = 'com.example.app')
),
task_durations AS (
  SELECT s.dur / 1000000.0 AS duration_ms
  FROM slice s
  JOIN main_thread m USING(tid)
  WHERE s.dur > 0
)
SELECT
  printf('%.2f', PERCENTILE(duration_ms, 50)) AS p50_ms,
  printf('%.2f', PERCENTILE(duration_ms, 90)) AS p90_ms,
  printf('%.2f', PERCENTILE(duration_ms, 99)) AS p99_ms,
  printf('%.2f', MAX(duration_ms)) AS max_ms,
  COUNT(*) AS total_tasks,
  SUM(CASE WHEN duration_ms > 16 THEN 1 ELSE 0 END) AS jank_tasks,
  printf('%.1f%%', 100.0 * SUM(CASE WHEN duration_ms > 16 THEN 1 ELSE 0 END) / COUNT(*)) AS jank_rate
FROM task_durations;

-- ========== 按任务类型聚合 ==========
WITH main_thread AS (
  SELECT tid FROM thread
  WHERE name = 'main'
    AND pid = (SELECT pid FROM process WHERE name = 'com.example.app')
)
SELECT
  CASE
    WHEN s.name LIKE '%onCreate%' THEN 'Lifecycle.onCreate'
    WHEN s.name LIKE '%onResume%' THEN 'Lifecycle.onResume'
    WHEN s.name LIKE '%onMeasure%' THEN 'View.onMeasure'
    WHEN s.name LIKE '%onLayout%' THEN 'View.onLayout'
    WHEN s.name LIKE '%onDraw%' THEN 'View.onDraw'
    WHEN s.name LIKE '%bind%' THEN 'Binder'
    WHEN s.name LIKE '%IO%' OR s.name LIKE '%FileInputStream%' THEN 'IO'
    WHEN s.name LIKE '%GC%' OR s.name LIKE '%garbage%' THEN 'GC'
    ELSE 'Other'
  END AS task_category,
  COUNT(*) AS count,
  printf('%.2f', SUM(s.dur) / 1000000.0) AS total_ms,
  printf('%.2f', AVG(s.dur) / 1000000.0) AS avg_ms,
  printf('%.2f', MAX(s.dur) / 1000000.0) AS max_ms
FROM slice s
JOIN main_thread m USING(tid)
WHERE s.dur > 1000000  -- > 1ms
GROUP BY task_category
ORDER BY total_ms DESC;
