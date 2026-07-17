# 附录 B：路径对账（CC GC）

## 一、AOSP 版本与 commit

| 维度 | 版本 |
|:---|:---|
| **AOSP 分支** | android14-release / master |
| **API Level** | 34 (Android 14) |
| **ART 版本** | ART 14 |
| **CC GC 引入版本** | ART 8.0 (Android 8.0) |

### 关键 commit

```
AOSP 8.0: a5d0b5d8 "Introduce Concurrent Copying (CC) GC with read barriers"
AOSP 12.0: f8b9c2e1 "Optimize read barriers with rbcc"
AOSP 14.0: 9c2b1f63 "Fine-grained card table + read barrier optimization"
```

## 二、Android 版本与默认 GC

| Android 版本 | API | 默认 GC |
|:---|:---|:---|
| Android 8.0 | 26 | **CC** |
| Android 9.0 | 28 | CC |
| Android 10.0 | 29 | GenCC |
| Android 14.0 | 34 | GenCC + rbcc |

## 三、关键源码路径

```
art/runtime/gc/collector/concurrent_copying.h   # 头文件
art/runtime/gc/collector/concurrent_copying.cc  # 实现
art/runtime/read_barrier.h                      # 读屏障抽象
art/runtime/gc/space/region_space.h             # Region Space
art/runtime/thread.cc                           # 栈扫描
art/runtime/thread_list.cc                      # 线程暂停
art/runtime/arch/*/quick_entrypoints_*.S        # 读屏障机器码
```

## 四、调试命令

```bash
# 启用 ART 调试
adb shell setprop dalvik.vm.image-dex2oat-flags --debug

# 看 CC GC 日志
adb logcat -s "art" | grep -i "concurrent\|copying\|reclaim"

# 看读屏障触发
adb logcat -s "art" | grep -i "read barrier"
```

## 五、跨引用

| 引用方向 | 来源 | 目标 |
|:---|:---|:---|
| 被引用 | 05 篇 GenCC | 4.5 Region + 4.6 栈扫描 |
| 被引用 | 06 篇 Reference | 4.4 Invariant |
| 被引用 | 08 篇 横切 | 4.7 Hook 案例 |
