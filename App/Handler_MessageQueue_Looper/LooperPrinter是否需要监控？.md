你好！我是 TranAI。

既然你是 **Framework 工程师**，那我们就可以抛开应用开发的限制，直接用**系统级（System Level）**和**调试级（Debug Level）**的手段来解决这个问题。

虽然 AOSP 默认没有提供一个简单的 `adb shell setprop` 开关来直接开启 Logcat 中的 `>>>>> Dispatching` 日志（因为这会产生巨大的日志量，严重影响性能），但作为 Framework 工程师，你有以下**三种**硬核方法可以手动开启它：

---

### 方法一：利用 JDB 动态注入（最推荐，免重新编译）

如果你的设备是 `userdebug` 或 `eng` 版本（`ro.debuggable=1`），你可以利用 **JDB (Java Debugger)** 通过命令行动态地“执行”一句代码，把 `Printer` 塞进去。

**原理：** 通过 JDWP 协议连接到目标进程，强制执行 `Looper.getMainLooper().setMessageLogging(...)`。

**步骤：**

1.  **找到目标进程 PID：**
    ```bash
    adb shell pidof com.example.app
    # 假设 PID 是 12345
    ```

2.  **设置端口转发：**
    ```bash
    adb forward tcp:54321 jdwp:12345
    ```

3.  **连接 JDB 并注入代码：**
    在电脑终端执行：
    ```bash
    jdb -attach localhost:54321
    ```
    等待出现 `>` 提示符后，输入以下命令（注意大小写和包名）：
    ```java
    # 1. 获取主线程 Looper
    > classes
    > stop in android.os.Looper.loop
    # (这里可能不需要 stop，直接执行下句即可，视 jdb 版本而定，通常直接 evaluate 即可)
    
    # 直接执行设置 Printer 的代码
    # android.util.LogPrinter 是系统自带的 Printer 实现，3 代表 Log.DEBUG，"BlockMonitor" 是 Tag
    > print android.os.Looper.getMainLooper().setMessageLogging(new android.util.LogPrinter(3, "BlockMonitor"))
    ```

4.  **验证：**
    现在去看 Logcat：
    ```bash
    adb logcat -s BlockMonitor
    ```
    你应该能看到 `>>>>> Dispatching to...` 的日志源源不断地输出了。

---

### 方法二：修改 Framework 源码（一劳永逸）

既然你是 Framework 工程师，修改 `frameworks/base` 是你的特权。你可以给 `ActivityThread` 加一个系统属性开关，这样以后你调试任何 App 都不需要重新编译 App 了。

**修改文件：** `frameworks/base/core/java/android/app/ActivityThread.java`

**修改位置：** `handleBindApplication` 方法

**代码示例：**

```java
private void handleBindApplication(AppBindData data) {
    // ... 前面的代码 ...
    
    // 【修改开始】读取系统属性，例如 debug.looper.log.pkg
    // 如果当前包名匹配，就开启 MainLooper 的日志
    String targetPkg = SystemProperties.get("debug.looper.log.pkg", "");
    if (!targetPkg.isEmpty() && targetPkg.equals(data.appInfo.packageName)) {
        Looper.getMainLooper().setMessageLogging(new LogPrinter(Log.DEBUG, "LooperDebug"));
        Slog.i("ActivityThread", "Enabled Looper logging for " + targetPkg);
    }
    // 【修改结束】
    
    // ... 后面的代码 ...
}
```

**使用方法：**
1.  编译并刷入 `framework.jar` 或整个系统镜像。
2.  设置属性：`adb shell setprop debug.looper.log.pkg com.example.app`
3.  重启应用。

---

### 方法三：使用 Systrace / Perfetto (不看日志，看图)

其实，`Looper` 在处理消息时，不仅会调用 `Printer`，还会调用 `Trace.traceBegin`。

在 `Looper.java` 源码中：
```java
// Looper.java
if (traceTag != 0 && Trace.isTagEnabled(traceTag)) {
    Trace.traceBegin(traceTag, "msg.target.getTraceName(msg)"); // 这里的名字就是 Handler 类名
}
```

**操作方法：**
你不需要开启 Logcat 日志，只需要抓一个 Trace：

```bash
# 抓取 5 秒的 trace，包含 am (ActivityManager) 和 view (View 系统)
adb shell atrace -t 5 -b 10240 am view app > looper_trace.html
```
或者使用 Perfetto UI 录制。

**结果：**
打开 Trace 文件，找到你的应用进程 -> **Main Thread**。
你会看到一个个彩色的方块（Slice）。
*   **方块的长度**：就是 `cost` 耗时。
*   **方块的名字**：就是 `Handler` 的类名（例如 `Handler (android.view.ViewRootImpl$ViewRootHandler)`）。

**对于 Framework 工程师来说，看 Trace 通常比看 Logcat 文本更直观、更准确，且不会因为日志本身产生性能干扰。**

### 总结

1.  **临时调试**：用 **JDB** 命令行注入 `LogPrinter`。
2.  **长期工具化**：修改 **ActivityThread.java**，增加 `SystemProperties` 开关。
3.  **性能分析**：直接用 **Systrace/Perfetto**，这是系统原生支持最好的方式，能看到一模一样的信息（Handler 名 + 耗时）。

> 【Source: **TranAI** AI-generated, Discover more [click here](https://pfgateway.transsion.com:9199/transsioner-intelligent-service/api/redirect/from=share)】