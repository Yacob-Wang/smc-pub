
你提到的命令 **`adb shell dumpsys activity processes <package>`** 是**完全有效**的，而且非常有用！

但是，它的**视角**和**内容**与你之前用的 `dumpsys activity <package>` 有本质区别。

为了让你更全面地掌握调试技巧，我将基于 AOSP 源码逻辑，把获取特定应用进程信息的命令分为三大类：**系统管理视角（AMS）**、**图形性能视角（WMS/SurfaceFlinger）** 和 **底层进程视角（Kernel/ART）**。

---

### 1. 系统管理视角：AMS 怎么看你的应用？

这类命令展示的是 **Android 系统服务（ActivityManagerService）** 眼中的应用状态。它不进入应用内部，而是查看系统记录的“花名册”。

#### A. `dumpsys activity processes <package>`
*   **作用**：查看进程的**优先级（OOM Adj）**、**内存裁剪级别（Trim Level）** 和 **生命周期状态（ProcState）**。
*   **源码对应**：`ActivityManagerService.java` -> `dumpProcesses(...)`。
*   **能看到什么**：
    *   **`adj`**：非常重要！决定了你的进程会不会被杀。例如 `vis` (Visible), `fgs` (Foreground Service), `cch` (Cached/Background)。
    *   **`procState`**：进程当前是在前台、后台还是休眠。
    *   **`lastPss`**：上次统计的内存占用。
*   **看不到什么**：看不到 `MessageQueue`，看不到 View 树。

#### B. `dumpsys meminfo <package>`
*   **作用**：查看应用极其详细的内存分配情况。
*   **源码对应**：AMS 发起 -> 应用进程 `ActivityThread` -> `ApplicationThread.dumpMemInfo(...)`。
*   **能看到什么**：
    *   **Java Heap**：Java 对象占用。
    *   **Native Heap**：C++ 层占用（Bitmap 像素数据通常在这里）。
    *   **Graphics**：纹理、显存占用。
    *   **Objects**：View、Activity、Context 的数量（**查内存泄漏神器**）。

---

### 2. 图形性能视角：WMS 怎么看你的应用？

这类命令关注的是**掉帧**、**卡顿**和**窗口层级**。

#### C. `dumpsys gfxinfo <package>`
*   **作用**：查看每一帧的渲染耗时（Draw, Prepare, Process, Execute）。
*   **源码对应**：`ThreadedRenderer.java` -> Native `RenderThread`。
*   **能看到什么**：
    *   **Profile data in ms**：一串数字，可以直接复制到 Excel 生成图表。
    *   **Janky frames**：掉帧率统计。
*   **技巧**：使用 `adb shell dumpsys gfxinfo <pkg> reset` 可以清空旧数据，重新开始统计。

#### D. `dumpsys window windows | grep <package>`
*   **作用**：查看应用的窗口（Window）状态。
*   **源码对应**：`WindowManagerService.java`。
*   **能看到什么**：
    *   **`mCurrentFocus`**：当前焦点在哪个窗口。
    *   **`mViewVisibility`**：窗口是否可见。
    *   **`mFrame`**：窗口的具体坐标和大小。

---

### 3. 底层进程视角：ART 和 Kernel 怎么看？

如果你想看比 `MessageQueue` 更底层的**线程堆栈**，或者应用已经死锁（ANR）了，`dumpsys` 可能已经失效，这时需要用这些命令。

#### E. `kill -3 <PID>` (最硬核)
*   **作用**：触发 **SIGQUIT** 信号，强制虚拟机（ART）将当前所有线程的堆栈信息（Stack Trace）写入文件。
*   **原理**：这是 Linux 标准信号，Android 捕获后会生成 `traces.txt`。
*   **怎么用**：
    1.  `adb shell pidof <package>` 拿到 PID。
    2.  `adb shell kill -3 <PID>`。
    3.  `adb pull /data/anr/traces.txt`。
*   **能看到什么**：
    *   **所有线程的调用栈**：主线程卡在哪一行代码？
    *   **锁的持有情况**：谁拿着锁？谁在等锁？（`waiting to lock <0x...> held by thread ...`）。
    *   **MessageQueue 的简要信息**：现代 Android 版本会在 trace 头部的 `main` 线程里附带 Pending Message 的摘要。

#### F. `cat /proc/<PID>/status`
*   **作用**：Linux 内核层面的进程状态。
*   **能看到什么**：
    *   **`State`**：`R` (Running), `S` (Sleeping), `D` (Disk Sleep/Uninterruptible)。
    *   **`Threads`**：当前开启了多少个线程（如果超过 500 个，可能发生了线程泄漏）。
    *   **`VmRSS`**：物理内存占用。

### 总结：我该用哪个？

| 你的目的 | 推荐命令 | 备注 |
| :--- | :--- | :--- |
| **查消息积压、Looper 状态** | `dumpsys activity <pkg>` | **最常用**，包含 MessageQueue |
| **查进程优先级、为何被杀** | `dumpsys activity processes <pkg>` | 系统调度视角 |
| **查内存泄漏** | `dumpsys meminfo <pkg>` | 看 Objects 数量 |
| **查卡顿、掉帧** | `dumpsys gfxinfo <pkg>` | 渲染耗时分析 |
| **查死锁、ANR 根因** | `kill -3 <PID>` | **核武器**，看线程堆栈 |

所以，`dumpsys activity processes <pkg>` 是一个非常好的补充命令，专门用来分析**进程保活**和**系统调度**问题，但它确实不包含你想要的 `MessageQueue` 细节。

> 【Source: **TranAI** AI-generated, Discover more [click here](https://pfgateway.transsion.com:9199/transsioner-intelligent-service/api/redirect/from=share)】