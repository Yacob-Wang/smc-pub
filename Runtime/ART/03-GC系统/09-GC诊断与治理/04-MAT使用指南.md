# 9.4 MAT（Memory Analyzer）使用指南

> **本节回答一个根本问题**：MAT 是什么？怎么用 MAT 分析 hprof？Retained Size 和 Shallow Size 有什么区别？
>
> **答案**：**MAT 是 Eclipse 基金会开发的 heap dump 分析工具** —— 全功能但慢，适合深度分析。

---

## 一、MAT 概述

### 9.4.1 MAT 的定义

```
MAT（Memory Analyzer）：

- Eclipse 基金会的开源工具
- 全功能 heap dump 分析器
- 支持 OQL（Object Query Language）
- 支持 Retained Heap 分析
- 适合深度分析（比 LeakCanary 的 Shark 引擎慢但功能强）
```

### 9.4.2 MAT vs Shark 引擎

| 维度 | MAT | Shark 引擎 |
|:---|:---|:---|
| **分析速度** | 慢（一次性加载） | 快（流式处理） |
| **内存占用** | 大（占 GB 级别） | 小（流式） |
| **分析能力** | 全功能（OQL、Retained Heap、支配树等） | 找泄漏链 |
| **使用方式** | 独立工具 | 集成在 LeakCanary |
| **适用场景** | 深度分析 | 自动监控 |

---

## 二、MAT 的安装与使用

### 9.4.3 MAT 的下载

```
MAT 下载：
- Eclipse Memory Analyzer: https://www.eclipse.org/mat/
- 当前版本：1.13.0
- 支持 macOS / Linux / Windows
- 需要 Java 11+
```

### 9.4.4 MAT 的启动

```bash
# 启动 MAT
./mat/eclipse -vmargs -Xmx4g
# 或使用包装脚本
./mat/ParseHeapDump.sh /path/to/heap.hprof
```

### 9.4.5 MAT 的内存配置

```
# MAT 默认 heap dump 加载需要 1-2 GB 内存
# 大型 hprof（> 500 MB）需要更多

# 修改 MAT 启动参数
./mat/eclipse -vmargs -Xmx8g

# 或在 mat/ 目录下修改 MemoryAnalyzer.ini
-vmargs
-Xmx8g
-XX:+UseG1GC
```

---

## 三、MAT 的核心概念

### 9.4.6 Shallow Size（浅大小）

```
Shallow Size（浅大小）：

定义：对象自身占用的内存（不含引用的对象）
包括：
- 对象头
- 实例字段
- 对齐填充

示例：
class User {
    long id;        // 8 bytes
    String name;    // 4 bytes（引用）
    int age;        // 4 bytes
}
User 实例的 Shallow Size = 8 + 4 + 4 + 8（对象头）+ 4（对齐）= 28 bytes
```

### 9.4.7 Retained Size（保留堆）

```
Retained Size（保留堆）：

定义：如果该对象被 GC 回收，能释放的总内存
包括：
- 对象自身的 Shallow Size
- 该对象引用的所有对象的 Shallow Size
- 这些对象引用的对象的 Shallow Size（递归）

示例：
A 引用 B，B 引用 C
A 的 Retained Size = A.shallow + B.shallow + C.shallow
```

### 9.4.8 Retained Heap vs Shallow Heap

```
Shallow Heap：
- 对象自身的大小
- 直接看得到

Retained Heap：
- 对象能"保留"的总内存
- 如果释放这个对象，能释放多少
- 更能反映"泄漏的影响"

→ MAT 中看 Retained Heap 找最大内存占用
→ MAT 中看 Shallow Heap 找最多的对象实例
```

### 9.4.9 Dominator Tree（支配树）

```
Dominator Tree（支配树）：

定义：A 支配 B = 从 GC Root 到 B 的所有路径都必须经过 A
特点：
- 如果 A 被回收，B 也必然被回收
- Retained Size = 支配树中的子树大小

用途：
- 找内存中最大的子树
- 找可能的内存泄漏点
```

---

## 四、MAT 的核心功能

### 9.4.10 Histogram（直方图）

```
Histogram：按类统计对象实例数和 Shallow Heap

操作：
1. 打开 hprof
2. 点击 "Histogram" 图标
3. 输入类名过滤（如 com.example.*）
4. 查看：
   - Objects：实例数
   - Shallow Heap：浅堆总大小
   - Retained Heap：保留堆总大小
```

### 9.4.11 Dominator Tree（支配树）

```
Dominator Tree：按 Retained Heap 排序的对象树

操作：
1. 打开 hprof
2. 点击 "Dominator Tree" 图标
3. 查看：
   - 顶层是 Retained Heap 最大的对象
   - 子树表示引用关系

→ 通过 Dominator Tree 找最大内存占用者
```

### 9.4.12 Leak Suspects（泄漏嫌疑）

```
Leak Suspects：MAT 自动找的内存泄漏嫌疑

操作：
1. 打开 hprof
2. 点击 "Leak Suspects" 报告
3. 查看：
   - 可能的泄漏点
   - Retained Heap 大小
   - 建议的修复方案

→ 快速定位泄漏点
```

### 9.4.13 Top Consumers（最大消费者）

```
Top Consumers：找占用内存最多的类

操作：
1. 打开 hprof
2. 点击 "Top Consumers" 报告
3. 查看：
   - 按 Retained Heap 排序
   - 占用最大的类
   - 占用最大的包

→ 找到占用内存最多的"嫌疑"
```

---

## 五、OQL（Object Query Language）

### 9.4.14 OQL 概述

```
OQL：MAT 的 SQL-like 查询语言

语法：
SELECT *
FROM <class_name>
WHERE <condition>

示例：
SELECT *
FROM com.example.User
WHERE age > 18
```

### 9.4.15 OQL 常用查询

```sql
-- 1. 查所有 Activity
SELECT *
FROM android.app.Activity

-- 2. 查所有 Bitmap
SELECT *
FROM android.graphics.Bitmap
WHERE width > 1000

-- 3. 查所有自定义类的实例数
SELECT class.name, count(obj)
FROM java.lang.Object obj
WHERE class.name LIKE 'com.example.%'
GROUP BY class.name
ORDER BY count(obj) DESC

-- 4. 查 Retained Heap 最大的对象
SELECT obj, obj.@retainedHeapSize
FROM java.lang.Object obj
ORDER BY obj.@retainedHeapSize DESC
LIMIT 10

-- 5. 查所有带特定字段的对象
SELECT u.name, u.id
FROM com.example.User u
WHERE u.id > 1000
```

### 9.4.16 OQL 实战案例

```sql
-- 查所有大于 1 MB 的 Bitmap
SELECT b.@displayName, b.@retainedHeapSize, b.width, b.height
FROM android.graphics.Bitmap b
WHERE b.@retainedHeapSize > 1048576
ORDER BY b.@retainedHeapSize DESC
```

```sql
-- 查所有泄漏的 Activity（按引用链）
SELECT a, a.@GCRootsInfo
FROM com.example.MainActivity a
WHERE a.@GCRootsInfo.@retainedHeapSize > 524288
```

---

## 六、MAT 的工作流

### 9.4.17 完整分析流程

```
1. 生成 hprof
   adb shell am dumpheap <pid> /data/local/tmp/dump.hprof
   adb pull /data/local/tmp/dump.hprof

2. hprof-conv 转换（Android 格式 → Java SE 格式）
   hprof-conv dump.hprof dump-conv.hprof

3. MAT 打开
   File → Open Heap Dump → dump-conv.hprof

4. 等待解析（可能几分钟）

5. Leak Suspects 报告（自动找泄漏点）

6. Dominator Tree 找最大占用

7. Histogram 找对象分布

8. OQL 精确查询

9. 修复 + 验证
```

### 9.4.18 MAT 的常见操作

```
1. 看 Leak Suspects
2. 看 Dominator Tree（按 Retained Heap 排序）
3. 右键 → List objects → with incoming references（看谁引用它）
4. 右键 → List objects → with outgoing references（看它引用谁）
5. 右键 → Path to GC Roots → exclude weak references（找 GC Root 路径）
```

---

## 七、MAT 的工程实践

### 9.4.19 与 LeakCanary 的协作

```
MAT 与 LeakCanary 的协作：

1. LeakCanary 自动检测 + 输出路径
2. 用 MAT 深度分析（如果需要）
3. LeakCanary 的报告 → MAT 验证

或者：
1. LeakCanary 输出路径
2. 用 Shark 引擎的输出（如果不需要 MAT 的高级功能）
```

### 9.4.20 与 hprof-conv 的配合

```bash
# 1. Android 格式 hprof → Java SE 格式
hprof-conv android.hprof java.hprof

# 2. MAT 打开 java.hprof
# （MAT 不识别 Android 格式，必须转换）

# 3. hprof-conv 在哪里
# - AOSP 源码：external/robolectric-shadows/
# - Android Studio：直接用 Android Studio 自带的工具
```

### 9.4.21 MAT 的限制

```
MAT 的限制：

1. 内存占用大
   - 加载 hprof 需要数 GB 内存
   - 大型 App 难以分析

2. 速度慢
   - 加载 + 解析可能需要数分钟
   - 不适合实时监控

3. 不支持 Android 11+ Heap Dump API
   - 必须先生成 hprof 文件

→ MAT 适合"事后深度分析"，不适合"实时监控"
```

---

## 八、本节小结

1. **MAT 是 Eclipse 基金会的 heap dump 分析工具**
2. **核心概念**：Shallow Size / Retained Size / Dominator Tree
3. **核心功能**：Histogram / Dominator Tree / Leak Suspects / OQL
4. **完整工作流**：生成 hprof → 转换 → MAT 打开 → 分析 → 修复
5. **与 LeakCanary 协作**：LeakCanary 检测 + MAT 深度分析

→ **理解 MAT，就掌握了"深度内存分析"的工具**。

---

## 跨节引用

**本节被以下章节引用**：
- [9.3 LeakCanary](./03-LeakCanary原理.md) —— LeakCanary 自动检测
- [9.9 实战案例 1](./09-实战案例1-dumpsys诊断.md) —— 完整排查

**本节引用**：
- [9.1 dumpsys meminfo](./01-dumpsys-meminfo详解.md) —— 内存概览
- [9.2 procrank / smaps](./02-procrank-smaps.md) —— 进程级
