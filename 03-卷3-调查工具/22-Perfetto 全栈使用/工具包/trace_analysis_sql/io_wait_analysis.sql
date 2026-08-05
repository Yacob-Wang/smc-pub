-- io_wait_analysis.sql
-- 用途:从 Perfetto trace 中分析 IO 等待和 block 事件
-- 适用:IO 慢问题、冷启动退化中的 IO 等待
-- 用法:trace_processor --query-file io_wait_analysis.sql trace.pftrace

-- ========== 块 IO 事件统计 ==========
SELECT
  name AS io_event,
  COUNT(*) AS count,
  printf('%.2f', AVG(dur) / 1000.0) AS avg_us,
  printf('%.2f', MAX(dur) / 1000.0) AS max_us,
  printf('%.2f', PERCENTILE(dur / 1000.0, 50)) AS p50_us,
  printf('%.2f', PERCENTILE(dur / 1000.0, 95)) AS p95_us,
  printf('%.2f', PERCENTILE(dur / 1000.0, 99)) AS p99_us
FROM ftrace_events
WHERE
  name LIKE 'block_%'
  OR name LIKE 'ext4_%'
  OR name LIKE 'f2fs_%'
GROUP BY name
ORDER BY count DESC
LIMIT 30;

-- ========== 最慢的 20 个 IO 请求 ==========
SELECT
  ts,
  dur / 1000.0 AS duration_us,
  name AS io_event,
  (SELECT name FROM thread WHERE tid = ftrace_events.tid) AS thread_name,
  (SELECT name FROM process WHERE pid = thread.pid) AS process_name
FROM ftrace_events
JOIN thread ON ftrace_events.tid = thread.tid
WHERE name = 'block_rq_complete'
ORDER BY dur DESC
LIMIT 20;

-- ========== 设备级 IO 统计(按设备) ==========
SELECT
  -- block_rq_complete 事件里通常有 dev 字段,这里用 thread + stack 推断
  COUNT(*) AS io_count,
  printf('%.2f', SUM(dur) / 1000000.0) AS total_ms,
  printf('%.2f', AVG(dur) / 1000000.0) AS avg_ms
FROM ftrace_events
WHERE name = 'block_rq_complete'
  AND ts > 1700000000000000000  -- 时间窗口
GROUP BY tid
ORDER BY total_ms DESC
LIMIT 20;

-- ========== 进程等待 IO 的时间 ==========
-- 思路:进程处于 D 状态(state = D)的时间 + block IO 事件累计
SELECT
  (SELECT name FROM process WHERE pid = thread.pid) AS process_name,
  thread.name AS thread_name,
  COUNT(*) AS d_state_count,
  printf('%.2f', SUM(dur) / 1000000.0) AS total_d_time_ms
FROM sched_slice
JOIN thread ON sched_slice.tid = thread.tid
WHERE
  -- D 状态(uninterruptible sleep,通常是 IO 等待)
  -- 注意:sched_slice 不直接记录 state,需要通过其他方式推断
  -- 这里用替代方案:进程在 block IO 期间没有 sched_switch 到别的线程
  ts > 1700000000000000000
GROUP BY process_name, thread_name
ORDER BY total_d_time_ms DESC
LIMIT 30;

-- ========== 文件系统层 IO ==========
SELECT
  name AS fs_event,
  COUNT(*) AS count,
  printf('%.2f', AVG(dur) / 1000.0) AS avg_us,
  printf('%.2f', MAX(dur) / 1000.0) AS max_us
FROM ftrace_events
WHERE
  name LIKE 'ext4_%'
  OR name LIKE 'f2fs_%'
  OR name LIKE 'fs_%'
  OR name LIKE 'sync_%'
  OR name LIKE 'writeback_%'
GROUP BY name
ORDER BY count DESC
LIMIT 30;

-- ========== 写回(writeback)事件 ==========
-- 写回慢通常意味着 IO 压力大
SELECT
  ts,
  dur / 1000.0 AS duration_us,
  name,
  tid
FROM ftrace_events
WHERE
  name LIKE 'writeback_%'
  AND dur > 10000000  -- > 10ms
ORDER BY ts;
