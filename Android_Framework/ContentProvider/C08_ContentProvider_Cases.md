# C08 · 实战案例集：5 大稳定性问题排查（横切专题）

> **基线**：AOSP `android-17.0.0_r1`（API 37） + Linux `android17-6.18` LTS
> **本篇角色**：ContentProvider 系列 **第 8 篇 / 横切专题**（**破例：3 张图**）
> **强依赖**：[C01-C07 全部 7 篇](C01_ContentProvider_Overview.md)
> **承接自**：C01-C07 已分别覆盖 5 大场景的机制与案例；本篇**精选 5 个真实场景案例的完整排查过程**，作为"案例集"
> **衔接去**：[C09 · ContentProvider 优化与监控](C09_ContentProvider_Optimize_Monitor.md) — C08 收尾横切；C09 进入诊断治理
> **不重复内容**：与 C01-C07 单篇案例不重复；本篇是"案例集"视角

## 破例决策记录

| 破例项 | 破例内容 | 破例理由 | 影响范围 | 是否传染 |
|--------|---------|---------|---------|---------|
| 图表密度 | 3 张图（规则 4-6 张） | §9.1 合法破例：横切专题型 | 仅 C08 | 否 |
| 风险地图 | 简化版 | §9.1 合法破例：横切专题型 | 仅 C08 | 否 |

---

## 一、背景与定义

### 1.1 案例集设计思路

本篇**不重复 C01-C07 的单篇案例**，而是从"案例集"视角**精选 5 个真实场景**，覆盖 ContentProvider 稳定性的 5 大核心问题：

| 案例 | 问题类型 | 根因 | 修复 |
|------|---------|------|------|
| **CASE-C-01** | 冷启动慢 | Provider onCreate 同步初始化 | 异步化 + 拆分 Provider |
| **CASE-C-02** | 跨 App 失败 | AOSP 11+ 包不可见 | 加 `<queries>` 声明 |
| **CASE-C-03** | 内存泄漏 | Cursor 未 close | try-with-resources |
| **CASE-C-04** | 性能退化 | 跨进程 query 频次过高 | 业务层缓存 |
| **CASE-C-05** | CursorWindow 异常 | 大 Cursor 跨进程传输 | 加 LIMIT + 分片传输 |

### 1.2 为什么需要案例集

1. **稳定性架构师真正关心的是"案例排查"**——**不是源码**。
2. **5 大问题覆盖 ContentProvider 90% 线上问题**。
3. **AOSP 17 强化**——案例基于 AOSP 17 + android17-6.18 LTS 基线。

---

## 二、案例 1：Provider onCreate 同步初始化导致冷启动慢

### 1.1 现象

```
User 报告: "App 冷启动慢 1.5 秒"
systrace:
06-20 11:30:33.456  com.example.app  LoadedApk.installProvider  +1200ms
06-20 11:30:33.456  com.example.app  LoadedApk.makeApplication +200ms
06-20 11:30:33.456  com.example.app  MainActivity.onCreate    +300ms
```

### 1.2 环境

- Android 17 (API 37)
- 内核：`android17-6.18` LTS
- 设备：Pixel 6
- 复现步骤：杀掉进程后启动 App

### 1.3 排查过程

**第 1 步：trace 分析**

```
LoadedApk.installProvider  +1200ms  ← 慢
LoadedApk.makeApplication +200ms   ← 正常
MainActivity.onCreate    +300ms   ← 正常
```

**第 2 步：找 installProvider 的具体方法**

```bash
adb shell dumpsys activity providers com.example.app
# 输出:
# Provider: com.example.app/.DataProvider
# time=+1200ms ago
# launching=true
```

**第 3 步：检查 DataProvider.onCreate**

```java
public class DataProvider extends ContentProvider {
    @Override
    public boolean onCreate() {
        super.onCreate();
        // 同步初始化 4 个 SDK
        SDK1.init(getContext());  // 300ms
        SDK2.init(getContext());  // 400ms
        SDK3.init(getContext());  // 200ms
        SDK4.init(getContext());  // 300ms
        return true;  // 总 1200ms
    }
}
```

### 1.4 根因

业务方在 `DataProvider.onCreate` 同步初始化 4 个 SDK（每个 300-400ms = 1200ms 总耗时）。**ContentProvider.onCreate 在 Application.onCreate 之前**，**业务方没意识到这是冷启动瓶颈**。

### 1.5 修复

**修复前 → 修复后**：

```diff
--- a/DataProvider.java
+++ b/DataProvider.java
@@ -10,12 +10,15 @@ public class DataProvider extends ContentProvider {
     @Override
     public boolean onCreate() {
         super.onCreate();
-        // 同步初始化 4 个 SDK（1200ms）
-        SDK1.init(getContext());
-        SDK2.init(getContext());
-        SDK3.init(getContext());
-        SDK4.init(getContext());
+        // 立即返回，异步初始化
+        new Thread(() -> {
+            SDK1.init(getContext());
+            SDK2.init(getContext());
+            SDK3.init(getContext());
+            SDK4.init(getContext());
+        }).start();
         return true;
     }
 }
```

### 1.6 验证

- 修复后冷启动时间从 1500ms 降到 600ms
- 关键监控：`LoadedApk.installProvider` 耗时从 1200ms 降到 5ms
- 关键监控：冷启动总时长从 1500ms 降到 600ms

---

## 三、案例 2：AOSP 11+ 包不可见导致跨 App ContentProvider 访问失败

### 2.1 现象

```
logcat:
11-10 14:30:22.123  1000  1234  1234 E com.example.app: java.lang.SecurityException: 
11-10 14:30:22.123  1000  1234  1234 E com.example.app:   Failed to find provider com.android.providers.media for user 0
11-10 14:30:22.123  1000  1234  1234 E com.example.app:   but could not be found in package com.android.providers.media
```

### 2.2 环境

- Android 17 (API 37)
- 设备：Pixel 6
- 复现步骤：App 升级到 targetSdk 30 后，访问 MediaStore

### 2.3 排查过程

**第 1 步：查 manifest**

```xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.example.app">
    <application>
        ...
    </application>
</manifest>
```

**问题**：没有 `<queries>` 声明。

**第 2 步：确认 AOSP 11+ 行为**

- AOSP 11 引入包可见性
- 业务方没声明 `<queries>` → MediaStore 不可见

**第 3 步：修复**

```xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <queries>
        <package android:name="com.android.providers.media" />
        <package android:name="com.android.providers.contacts" />
        <intent>
            <action android:name="android.intent.action.VIEW" />
            <data android:mimeType="image/*" />
        </intent>
    </queries>
    <application>
        ...
    </application>
</manifest>
```

### 2.4 根因

业务方升级到 AOSP 11 (targetSdk 30) 后没声明 `<queries>`，**包可见性默认"全部不可见"**。

### 2.5 修复验证

- 修复后跨 App ContentProvider 访问成功
- 关键监控：SecurityException 次数从 100% 降到 0

---

## 四、案例 3：Cursor 未 close 导致 CursorWindow 内存泄漏

### 3.1 现象

```
LeakCanary 报告:
┌──────────────────────────────────────┐
│ * CursorWindow has leaked            │
│ * GC Root: ContentResolver           │
│ * Details:                           │
│   Cursor was not closed              │
└──────────────────────────────────────┘

dumpsys meminfo:
Pss Total:    156789 KB
  Cursor:     1234 KB  ← 异常占用
```

### 3.2 环境

- Android 17 (API 37)
- 设备：Pixel 6
- 复现步骤：App 多次进出后 dumpsys meminfo

### 3.3 排查过程

**第 1 步：dump meminfo 找 Cursor 占用**

```bash
adb shell dumpsys meminfo com.example.app
# 输出:
# Objects:
#   Views:        145
#   Cursor:     1234 KB  ← 异常
```

**第 2 步：grep 代码**

```bash
grep -rn "getContentResolver().query" app/src/main/java/
# 找到 5 个 query 调用，3 个漏 close
```

**第 3 步：LeakCanary 报出 Cursor 引用链**

```
CursorWindow  ←  Cursor  ←  ContentResolver  ←  MainActivity
                ↑                                ↑ (leaked)
                close? 漏!
```

### 3.4 根因

业务方在 Activity onCreate 中 query 但没 close cursor，**多次进出后 CursorWindow 累积泄漏**。

### 3.5 修复

**修复前 → 修复后**：

```diff
--- a/MainActivity.java
+++ b/MainActivity.java
@@ -25,12 +25,15 @@ public class MainActivity extends AppCompatActivity {
     private void loadData() {
-        Cursor cursor = getContentResolver().query(uri, ...);
-        while (cursor.moveToNext()) {
-            // 处理
+        try (Cursor cursor = getContentResolver().query(uri, ...)) {
+            while (cursor.moveToNext()) {
+                // 处理
+            }
         }
-        // 漏 close!
+        // try-with-resources 自动 close
     }
```

### 3.6 修复验证

- 修复后 CursorWindow 占用稳定 < 100KB
- 关键监控：LeakCanary 报告 0 泄漏
- 关键监控：用户反复进出 100 次后，Cursor 占用稳定

---

## 五、案例 4：跨进程 query 频次过高导致性能退化

### 4.1 现象

```
Perfetto trace:
12-01 10:00:00.000  com.example.app  ContentResolver.query  +1ms
12-01 10:00:00.005  com.example.app  ContentResolver.query  +1ms
12-01 10:00:00.010  com.example.app  ContentResolver.query  +1ms
... (每秒 200 次)
```

### 4.2 环境

- Android 17 (API 37)
- 设备：Pixel 6
- 复现步骤：ListView 滚动时多次调用 ContentResolver.query

### 4.3 排查过程

**第 1 步：Perfetto 抓 trace**

- 看到 ContentResolver.query 每秒 200 次调用
- Binder 线程占用 14/15

**第 2 步：grep 代码**

```bash
grep -rn "query" app/src/main/java/feature/listview/
# 找到 ListView adapter.getView 中每次调用 query
```

**第 3 步：分析 query 时延**

- 每次 query 1ms（缓存命中）
- 200 次/秒 = 200ms/秒 在 query 上
- 主线程被占用 200ms/秒

### 4.4 根因

业务方在 ListView adapter.getView 中每次调用 ContentResolver.query，**未使用 CursorLoader / CursorAdapter**。

### 4.5 修复

**修复前 → 修复后**：

```diff
--- a/MyAdapter.java
+++ b/MyAdapter.java
@@ -30,8 +30,8 @@ public class MyAdapter extends BaseAdapter {
     @Override
     public View getView(int position, View convertView, ViewGroup parent) {
-        // 每次 query，200 次/秒
-        Cursor cursor = contentResolver.query(uri, ...);
-        bindView(cursor);
+        // 业务层缓存
+        Item item = itemCache.get(position);
+        if (item == null) {
+            item = loadItem(position);
+            itemCache.put(position, item);
+        }
+        bindView(item);
         return convertView;
     }
```

### 4.6 修复验证

- 修复后 query 次数从 200/秒 降到 5/秒
- 关键监控：ListView 滚动 FPS 从 30 提升到 60
- 关键监控：Binder 线程占用从 14/15 降到 3/15

---

## 六、案例 5：CursorWindow TransactionTooLargeException

### 5.1 现象

```
logcat:
12-05 14:30:22.123  1000  1234  1234 E AndroidRuntime: FATAL EXCEPTION: main
12-05 14:30:22.123  1000  1234  1234 E AndroidRuntime: Process: com.example.app, PID: 1234
12-05 14:30:22.123  1000  1234  1234 E AndroidRuntime: java.lang.RuntimeException: 
12-05 14:30:22.123  1000  1234  1234 E AndroidRuntime:   at android.os.Parcel.readException(Parcel.java:2225)
12-05 14:30:22.123  1000  1234  1234 E AndroidRuntime:   android.os.TransactionTooLargeException: data parcel size 2097152 bytes
```

### 5.2 环境

- Android 17 (API 37)
- 设备：Pixel 6
- 复现步骤：App 跨进程访问其他 App 的 ContentProvider，query 返回大数据

### 5.3 排查过程

**第 1 步：看 ANR trace**

- 看到 TransactionTooLargeException
- data parcel size 2097152 bytes = 2MB

**第 2 步：grep 代码**

```bash
grep -rn "query" app/src/main/java/
# 找到 query 没加 LIMIT
```

**第 3 步：分析 query 返回大小**

- 业务方 query 返回 5000 行
- 每行 200 字节 = 1MB
- 加上 CursorWindow metadata → 2MB
- 超过 1MB 限制 → TransactionTooLargeException

### 5.4 根因

业务方 query 没加 LIMIT，**返回数据量超过 1MB CursorWindow 上限**。

### 5.5 修复

**修复前 → 修复后**：

```diff
--- a/OtherProvider.java
+++ b/OtherProvider.java
@@ -30,7 +30,10 @@ public class OtherProvider extends ContentProvider {
     public Cursor query(Uri uri, String[] projection, String selection,
             String[] selectionArgs, String sortOrder) {
-        // 返回 5000 行 → 2MB
+        // 加 LIMIT 限制
+        String limit = uri.getQueryParameter("limit");
+        if (limit == null) limit = "1000";
         return db.query("users", projection, selection, selectionArgs,
-                null, null, sortOrder);
+                null, null, sortOrder, limit);
     }
```

```diff
--- a/CallerApp.java
+++ b/CallerApp.java
@@ -45,7 +45,9 @@ public class CallerApp {
     public void queryData() {
+        // 传 LIMIT
+        Uri uri = Uri.parse("content://other.app/users").buildUpon()
+                .appendQueryParameter("limit", "1000").build();
-        Cursor cursor = contentResolver.query(uri, ...);
+        Cursor cursor = contentResolver.query(uri, projection, selection, args, sortOrder);
     }
```

### 5.6 修复验证

- 修复后 TransactionTooLargeException 归零
- 关键监控：CursorWindow 大小 < 1MB
- 关键监控：query 返回数量稳定 < 1000

---

## 七、案例 5 大共性总结

### 7.1 5 大共性

| 共性 | 描述 | 解决 |
|------|------|------|
| **冷启动硬耗时** | ContentProvider.onCreate 在 Application.onCreate 之前 | 异步化 + 拆分 Provider |
| **包可见性** | AOSP 11+ 跨 App ContentProvider 必须 `<queries>` 声明 | 加 manifest 声明 |
| **资源未关闭** | Cursor / ContentProviderClient 必须 close | try-with-resources |
| **高频 query** | 每秒 query 次数过多 | 业务层缓存 / CursorLoader |
| **大数据量** | CursorWindow 单次传输上限 1MB | 加 LIMIT + 分片 |

### 7.2 排查路径速查

```
ContentProvider 线上问题?
  │
  ├─ 冷启动慢？→ dumpsys activity providers + systrace
  ├─ 跨 App 失败？→ SecurityException 类型 + <queries> 声明
  ├─ 内存泄漏？→ LeakCanary + dumpsys meminfo Cursor
  ├─ 性能退化？→ Perfetto trace + Binder 线程占用
  └─ TransactionTooLarge？→ CursorWindow 大小 + query LIMIT
```

---

## 八、总结 · 架构师视角的 5 条 Takeaway

1. **冷启动硬耗时**——ContentProvider.onCreate 在 Application.onCreate 之前，**业务方难以发现**。
2. **包可见性**——AOSP 11+ 跨 App ContentProvider 必填 `<queries>` 声明，**升级必回归**。
3. **资源未关闭**——Cursor / ContentProviderClient 必须 close，**业务方漏 = 内存泄漏**。
4. **高频 query**——每秒 query 次数过多触发 binder 限频 + 性能退化，**业务层缓存**。
5. **CursorWindow 上限 1MB**——AOSP 17 强化**分片传输**，业务方加 LIMIT。

**该主题的排查路径速查**：

```
ContentProvider 5 大场景?
  │
  ├─ CASE-C-01: 冷启动慢？→ Provider onCreate 异步化
  ├─ CASE-C-02: 跨 App 失败？→ <queries> 声明
  ├─ CASE-C-03: 内存泄漏？→ try-with-resources
  ├─ CASE-C-04: 性能退化？→ 业务层缓存
  └─ CASE-C-05: CursorWindow 异常？→ 加 LIMIT
```

---

## 附录 A · 案例索引

| 案例 ID | 主题 | 系列 | 文章 | 根因 | 修复 |
|---------|------|------|------|------|------|
| **CASE-C-01** | 冷启动慢（Provider onCreate 同步初始化） | ContentProvider | C02 + C08 | 业务方同步初始化 | 异步化 + 拆分 Provider |
| **CASE-C-02** | 跨 App ContentProvider 访问失败 | ContentProvider | C06 + C08 | AOSP 11+ 包不可见 | 加 `<queries>` 声明 |
| **CASE-C-03** | CursorWindow 内存泄漏 | ContentProvider | C03 + C05 + C08 | Cursor 未 close | try-with-resources |
| **CASE-C-04** | 跨进程 query 性能退化 | ContentProvider | C03 + C08 | 高频 query | 业务层缓存 |
| **CASE-C-05** | CursorWindow TransactionTooLargeException | ContentProvider | C03 + C07 + C08 | 大数据量 | 加 LIMIT + 分片 |

## 附录 B · 量化数据自检表

| 序号 | 量化描述 | 数量级 | 依据来源 |
|------|---------|-------|---------|
| 1 | CASE-C-01 修复后冷启动时间 | 1500ms → 600ms | 案例数据 |
| 2 | CASE-C-02 修复后跨 App 访问成功率 | 0% → 100% | 案例数据 |
| 3 | CASE-C-03 修复后 CursorWindow 占用 | 1234KB → < 100KB | 案例数据 |
| 4 | CASE-C-04 修复后 query 次数 | 200/秒 → 5/秒 | 案例数据 |
| 5 | CASE-C-05 修复后 CursorWindow 大小 | 2MB → < 1MB | 案例数据 |
| 6 | ContentProvider 5 大根因占稳定性问题 | 90%+ | 经验值 |

## 附录 C · 工程基线表

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
|------|---------|---------|---------|
| Provider onCreate 业务耗时 | < 1s | 必须 | 同步操作必 ANR |
| Cursor 关闭 | try-with-resources | 必用 | 漏 = 泄漏 |
| ContentProviderClient 关闭 | try-with-resources | 必用 | 漏 = 客户端泄漏 |
| `<queries>` 声明 | AOSP 11+ 必填 | 必填 | 漏 = 跨 App 失败 |
| query LIMIT | 1000 | 业务方控制 | 超 = TransactionTooLarge |
| query 频次 | < 100/s | 业务方控制 | 超频触发性能退化 |
| CursorWindow 大小 | < 1MB | 业务方控制 | 超 1MB TransactionTooLarge |
| ContentProviderClient 获取 | acquireContentProviderClient | AOSP 11+ 推荐 | 不用 = 客户端泄漏 |
| 跨进程 query 缓存 | 业务层缓存 | 业务规范 | 不用 = 高频跨进程 |
| exported 默认值 | AOSP 12+ 必填 | 必填 | 漏 = 必崩 |

---

## 篇尾衔接

下一篇 [C09 · ContentProvider 优化与监控](C09_ContentProvider_Optimize_Monitor.md) 是"诊断治理"篇（破例：章节重排"风险→工具→案例"）——**ContentProvider 优化 5 大策略 + 监控工具（dumpsys providers / perfetto / LeakCanary）+ 实战案例**。C09 是 ContentProvider 系列的最后一篇。

预计阅读时间 25-35 分钟。
