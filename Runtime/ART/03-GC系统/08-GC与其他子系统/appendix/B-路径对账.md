# 附录 B：路径对账（GC 与其他子系统）

## 一、AOSP 版本

| 维度 | 版本 |
|:---|:---|
| **AOSP 分支** | android14-release / master |
| **API Level** | 34 |

## 二、调试命令

```bash
# 1. JNI 相关
adb shell dumpsys meminfo <package> | grep "JNI"

# 2. Hook 相关
adb logcat -s "art" | grep "Invariant\|Hook"

# 3. Zygote / System Server
adb shell ps -A | grep "zygote\|system_server"
adb shell dumpsys meminfo system_server

# 4. 输入法 / SurfaceFlinger
adb shell dumpsys input_method
adb shell dumpsys SurfaceFlinger

# 5. ART 模块
adb shell cmd apd list
```
