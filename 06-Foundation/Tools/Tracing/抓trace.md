cat > boottrace.pbtxt << EOF
buffers {
size_kb: 65536
fill_policy: DISCARD
}

data_sources {
config {
name: "linux.ftrace"
target_buffer: 0
ftrace_config {
# Atrace categories
atrace_categories: "adb"
atrace_categories: "aidl"
atrace_categories: "am"
atrace_categories: "audio"
atrace_categories: "binder_driver"
atrace_categories: "binder_lock"
atrace_categories: "bionic"
atrace_categories: "camera"
atrace_categories: "dalvik"
atrace_categories: "database"
atrace_categories: "gfx"
atrace_categories: "hal"
atrace_categories: "input"
atrace_categories: "network"
atrace_categories: "nnapi"
atrace_categories: "pm"
atrace_categories: "power"
atrace_categories: "res"
atrace_categories: "rro"
atrace_categories: "rs"
atrace_categories: "sm"
atrace_categories: "ss"
atrace_categories: "vibrator"
atrace_categories: "video"
atrace_categories: "view"
atrace_categories: "webview"
atrace_categories: "wm"

      # Sched events - 使用完整路径
      ftrace_events: "sched/sched_switch"
      ftrace_events: "sched/sched_waking"
      ftrace_events: "sched/sched_wakeup_new"
      ftrace_events: "sched/task_newtask"
      ftrace_events: "sched/task_rename"
      ftrace_events: "sched/sched_process_exit"
      ftrace_events: "sched/sched_process_fork"
      ftrace_events: "sched/sched_process_free"
      # 先注释掉可能有问题的事件
      # ftrace_events: "sched/sched_process_exec"
      # ftrace_events: "sched/sched_process_hang"
      # ftrace_events: "sched/sched_process_wait"
      
      # Block events - 逐个指定而不是用通配符
      ftrace_events: "block/*"
    }
}
}

data_sources {
config {
name: "linux.process_stats"
target_buffer: 0
}
}

duration_ms: 40000
EOF



su
setprop persist.debug.perfetto.boottrace 1

setprop persist.traced.enable 1

---分割线--=

perfetto \
-o /data/local/tmp/pef.trace \
--duration 30s \
--data-source linux.block \
--data-source linux.task \
--data-source linux.syscalls
  
  

