# 附录 B：路径对账（GenCC）

## 一、AOSP 版本

| 维度 | 版本 |
|:---|:---|
| **AOSP 分支** | android14-release / master |
| **API Level** | 34 |
| **GenCC 引入版本** | ART 10.0 (Android 10) |

### 关键 commit

```
AOSP 10.0: e1c3a44 "Add generational support to Concurrent Copying GC"
AOSP 12.0: f8b9c2e "Optimize read barriers with rbcc"
AOSP 14.0: 9c2b1f6 "Fine-grained card table + adaptive promotion"
```

## 二、Android 版本与默认 GC

| Android | API | 默认 GC |
|:---|:---|:---|
| Android 10.0 | 29 | **GenCC** |
| Android 11.0 | 30 | GenCC |
| Android 14.0 | 34 | GenCC + rbcc |

## 三、关键源码路径

```
art/runtime/gc/collector/concurrent_copying.{h,cc}
art/runtime/gc/space/region_space.{h,cc}
art/runtime/gc/heap.{h,cc}
art/runtime/write_barrier.{h,cc}
```

## 四、调试命令

```bash
# 看 Minor GC
adb logcat -s "art" | grep "minor GC"

# 看晋升
adb logcat -s "art" | grep "Promote"

# 看 dirty card
adb logcat -s "art" | grep "Card"

# 看 GenCC 触发
adb logcat -s "art" | grep "kGcCauseForAlloc\|kGcCauseBackground"
```
