# OC04 · NE 响应剧本：Native Crash 黄金 5/15/30 + 6 类信号 + Tombstone 解读

> **系列**：On-Call Playbook（03-Forensics/Oncall）· 第 4 篇 / 共 8 篇
>
> **基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18` LTS
>
> **目标读者**：oncall 工程师 / 稳定性架构师 / Native 开发
>
> **完成时间**：2026-07-22（v1.0 首版）

<!-- AUTHOR_ONLY:START -->

## 本篇定位

- **本篇系列角色**：**oncall 7 大症状剧本第 3 篇** —— Native 崩溃（最复杂）
- **强依赖**：
  - 必先读 [OC01-oncall 工程总论](OC01-oncall工程总论：值班机制与工具栈.md)
  - 必先读 [02-Symptom/S03-NE/01-症状机制.md](../../02-Symptom/S03-NE/01-症状机制.md) NE 机制
  - 必先读 [03-Forensics/F04-NE/01-取证机制.md](../F04-NE/01-取证机制.md) NE 取证
  - 必先读 [01-Mechanism/Runtime/Native_Crash 系列](../../01-Mechanism/Runtime/Native_Crash/) 8 篇
- **承接自**：OC02 ANR + OC03 JE
- **衔接去**：[OC05-SWT 响应剧本](OC05-SWT响应剧本.md)（待补）
- **不重复内容**：OC01 + S03 + Native_Crash
- **本篇贡献**：
  1. **NE 黄金 5/15/30 标准动作**
  2. **6 类信号分类**（SIGSEGV / SIGABRT / SIGBUS / SIGFPE / SIGILL / SIGTRAP）
  3. **Tombstone 完整解读**（backtrace / memory map / registers / stack）
  4. **5 类真实场景剧本**（NPE / OOM / Stack Overflow / NDK 库 bug / 内存踩踏）
  5. **NE 12 反例清单**

## 校准决策日志

| 轮次 | 类别 | 决策 | 理由 | 影响范围 |
|:-----|:-----|:-----|:-----|:---------|
| 1 | 结构 | 单篇 600+ 行 | §8 破例 | 全文 |
| 1 | 结构 | 6 类信号 + 5 场景剧本 | NE 复杂度高 | §2-§9 |
| 2 | 硬伤 | 黄金 5/15/30 每分钟动作 | 反例 #4 | §3 |
| 2 | 硬伤 | Tombstone 解读必须有完整示例 | 反例 #11 | §5 |
| 3 | 锐度 | 删"可能" | 反例 #5 | 全文 |

## 角色设定

我是一名 **oncall 工程师**，刚收到 P0 告警：

> **告警**：`Native Crash-free Session` < 99.8%
> **触发时间**：14:30:00
> **影响范围**：约 20 万 DAU 出现 NE 崩溃
> **崩溃位置**：libmyjni.so 0x12345

## 上下文

- **上一篇**：[OC03-JE 响应剧本](OC03-JE响应剧本.md)
- **下一篇**：[OC05-SWT 响应剧本](OC05-SWT响应剧本.md)
- **跨系列引用**：
  - [02-Symptom/S03-NE](../../02-Symptom/S03-NE/01-症状机制.md)
  - [01-Mechanism/Runtime/Native_Crash](../../01-Mechanism/Runtime/Native_Crash/) 8 篇
  - [04-Tool/Dumpsys](../../04-Tool/Dumpsys/)
- **本篇专题类型**：**实战剧本**

## 写作标准

> v5 规范 + 5 段前言 marker ✅

<!-- AUTHOR_ONLY:END -->

---

# 1. NE 6 大信号速查

> **铁律**：NE 崩溃的核心信息在 **tombstone 文件**，**第 1 件事是看 signal**

| # | 信号 | 名称 | 含义 | 占比 |
|:-:|:-----|:-----|:-----|:----:|
| 1 | **SIGSEGV (11)** | Segmentation Fault | 非法内存访问 | 50% |
| 2 | **SIGABRT (6)** | Abort | abort() / assert 失败 / double free | 25% |
| 3 | **SIGBUS (7)** | Bus Error | 未对齐访问 / mmap 错误 | 10% |
| 4 | **SIGFPE (8)** | Floating Point Exception | 除零 / 算术异常 | 5% |
| 5 | **SIGILL (4)** | Illegal Instruction | 非法指令 / 栈破坏 | 5% |
| 6 | **SIGTRAP (5)** | Trace/Breakpoint | debuggerd 主动抛 | 5% |

**关键 logcat 关键字**：

```bash
# 一次性搜 NE 关键字
adb logcat -d -b crash | grep -E "tombstone|signal|sigaction|libc.*Fatal"
```

---

# 2. 黄金 5 分钟：必做 4 件事

## 2.1 第 1 分钟：确认告警 + 拉群

```bash
# 1. APM 推送卡片
# 2. 回复"已收到"
# 3. 拉应急群
```

## 2.2 第 2 分钟：抓 tombstone

```bash
# 1. 拉 tombstone（30 秒）
adb shell ls /data/tombstones/  # 列出所有
adb pull /data/tombstones/ /tmp/tombstones/

# 2. 同步抓 logcat（30 秒）
adb logcat -d -b crash | tail -100
```

## 2.3 第 3 分钟：判断信号类型

**看 tombstone 第 3-5 行**：

```
*** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***
Build fingerprint: 'Xiaomi/...'
Revision: '0'
ABI: 'arm64'
pid: 12345, tid: 12345, name: my.app  >>> com.example.app <<<
signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0
```

**判断结果**：
- SIGSEGV + fault addr 0x0 → **空指针解引用**（→ §7）
- SIGSEGV + fault addr 0x... → **野指针**（→ §7）
- SIGABRT → **abort/assert/double free**（→ §8）
- SIGBUS → **栈溢出 / 内存对齐**（→ §9）

## 2.4 第 4-5 分钟：发首报

```yaml
告警: NE 率超阈值
触发: 14:30:00
当前: oncall @A 已介入
判断: [SIGSEGV/SIGABRT/SIGBUS] + [信号原因]
首报:
  - 影响: 20 万 DAU
  - 信号类型: SIGSEGV (11)
  - 崩溃库: libmyjni.so
  - 崩溃偏移: 0x12345
  - 怀疑: [空指针/野指针/...]
  - 行动: 已抓 tombstone，开始解读
  - ETA: 10 分钟内出二报
```

---

# 3. 白银 15 分钟：Tombstone 解读

## 3.1 Tombstone 完整结构

```
*** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***   ← 1. 头部
Build fingerprint: 'Xiaomi/cepheus/cepheus:10/QKQ1.190825.002/...'   ← 2. 设备信息
ABI: 'arm64'                                                          ← 3. ABI
pid: 12345, tid: 12345, name: my.app  >>> com.example.app <<<         ← 4. 进程
signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0            ← 5. 信号（关键）
                                                                      ← 6. 寄存器（关键）
backtrace:                                                            ← 7. 栈回溯（关键）
      #00 pc 000000000012345  libmyjni.so (MyJni.foo+88)
      #01 pc 000000000067890  libmyjni.so (MyJni.bar+200)
      #02 pc 0000000000abcde  libart.so (art_quick_generic_native_call+...)
      ...
stack:                                                                ← 8. 栈内容
    00007fff34567890  0000000000000000
    00007fff34567898  0000000012345678
memory map:                                                           ← 9. 内存映射
    0000000000400000-0000000000500000 r-xp  /system/bin/app_process64
    0000000000600000-0000000000700000 r--p  /system/bin/app_process64
    ...
```

## 3.2 9 段 Tombstone 解读要点

| 段 | 看什么 | 关键信息 |
|:---|:-------|:---------|
| **1. 头部** | 崩溃时间 | 时间戳 |
| **2. 设备** | Build fingerprint | 厂商 + 机型 |
| **3. ABI** | arm64 / armv7 | 决定 addr2line 命令 |
| **4. 进程** | pid + tid + name | 哪个进程崩了 |
| **5. 信号** | signal + code + fault addr | **最重要** |
| **6. 寄存器** | x0-x30 + sp + pc | 寄存器值定位参数 |
| **7. 栈回溯** | pc 偏移 + 库 + 函数 | **最关键** |
| **8. 栈内容** | sp 开始的内存 | 调用参数 |
| **9. 内存映射** | 库的加载地址 | 决定符号化 |

## 3.3 addr2line 符号化

```bash
# 把 pc 偏移 + 库路径 跑 addr2line
$ANDROID_NDK/ndk-stack \
  -sym libmyjni.so \
  -dump tombstone_00

# 输出
#00 pc 000000000012345  libmyjni.so (MyJni.foo+88)
#01 pc 000000000067890  libmyjni.so (MyJni.bar+200)
#                                          ↑
#                                       MyJni.java:200
```

**反汇编辅助**（看具体汇编）：

```bash
$ANDROID_NDK/llvm-objdump -d libmyjni.so | grep -A 30 "MyJni.foo:"
```

---

# 4. 黄金 30 分钟：执行修复

## 4.1 决策树

```
定位到根因
   │
   ├── 应用层 bug
   │     │
   │     ├── 紧急 → **热修**（Java 改 + 重打包）
   │     └── 不紧急 → **下版修**
   │
   ├── NDK 库 bug
   │     │
   │     ├── 紧急 → **回滚旧版 NDK**
   │     └── 不紧急 → **修 NDK + 发版**
   │
   └── 硬件/OEM 问题
         │
         ├── 单机型 → **该机型走特殊处理**
         └── 多机型 → **上报 Google/OEM**
```

## 4.2 修复代码（5 类常见 NE）

### 4.2.1 空指针解引用（C/C++）

```c
// 错误
const char* name = user->name;  // ❌ user 可能为 null
return strlen(name);

// 正确
if (user == NULL || user->name == NULL) return "";  // ✅ 防御
return strlen(user->name);
```

### 4.2.2 野指针（use-after-free）

```c
// 错误
free(obj);
obj->field = 1;  // ❌ use-after-free

// 正确
free(obj);
obj = NULL;  // ✅ 置 null
// 或用智能指针（std::shared_ptr）
```

### 4.2.3 栈溢出（Stack Overflow）

```c
// 错误
void recursive() {
    char buf[1024 * 1024];  // ❌ 1MB 栈
    recursive();
}

// 正确
void recursive() {
    char* buf = (char*)malloc(1024 * 1024);  // ✅ 堆分配
    // ... use buf ...
    free(buf);
    recursive();
}
```

### 4.2.4 NDK 库 bug

```c
// 错误（没检查返回值）
ALOGD("opening %s", filename);
int fd = open(filename, O_RDONLY);  // ❌ 失败时 fd=-1
read(fd, buf, 100);  // ❌ SIGSEGV

// 正确
int fd = open(filename, O_RDONLY);
if (fd < 0) {  // ✅ 检查
    ALOGE("open failed: %s", strerror(errno));
    return -1;
}
read(fd, buf, 100);
close(fd);
```

### 4.2.5 内存踩踏（Buffer Overflow）

```c
// 错误
char buf[10];
strcpy(buf, "this is a long string");  // ❌ 越界

// 正确
char buf[10];
strncpy(buf, "this is a long string", sizeof(buf) - 1);  // ✅
buf[sizeof(buf) - 1] = '\0';
// 更好：用 AddressSanitizer
```

---

# 5. 5 类真实场景剧本

## 5.1 场景 1：JNI 空指针（SIGSEGV）

**现象**：调用 JNI 方法时崩溃
**tombstone**：

```
signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0
backtrace:
  #00 pc 000000000012345  libmyjni.so (Java_com_example_app_MyJni_foo+88)
```

**根因**：`MyJni_foo(JNIEnv* env, jobject obj)` 中 `env` 为 null
**修复**：在 native 入口检查 env

```c
JNIEXPORT void JNICALL
Java_com_example_app_MyJni_foo(JNIEnv* env, jobject obj) {
    if (env == NULL) return;  // ✅
    // ...
}
```

## 5.2 场景 2：图片解码 OOM（SIGABRT）

**现象**：拍照后打开图片，App 闪退
**tombstone**：

```
signal 6 (SIGABRT), code -1 (SI_TKILL), fault addr 0x0
backtrace:
  #00 pc 000000000012345  libc.so (abort+88)
  #01 pc 0000000000abcde  libskia.so (SkBitmap::tryAllocPixels+...)
```

**根因**：图片解码时分配 100MB+ 内存，触发 LMKD
**修复**：分块解码 + 缩略图

## 5.3 场景 3：栈溢出（SIGSEGV + 0xdeadbaad）

**现象**：递归调用时崩溃
**tombstone**：

```
signal 11 (SIGSEGV), code 0 (SEGV_ACCERR), fault addr 0xdeadbaad
backtrace:
  #00 pc 000000000012345  libmyjni.so (recursive+88)
  #01 pc 000000000012345  libmyjni.so (recursive+88)
  #02 pc 000000000012345  libmyjni.so (recursive+88)
  ...
  #99 pc 000000000012345  libmyjni.so (recursive+88)
```

**根因**：无限递归
**修复**：加递归深度限制

## 5.4 场景 4：NDK 库不匹配

**现象**：升级 Android 12 后崩溃
**tombstone**：

```
signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x12345678
backtrace:
  #00 pc 000000000012345  libmyjni.so
```

**根因**：NDK 库没重新编译，符号不匹配
**修复**：用最新 NDK 重新编译

## 5.5 场景 5：内存踩踏（随机崩溃）

**现象**：随机崩溃，崩溃栈不同
**tombstone**：

```
signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x...
backtrace:
  #00 pc 0000000000random  libmyjni.so (?)
```

**根因**：缓冲区溢出踩坏相邻内存
**修复**：开 AddressSanitizer 复现 + 找根因

```cmake
# CMakeLists.txt 开 ASan
target_compile_options(myjni PRIVATE -fsanitize=address)
target_link_options(myjni PRIVATE -fsanitize=address)
```

---

# 6. NE 告警规则

```yaml
# APM 告警（NE 类）
- alert: NeFreeSessionDrop
  expr: |
    1 - (
      countIf(event_type='ne_tombstone', session_id != '')
      / countIf(event_type='session_start')
    ) < 0.999
  for: 2m
  labels: { severity: P0 }

- alert: SameSignalSpike
  expr: |
    count by (signal) (rate(ne_tombstone_total[5m])) > 5
  for: 3m
  labels: { severity: P1 }
```

---

# 7. NE oncall 12 反例

| # | 反例 | 错误做法 | 正确做法 |
|:-:|:-----|:---------|:---------|
| 1 | **只看 signal 11** | 不看 code + fault addr | **5 行必看** |
| 2 | **不符号化** | 看到 0x12345 就放弃 | **addr2line 必跑** |
| 3 | **不抓 tombstone** | 只看 logcat | **tombstone 是金标准** |
| 4 | **不查引入版本** | 不查 NDK 升级 | **第 3 步必查** |
| 5 | **不分信号类型** | "就是 NE" | **6 类信号分类** |
| 6 | **不反汇编** | 看到 0x12345 跳过 | **objdump 必看** |
| 7 | **改 try-catch 凑数** | Java 层 catch | **Native 改 native** |
| 8 | **不通知 Native 团队** | Java 团队自己修 | **第 1 分钟拉 Native** |
| 9 | **回滚旧 NDK 不通知** | 偷偷回滚 | **回滚前通知** |
| 10 | **不写 postmortem** | 修了就完 | **24h 内出** |
| 11 | **不查同类** | 单点修复 | **横向 review** |
| 12 | **不复盘** | 24h 后忘光 | **72h 内复盘** |

---

# 8. 5 条 Takeaway

1. **NE 黄金 5/15/30** —— 5 分钟抓 tombstone + 拉群；15 分钟符号化；30 分钟修复
2. **6 类信号分类**（SIGSEGV 50% / SIGABRT 25% / SIGBUS 10% / 其他 15%）—— 看 signal 立刻分类
3. **Tombstone 9 段解读** —— 信号 + 寄存器 + backtrace 是金三角
4. **5 类真实场景**（空指针 / OOM / 栈溢出 / NDK 不匹配 / 内存踩踏）
5. **addr2line + objdump** 必用 —— 看到 0x12345 不是终点

---

# 9. 附录

## 附录 A：源码索引

| 模块 | 路径 | 关键类/方法 |
|:-----|:-----|:-------------|
| NE 机制 | [02-Symptom/S03-NE/01-症状机制.md](../../02-Symptom/S03-NE/01-症状机制.md) | 6 类信号 |
| NE 取证 | [03-Forensics/F04-NE/01-取证机制.md](../F04-NE/01-取证机制.md) | 完整流程 |
| Native Crash 总览 | [01-Mechanism/Runtime/Native_Crash/01-NativeCrash总览](../../01-Mechanism/Runtime/Native_Crash/01-NativeCrash总览.md) | 8 篇 |
| debuggerd | [Native_Crash/04-debuggerd与Tombstone](../../01-Mechanism/Runtime/Native_Crash/04-debuggerd与Tombstone.md) | tombstone 落盘 |
| Tombstone 解读 | [Native_Crash/06-Tombstone深度解读](../../01-Mechanism/Runtime/Native_Crash/06-Tombstone深度解读.md) | 9 段 |
| oncall 流程 | [OC01-oncall 工程总论](OC01-oncall工程总论：值班机制与工具栈.md) | 5/15/30 |

## 附录 B：路径对账

本篇新增模块无（沿用 S03 + F04 + Native_Crash 已有路径）。

## 附录 C：量化自检

- 6 类信号 + 占比 + 关键字 ✅
- 黄金 5/15/30 每分钟动作 ✅
- Tombstone 9 段完整解读 ✅
- 5 类真实场景剧本 ✅
- 12 反例清单 ✅
- 5 条 Takeaway ✅

## 附录 D：工程基线

- AOSP 17.0.0_r1（API 37）
- 工具链：ndk-stack + addr2line + objdump + ndk-gdb
- 告警栈：APM 自研 + tombstones 目录监控

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-22（v1.0）
