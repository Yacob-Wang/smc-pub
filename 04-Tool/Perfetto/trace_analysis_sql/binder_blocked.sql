-- binder_blocked.sql
-- 用途:从 Perfetto trace 中找 Binder 阻塞的主线程
-- 适用:ANR 分析、Input 延迟分析
-- 用法:trace_processor --query-file binder_blocked.sql trace.pftrace

-- ========== 主线程的 binder transaction 时间窗口 ==========
WITH main_thread AS (
  SELECT tid
  FROM thread
  WHERE name = 'main'
    AND pid = (
      SELECT pid FROM process
      WHERE name = 'com.example.app'  -- 替换为你的 app 包名
    )
)
SELECT
  s.ts AS start_ts,
  s.dur AS duration_us,
  s.name AS binder_call,
  s.depth
FROM slice s
JOIN main_thread m USING(tid)
WHERE
  s.name LIKE '%binder%'
  OR s.name LIKE '%IPC%'
  OR s.name LIKE '%transact%'
ORDER BY s.dur DESC
LIMIT 20;

-- ========== 阻塞超过 1s 的 binder 调用 ==========
SELECT
  ts,
  dur / 1000000.0 AS duration_ms,
  name,
  tid,
  (SELECT name FROM thread WHERE tid = s.tid) AS thread_name
FROM slice s
WHERE
  (name LIKE '%binder%' OR name LIKE '%IPC%')
  AND dur > 1000000000  -- > 1s
ORDER BY dur DESC
LIMIT 30;

-- ========== binder 调用链端到端追踪 ==========
WITH RECURSIVE binder_chain AS (
  -- 起点:app 主线程的 binder 入口
  SELECT
    s.id,
    s.ts,
    s.dur,
    s.name,
    s.tid,
    s.depth,
    1 AS level
  FROM slice s
  WHERE
    s.name LIKE '%binder%'
    AND s.tid = (
      SELECT tid FROM thread
      WHERE name = 'main'
        AND pid = (SELECT pid FROM process WHERE name = 'com.example.app')
    )
    AND s.ts BETWEEN 1700000000000000000 AND 1700001000000000000  -- 时间窗口

  UNION ALL

  -- 递归:同一时间范围内的子 slice
  SELECT
    s.id,
    s.ts,
    s.dur,
    s.name,
    s.tid,
    s.depth,
    bc.level + 1
  FROM slice s
  JOIN binder_chain bc
    ON s.ts BETWEEN bc.ts AND bc.ts + bc.dur
    AND s.tid != bc.tid  -- 跨线程
)
SELECT * FROM binder_chain ORDER BY ts, level LIMIT 100;
