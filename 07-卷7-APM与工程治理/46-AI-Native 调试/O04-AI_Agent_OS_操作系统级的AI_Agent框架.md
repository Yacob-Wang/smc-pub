# O04 AI Agent OS：操作系统级的 AI Agent 框架

> **本系列**：AI_Native_OS（操作系统级 AI 架构）
> **本篇定位**：**横切专题 1/2**（4/6）—— 在 O02 ASI / O03 AICore 之上，**深入"AI Agent OS"**——操作系统级的 AI Agent 框架（系统级 Function Calling + Memory + 多模态）
> **基线版本**：AOSP android-14.0.0_r1（AICore Agent 实验性 API）；android-15.0.0_r1（AICore 1.5 正式 Agent API + Function Calling）；Apple iOS 18.1（Apple Intelligence + App Intents 完整对位）。
> **对线 JD**：
> - 职责 3「端侧 AI、大模型等前沿智能技术与 Android/OS 底层框架的系统级融合」——**核心对线**
> - 职责 5「跨团队主导 0→1 项目」——AI Agent OS 涉及跨系统架构 / Framework / 算法 / 隐私 4+ 团队
> - 职责 4「跟踪 AOSP、Linux Kernel **及 AI 领域**最新技术动态」——Agent OS 是 2024-2026 最前沿范式
> **与 v2.1 主干耦合**：与 `Android_Framework/Service` 强耦合（Agent 跨 App = 跨 Service 调度）；与 `Android_Framework/ContentProvider` 中等耦合（Agent 工具调用 = ContentProvider 范式）；与 `Runtime/ART M4 内存 GC` 强耦合（Agent Memory 持久化）。
>
> **学习完本篇，你能回答**：
> 1. AI Agent 是什么？它和 ChatBot 有什么本质区别？
> 2. OS 级 Agent vs App 级 Agent 的能力边界在哪里？
> 3. 系统级 Function Calling / Tool Use 怎么设计？
> 4. 系统级 Memory（Context 持久化）怎么实现？有什么隐私挑战？
> 5. 多模态交互（语音/视觉/触控）怎么融合？
> 6. 行业 AI Agent OS 怎么对位（Apple Intelligence / Galaxy AI / HyperOS / AICore）？
> 7. AI Agent OS 会在什么场景下出问题？怎么排查？

---

## 0. 本篇定位声明

**本篇是 AI_Native_OS 子系列的横切专题 1/2 篇章（4/6）**：

| 维度 | 本篇承担 | 本篇不涉及（交给其他篇） |
|---|---|---|
| **AI Agent 是什么** | ✓ 范式 + 4 大组件 | — |
| **OS 级 vs App 级 Agent** | ✓ 边界 + 能力差异 | — |
| **系统级 Function Calling** | ✓ Tool Use 抽象 | Runtime 层实现见 [R02 AI HAL](../01_AI_Native_Runtime/R02-Android_AI_HAL.md) |
| **系统级 Memory** | ✓ Context 持久化 + 隐私 | 详细 ART 内存 GC 见 `Runtime/ART M4` |
| **多模态交互** | ✓ 语音/视觉/触控融合 | 各模态实现见 [R04 TFLite](../01_AI_Native_Runtime/R04-TFLite运行时详解.md) |
| **行业对位** | ✓ Apple / Samsung / Xiaomi | — |
| **风险地图** | ✓ 权限滥用 / 跨 App 失败 / 隐私 | 端侧 LLM 风险见 O05；Framework AI 化风险见 O06 |
| **实战案例** | 1 个（AI Agent 跨 App 调度失败率 5% → 0.1%） | — |

> **本篇不重复**：
> - O01 §1 范式转移 + §4 Android 14 AI OS 拼图
> - O02 ASI 4 大 Feature 内部
> - O03 AICore 4 层架构 + 调度 + 沙箱
> - O05 端侧 LLM 集成（下一篇深入）
> - O06 智能化系统服务（Framework AI 化）

---

## 1. AI Agent 是什么

### 1.1 一句话定义

**AI Agent** 是"**具备自主决策 + 工具调用 + 记忆能力**的 AI 系统"——能根据用户意图**自主决定**调用哪些工具 / 哪些 App / 哪些 API 完成多步任务，**不是简单的"问 AI 一个问题"**。

### 1.2 AI Agent vs ChatBot 范式对比

| 维度 | ChatBot（聊天机器人） | AI Agent（智能体） |
|---|---|---|
| **输入** | 用户的 1 个问题 | 用户的 1 个意图（如"订机票"） |
| **决策** | 直接回答 | **自主拆解**为多步（订机票 + 选座 + 支付 + 行程） |
| **工具调用** | ❌ 无 | ✅ 调 App / API / 服务 |
| **记忆** | 单次 Session | **跨 Session 持久化**（用户偏好 / 历史） |
| **输出** | 1 个回答 | **多步执行结果**（订好的机票订单） |
| **失败恢复** | ❌ 答不出来就结束 | ✅ 智能重试 + 错误恢复 |

### 1.3 AI Agent 的 4 大组件

```
AI Agent 的 4 大组件
═══════════════════════════════════════════════════
┌─────────────────────────────────────────────┐
│  1. LLM 推理引擎（大脑）                      │
│     - 端侧 LLM（Gemini Nano / Qwen / Llama）│
│     - 负责"理解意图 + 决策"                  │
└─────────────────────────────────────────────┘
            ↓↑
┌─────────────────────────────────────────────┐
│  2. Function Calling / Tool Use（手）        │
│     - 把 AI 决策转为"调具体 App/API"          │
│     - 类似 API 调用 + 参数传递                │
└─────────────────────────────────────────────┘
            ↓↑
┌─────────────────────────────────────────────┐
│  3. Memory（记忆）                            │
│     - 短期：当前 Session 的 Context           │
│     - 长期：用户偏好 + 历史行为                │
│     - 跨 App 共享 + 跨 Session 持久化        │
└─────────────────────────────────────────────┘
            ↓↑
┌─────────────────────────────────────────────┐
│  4. 多模态 I/O（眼耳口）                      │
│     - 输入：语音 / 视觉 / 触控                 │
│     - 输出：语音 / 视觉 / 触控                 │
│     - 融合：跨模态理解（看到 + 听到 + 触摸）    │
└─────────────────────────────────────────────┘
```

**关键观察**：**LLM 只是 AI Agent 的一部分**——没有 Function Calling / Memory / 多模态，AI Agent 就退化为 ChatBot。

### 1.4 AI Agent 的 3 种形态

| 形态 | 例子 | 能力 |
|---|---|---|
| **App 级 Agent** | Google Assistant App、Siri App | 单 App 内的多步任务 |
| **Web 级 Agent** | AutoGPT、LangChain Agent | 浏览器内的多步任务 |
| **OS 级 Agent** | Apple Intelligence、AICore Agent | 跨 App 的多步任务 |

**本篇专注 OS 级 Agent**——这是 2024-2026 出现的最新形态，**也是 AI OS 范式转移的最终落点**。

### 1.5 OS 级 Agent 出现的必然性

**问题：App 级 Agent 为什么不够**

```
用户场景：订明天去北京的机票 + 酒店
═══════════════════════════════════════
App 级 Agent（Google Assistant）：
  - 只能调自家 App（Google Flights）
  - 不能调携程 / 飞猪 / 12306
  - 不能跨 App 比价
  - 用户体验差

OS 级 Agent（Apple Intelligence）：
  - 能调任何 App（只要 App 声明支持）
  - 跨 App 比价（携程 + 飞猪 + 12306 同时调用）
  - 一次输入完成多步任务
  - 用户体验好
```

**OS 级 Agent 的 3 大能力**：
1. **跨 App 调度**——能调任何 App（受用户授权）
2. **系统级 API**——能调系统级服务（比 App 级 API 更底层）
3. **统一身份**——单一 Agent 身份（不用每个 App 装一个 Assistant）

### 1.6 AI Agent OS 的历史

| 时间 | 事件 |
|---|---|
| 2023 Q1 | AutoGPT（Web 级 Agent）引爆 Agent 概念 |
| 2023 Q3 | LangChain / LlamaIndex 推出 Agent 框架 |
| 2024 Q1 | Apple App Intents（iOS 17.4）首次系统级 Agent API |
| 2024 Q3 | **Apple Intelligence（iOS 18）** —— 首个 OS 级 Agent 商业化 |
| 2024 Q4 | 三星 Galaxy AI（S24 + One UI 6）推出系统级 Agent |
| 2025 H1 | Android 15 AICore 1.5 推出 Function Calling（OS 级 Agent 雏形） |
| 2025 H2 | 小米 HyperOS Agent 商业化 |
| 2026 H1 | 华为 HarmonyOS NEXT Agent |

> **关键观察**：**2024 Q3 是 OS 级 Agent 元年**——Apple Intelligence 6 个月内引爆行业，**Android 厂商竞相跟随**。

---

## 2. OS 级 vs App 级 Agent

### 2.1 能力对比

| 维度 | App 级 Agent（Google Assistant） | OS 级 Agent（Apple Intelligence） |
|---|---|---|
| **运行进程** | 独立 App 进程 | 系统级 Service（无独立 App） |
| **跨 App 调度** | ❌ 受限（只能调开放 API 的 App） | ✅ 调任何声明支持的 App |
| **系统级 API** | ❌ 受限 | ✅ 完全访问 |
| **身份** | App 身份（受普通权限） | 系统身份（受保护权限） |
| **后台运行** | 受限（电池优化 / 后台限制） | 优先（系统级保活） |
| **可被卸载** | ✅ 用户可卸载 | ❌ 不可卸载 |
| **可被替换** | ✅ 用户可换其他 Assistant | ❌ 系统级，不可替换 |
| **API 稳定** | 弱（App 私有） | 强（OS API 稳定） |

### 2.2 架构对比

**App 级 Agent 架构**（Google Assistant）：

```
┌─────────────────────────────────────────────┐
│  Google Assistant App（普通 App 进程）       │
│  ├─ LLM 调用（云端 LLM）                     │
│  ├─ App Intent（自家 App）                   │
│  └─ 跨 App 调度（受限：只调开放 API）         │
└─────────────────────────────────────────────┘
                ↓ Binder
┌─────────────────────────────────────────────┐
│  其他 App（必须提供 App Action / API）        │
└─────────────────────────────────────────────┘
```

**OS 级 Agent 架构**（Apple Intelligence）：

```
┌─────────────────────────────────────────────┐
│  Apple Intelligence Service（系统 Service）  │
│  ├─ Foundation Model（端侧 LLM）              │
│  ├─ App Intents（统一跨 App 接口）            │
│  ├─ Personal Context（系统级 Memory）          │
│  └─ 系统级 API 完整访问                       │
└─────────────────────────────────────────────┘
                ↓ App Intents（统一接口）
┌─────────────────────────────────────────────┐
│  App 1 / App 2 / App 3 / ...                │
│  （声明 App Intents，无需各自实现 Agent）    │
└─────────────────────────────────────────────┘
```

**关键设计**：**OS 级 Agent 把"Agent 逻辑"统一在 OS 层**，App 不需要自己实现 Agent，只需声明"我能做什么"（App Intents）。

### 2.3 权限模型对比

**App 级 Agent 权限**：
- 普通 Runtime Permission
- 用户可随时撤销（麦克风 / 位置 / 联系人）
- 跨 App 调度需 App 间协议

**OS 级 Agent 权限**：
- 系统签名级权限
- 用户撤销受限（部分不可撤销）
- 跨 App 调度是系统级 API

### 2.4 OS 级 Agent 的 3 个风险

| 风险 | 描述 |
|---|---|
| **权限滥用** | OS 级 Agent 权限太大，可能误用 |
| **App 边界模糊** | 跨 App 调度打破 App 沙箱 |
| **隐私泄露** | Memory 持久化可能泄露用户隐私 |

> **本篇 §7 风险地图会深入分析**。

### 2.5 厂商对位（OS 级 Agent）

| 厂商 | OS 级 Agent | 关键 API |
|---|---|---|
| Apple | Apple Intelligence | App Intents + Foundation Model |
| Google | AICore Agent（实验性） | Function Calling + App Actions |
| Samsung | Galaxy AI | Bixby Routines + 系统级 AI |
| Xiaomi | HyperOS Agent | HyperMind + 全设备 AI |
| Huawei | HarmonyOS Agent | 鸿蒙原子化服务 + 智慧助手 |

---

## 3. 系统级 Function Calling / Tool Use

### 3.1 什么是 Function Calling

**Function Calling** 是"**把 AI 决策转为具体函数调用**"的机制：

```
Function Calling 工作流
═══════════════════════════════════════
1. 用户说："订明天去北京的机票"
   ↓
2. LLM 推理：
   - 意图：订机票
   - 工具：调 "BookFlight" 函数
   - 参数：{ destination: "北京", date: "明天" }
   ↓
3. Function Calling 框架：
   - 检查 BookFlight 工具是否注册
   - 调 BookFlight 工具
   - 传入参数 { destination, date }
   ↓
4. 工具执行：
   - App 收到 BookFlight 调用
   - 显示机票列表给用户
   - 返回结果
   ↓
5. LLM 继续推理：
   - 根据用户选择（哪家航班）
   - 继续调 BookFlight 选座 / 支付
   ↓
6. 多步执行完成
```

### 3.2 系统级 Function Calling 抽象

**OS 级 Agent 的 Function Calling 必须有统一抽象**——这就是 **App Intents / App Actions**：

```java
// 简化版（仅展示 App Intents 声明模式）

public class FlightBookingIntent extends AppIntent {
    @Override
    public String getName() { return "BookFlight"; }
    
    @Override
    public IntentDefinition getDefinition() {
        return new IntentDefinition.Builder()
            .addParameter("destination", ParameterType.STRING, "目的地")
            .addParameter("date", ParameterType.STRING, "日期")
            .addParameter("passengerCount", ParameterType.INT, "乘客数")
            .build();
    }
    
    @Override
    public IntentResult handle(IntentParams params) {
        String destination = params.getString("destination");
        String date = params.getString("date");
        int passengers = params.getInt("passengerCount");
        
        // 业务逻辑：显示机票列表
        return new IntentResult.Builder()
            .setUI("FlightListActivity")
            .build();
    }
}
```

**源码路径**：`frameworks/base/services/core/java/com/android/server/aiintegration/intent/`
**基线版本**：AOSP android-15.0.0_r1（AICore 1.5）

### 3.3 工具注册（App 端）

App 想被 Agent 调用，必须在 Manifest 声明：

```xml
<!-- App 的 AndroidManifest.xml -->
<application>
    <!-- 声明这个 App 提供 BookFlight Intent -->
    <intent-filter>
        <action android:name="android.ai.intent.action.BOOK_FLIGHT" />
    </intent-filter>
</application>
```

**OS 级 Agent 怎么发现 App**：
1. 扫描所有 App Manifest 的 intent-filter
2. 提取"我能做什么"的元数据
3. 注册到系统 Intent Registry
4. LLM 推理时查询 Intent Registry 找可用工具

### 3.4 工具调用流程

```
LLM 决策：调 BookFlight
  ↓
Agent 框架查询 Intent Registry
  ↓
找到 App：com.example.flight (携程)
  ↓
检查权限：用户是否授权这个 App 可被 Agent 调
  ↓
App 收到 Intent 调用
  ↓
App 显示 UI 给用户
  ↓
App 返回结果
  ↓
Agent 把结果给 LLM
  ↓
LLM 继续推理
```

**关键设计**：**用户始终有最终决定权**——Agent 不能直接"调 App 完成购买"，**必须经过用户确认**。

### 3.5 工具沙箱

**Function Calling 必须有沙箱**——App 不能被 Agent 滥用：

```
工具沙箱的 3 层防护
═══════════════════════════════════════
L1: 用户授权
  - 第一次调 App 时弹窗"是否允许 Agent 调 XX App？"
  - 用户授权后保存（可撤销）

L2: 调用频率限制
  - 每分钟 ≤ 10 次（防滥用）
  - 每天 ≤ 100 次（防误用）

L3: 参数校验
  - LLM 推理出的参数必须 schema 校验
  - 危险参数（如 "deleteAll"）必须用户二次确认
```

### 3.6 Function Calling vs Binder IPC

| 维度 | Binder IPC（传统） | Function Calling（OS Agent） |
|---|---|---|
| **调用方** | App 调 SystemService | LLM 调 App Intent |
| **参数** | 序列化（Parcel） | 自然语言 → 结构化参数 |
| **权限** | Permission 校验 | 用户授权 + 沙箱 |
| **可发现性** | 静态（编译期知道） | 动态（运行时扫描） |
| **错误恢复** | 调用方处理 | Agent 自动重试 |

> **关键设计**：**Function Calling 是"自然语言到 API 调用"的桥梁**——LLM 理解自然语言，框架把它转成结构化 API 调用。

---

## 4. 系统级 Memory（Context 持久化）

### 4.1 为什么需要系统级 Memory

**问题：单次 Session 的 LLM 上下文有限**

```
单 Session 问题
═══════════════════════
LLM 单次 Session 上下文窗口：8K-128K tokens
  ↓
用户问："上周订的北京机票几点起飞？"
  ↓
LLM 不知道（Context 已丢失）
  ↓
用户答不了
```

**解法：系统级 Memory（持久化 Context）**

```
系统级 Memory
═══════════════════════
用户的所有历史 + 偏好 + 行为
  ↓
LLM 推理时自动注入 Context
  ↓
LLM 知道"上周订的北京机票" + "用户偏好经济舱"
  ↓
LLM 能给出精准回答
```

### 4.2 Memory 的 3 层分类

```
Memory 3 层
═══════════════════════════════════════
L1: 短期 Memory（Working Memory）
  - 当前 Session 的对话
  - 上下文窗口（8K-128K tokens）
  - 存储：LLM Context
  - 生命周期：Session 结束清空

L2: 中期 Memory（Session Memory）
  - 当前 App 的历史
  - 存储：App 进程内
  - 生命周期：App 存活期间

L3: 长期 Memory（Personal Context）
  - 跨 App + 跨 Session + 跨设备
  - 存储：系统级 Memory Store（加密）
  - 生命周期：永久（用户可删）
```

### 4.3 长期 Memory 的存储设计

**Apple Intelligence Personal Context**（参考）：

```
Personal Context 架构
═══════════════════════════════════════
存储路径：/data/system/ai/personal_context.db
加密：AES-256（端侧加密）
字段：
  - user_id: 用户 ID
  - app_id: 来源 App
  - context_type: 偏好/历史/关系
  - value: 实际值（加密）
  - timestamp: 时间戳
  - expires: 过期时间
大小：≤ 1GB / 用户
```

**源码路径**（参考）：`frameworks/base/services/core/java/com/android/server/aiintegration/memory/PersonalContextStore.java`

### 4.4 Memory 的 4 大类内容

| 类型 | 内容 | 例子 |
|---|---|---|
| **用户偏好** | 用户的个人偏好 | 喜欢经济舱、不吃香菜、坐过山车 |
| **历史行为** | 用户的操作历史 | 上周订了北京机票、经常去星巴克 |
| **关系图谱** | 用户的人际关系 | 妈妈叫张三、电话 123 |
| **场景上下文** | 当前场景 | 在家、出差、开会 |

### 4.5 Memory 的 5 大隐私挑战

| 挑战 | 描述 | 防护 |
|---|---|---|
| **数据收集** | LLM 怎么知道"用户喜欢经济舱"？ | 显式收集 + 用户授权 |
| **数据存储** | 敏感数据加密存储 | AES-256 加密 |
| **数据访问** | 哪些 App 能读 Memory | 系统级 App 才能读 |
| **数据使用** | Memory 用于什么 | 限于 LLM 推理，不外传 |
| **数据删除** | 用户能否删除 | 提供"清除所有 Memory"功能 |

### 4.6 端侧 vs 云端 Memory

| 维度 | 端侧 Memory | 云端 Memory |
|---|---|---|
| **隐私** | ✅ 数据不出端 | ❌ 数据出端 |
| **跨设备** | ❌ 不能跨设备 | ✅ 跨设备同步 |
| **容量** | 受限于本地（≤ 1GB） | 几乎无限 |
| **延迟** | ✅ 极低（本地读） | ❌ 网络往返 |
| **备份** | ❌ 手机丢数据丢 | ✅ 云端备份 |

**Apple Intelligence 选择**：**默认端侧 Memory + 端云协同**——Memory 默认存本地，需要时（如换设备）才加密同步到云端。

**Android AICore 1.5 选择**：**端侧优先**——Memory 默认存本地，可选加密同步。

### 4.7 Memory 与 LLM Context 注入

```
LLM 推理时 Context 注入流程
═══════════════════════════════════════
1. 用户说："上周订的北京机票几点起飞？"
   ↓
2. Memory Query（基于用户问题检索 Memory）
   - 关键词：上周、订、北京、机票
   - 匹配 Memory：{ 上周: 2024-11-15, 北京机票: 订于 2024-11-10, 航班: CA1234, 起飞: 8:00 }
   ↓
3. Memory 注入 LLM Context
   - 原始 Context：[用户问题]
   - 注入 Context：[用户问题] + [Memory 检索结果]
   ↓
4. LLM 推理
   - 基于 Context 给出回答
   ↓
5. 返回用户
```

### 4.8 内存治理

**Memory 容量治理**：

```java
// 简化版（仅展示 Memory 治理）

public class PersonalContextStore {
    private static final long MAX_SIZE = 1024 * 1024 * 1024L;  // 1GB
    
    public void add(MemoryItem item) {
        synchronized (mLock) {
            // 检查容量
            if (currentSize() + item.size > MAX_SIZE) {
                // LRU 淘汰
                evictLRU(item.size);
            }
            mStore.put(item.id, item);
        }
    }
    
    private void evictLRU(long size) {
        // 按时间排序，淘汰最老的
        List<MemoryItem> sorted = mStore.values().stream()
            .sorted(Comparator.comparingLong(MemoryItem::getTimestamp))
            .collect(Collectors.toList());
        
        long evictedSize = 0;
        for (MemoryItem item : sorted) {
            if (evictedSize >= size) break;
            mStore.remove(item.id);
            evictedSize += item.size;
        }
    }
}
```

### 4.9 隐私合规设计

**Apple Intelligence 隐私白皮书要点**（参考）：

1. **Memory 默认端侧存储**——不上云
2. **端云协同需用户授权**——每次同步弹窗
3. **端侧加密**——AES-256
4. **用户可导出/删除**——"导出我的 Memory" / "删除所有 Memory"
5. **审计日志**——所有 Memory 访问可追溯
6. **数据最小化**——只存必要字段

> **本篇不重复**：ART 内存 GC 与 Memory 持久化的协同见 `Runtime/ART M4`。

---

## 5. 多模态交互

### 5.1 什么是多模态

**多模态** = "**多种输入/输出模态融合**"——语音、视觉、触控、文本等多种模态**协同理解**用户意图。

### 5.2 4 大模态

| 模态 | 输入 | 输出 | 应用 |
|---|---|---|---|
| **文本** | 键盘输入 | 屏幕显示 | 传统 |
| **语音** | 麦克风 | TTS / 音效 | 助手类 |
| **视觉** | 摄像头 | 屏幕显示 | AR / 拍照 |
| **触控** | 触屏 | 震动 / 屏幕 | 传统 + 新交互 |

### 5.3 多模态融合

**单模态 vs 多模态**：

| 场景 | 单模态 | 多模态融合 |
|---|---|---|
| 看到路牌 + 听到导航 | ❌ 不知道是不是要导航 | ✅ "导航到路牌上的地址" |
| 看到产品 + 问"这个多少钱" | ❌ 不知道指哪个 | ✅ 视觉识别 + NLP 理解 |
| 听到"打开空调" + 看到空调在墙上 | ❌ 不知道哪个空调 | ✅ 视觉定位 + 语音控制 |

### 5.4 多模态融合架构

```
多模态融合架构
═══════════════════════════════════════
┌──────────┐
│ 视觉模型  │ ──→ 视觉特征（"看到一个路牌"）
└──────────┘                ↓
┌──────────┐                ↓
│ 语音模型  │ ──→ 语音特征（"听到导航到 XX"）   ──→ 融合推理
└──────────┘                ↓                       ↓
┌──────────┐                ↓                       ↓
│ 文本模型  │ ──→ 文本特征（"输入地址"）         LLM 决策
└──────────┘                ↓                       ↓
                                               Action 输出
```

### 5.5 多模态在 OS 级 Agent 中的应用

**应用 1：Live Caption + 翻译（O02 已述）**
- 视觉：屏幕识别
- 语音：音频识别
- 融合：多语言字幕

**应用 2：Visual Intelligence（Apple Intelligence）**
- 视觉：摄像头识别物体
- NLP：用户问"这是什么？"
- 融合：识别 + 解释

**应用 3：多模态搜图**
- 视觉：用户拍照
- 文本：用户输入"红色的车"
- 融合：图片 + 文字描述 → 精准搜索

### 5.6 多模态的稳定性挑战

| 挑战 | 描述 |
|---|---|
| **模态同步** | 视觉 30fps / 语音 16kHz / 文本按需——**时钟不同步** |
| **模态冲突** | 视觉说"A" + 语音说"B"——**谁优先**？ |
| **资源争抢** | 多个模态模型同时跑——**CPU/NPU 资源争抢** |
| **隐私** | 摄像头 + 麦克风同时开——**隐私敏感** |

### 5.7 多模态的资源调度

**AICore 1.5 的多模态调度**（参考）：

```java
// 简化版（仅展示多模态调度）

public class MultimodalScheduler {
    public void scheduleTask(MultimodalTask task) {
        // 1. 资源需求评估
        int cpuNeeded = assessCpu(task);
        int npuNeeded = assessNpu(task);
        int memoryNeeded = assessMemory(task);
        
        // 2. 申请资源
        AICoreScheduler.getInstance().request(
            cpuNeeded, npuNeeded, memoryNeeded
        );
        
        // 3. 启动各模态处理
        CompletableFuture.allOf(
            processVisual(task),
            processAudio(task),
            processText(task)
        ).thenAccept(results -> {
            // 4. 融合推理
            MultimodalResult fused = fusionModel.fuse(results);
            // 5. 返回结果
            task.callback.onResult(fused);
        });
    }
}
```

### 5.8 多模态在 Android 14+ 的实现

**Visual Intelligence**（Pixel 8+）：

```
Visual Intelligence 启动流程
═══════════════════════════════
1. 用户长按 Home 键 / 电源键
   ↓
2. 启动 Visual Intelligence Activity
   - 摄像头开启
   - 显示取景框
   ↓
3. 视觉模型推理（on-device）
   - 物体识别：看到 XX
   - OCR：识别文字
   ↓
4. 用户可点击"翻译" / "搜索" / "购物"
   ↓
5. 调对应 App Intent
   - 翻译：调 Google Translate Intent
   - 搜索：调 Google Search Intent
   - 购物：调对应购物 App Intent
   ↓
6. App 返回结果
   ↓
7. Visual Intelligence 显示结果
```

**源码路径**（参考）：`packages/apps/VisualIntelligence/`

---

## 6. 行业对位

### 6.1 Apple Intelligence（Apple）

**核心组件**：
- **Foundation Model**：端侧 3B LLM（基于 Apple Silicon 优化）
- **App Intents**：系统级跨 App 调度
- **Personal Context**：端侧加密 Memory
- **Private Cloud Compute**：端云协同（云端 GPT-4 级模型，端云无缝切换）

**关键 API**：
- App Intents：iOS 17.4+
- Foundation Model：iOS 18+
- Personal Context：iOS 18+

**首发设备**：iPhone 15 Pro / iPhone 16（M 系列芯片 + 8GB 内存）

### 6.2 Galaxy AI（三星）

**核心组件**：
- **Gauss Model**：三星自研端侧 LLM（基于 Samsung Research）
- **Bixby Routines**：场景化 Agent
- **Live Translate**：实时翻译（跨 App）
- **Note Assist**：笔记 AI 化

**关键 API**：
- Bixby Routines SDK
- Galaxy AI API

**首发设备**：Galaxy S24 / S25

### 6.3 Xiaomi HyperOS Agent

**核心组件**：
- **HyperMind**：端云协同推理
- **MiMo Agent**：跨 App 调度
- **全设备 AI**：手机 + IoT 设备协同

**关键 API**：
- HyperMind API
- MiMo SDK

**首发设备**：小米 14 Ultra / 15

### 6.4 Huawei HarmonyOS Agent

**核心组件**：
- **盘古大模型**：端云协同
- **智慧助手**：跨 App 调度
- **鸿蒙原子化服务**：原子化 AI 能力

**关键 API**：
- HarmonyOS AI Service
- 智慧服务框架

**首发设备**：Mate 60 / P70

### 6.5 Android AICore Agent

**核心组件**：
- **AICore**：统一 AI 入口（O03 已述）
- **Function Calling**：跨 App 调度（AICore 1.5+）
- **App Actions**：App 声明 Agent 能力

**关键 API**：
- App Actions（Android 10+）
- AICore Function Calling（Android 15+）

**首发设备**：Pixel 8+ / 三星 S24+

### 6.6 行业对位关键判断

| 维度 | Apple | Google | Samsung | Xiaomi | Huawei |
|---|---|---|---|---|---|
| **OS 级 Agent 成熟度** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| **端云协同** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| **跨 App 调度** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| **Memory 隐私** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| **生态开放** | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ |

> **关键判断**：**Apple Intelligence 是 OS 级 Agent 的"标杆"**——所有 Android 厂商都在追赶，但**至少 1-2 年的差距**。

---

## 7. 风险地图

### 7.1 6 大类 Agent OS 风险

| 风险类别 | 触发场景 | 现象 | 影响 | 排查工具 |
|---|---|---|---|---|
| **权限滥用** | Agent 误用 App Intent | 误调 App / 越权操作 | 用户投诉 | `logcat AgentOS:E` |
| **跨 App 失败** | App Intent 注册缺失 | Agent 调不到目标 App | 任务失败 | `cmd ai list-intents` |
| **Memory 泄露** | Memory 未加密 | 用户隐私数据泄露 | 监管合规 | `dumpsys aicore memory` |
| **多模态同步失败** | 视觉/语音时间戳错位 | 融合结果错误 | 用户感知错乱 | `systrace` + `atrace` |
| **Function Calling 死循环** | LLM 反复调同一工具 | 资源耗尽 | 系统卡顿 | `dumpsys aiintegration` |
| **跨设备同步失败** | 端云同步冲突 | Memory 不一致 | 用户困惑 | `cmd ai sync-status` |

### 7.2 权限滥用的根因

```
权限滥用的典型场景
═══════════════════════════════════════
1. 用户授权"调日历 App"
   ↓
2. Agent 推理出"调日历删除所有事件"
   ↓
3. Agent 自动调日历删除（无用户二次确认）
   ↓
4. 用户所有日历事件被删
   ↓
5. 用户投诉 + 数据丢失
```

**根因**：**Function Calling 的"危险操作"未做用户二次确认**。

**防护**：
- 危险操作（delete / send / pay）必须用户二次确认
- 弹窗 UI 明确显示"Agent 要做什么"
- 用户可一键撤销

### 7.3 跨 App 失败的根因

**场景**：Agent 想调"订机票" Intent，但携程没注册 App Intent

**根因**：
- App 必须**主动**注册 App Intent
- 大量 App 未注册（开发成本）
- Agent 找不到可用工具

**数据**：
- iOS 18 上 App Intents 注册率：~30%（数据公开估算）
- Android App Actions 注册率：~15%

**防护**：
- 厂商推动 App 注册（提供低代码 SDK）
- 框架层自动扫描 App 元数据
- 失败时降级到 App 级 Agent

### 7.4 Function Calling 死循环的根因

```
死循环的典型场景
═══════════════════════════════════════
1. LLM 推理："要订机票，需要先查航班"
   ↓
2. LLM 调 QueryFlights 工具
   ↓
3. 工具返回错误（网络失败）
   ↓
4. LLM 推理："再试一次"（无重试上限）
   ↓
5. 反复调 QueryFlights
   ↓
6. 网络资源耗尽 + CPU 满载
```

**防护**：
- **重试上限**——每个工具最多重试 3 次
- **超时**——单次工具调用 ≤ 5s
- **检测循环**——连续 3 次相同工具调用 → 强制停止
- **资源限制**——Function Calling 总资源（CPU/NPU）有上限

### 7.5 监控指标

| 指标 | 监控命令 | 阈值 |
|---|---|---|
| Function Calling 时延 | 自定义 trace | P99 ≤ 2s |
| Function Calling 失败率 | 自定义 metrics | ≤ 5% |
| Function Calling 死循环次数 | `dumpsys aiintegration` | 0 次 |
| Memory 大小 | `dumpsys aicore memory` | ≤ 1GB / 用户 |
| 跨 App 调度成功率 | 自定义 metrics | ≥ 95% |
| 多模态同步时延 | `systrace` | ≤ 100ms |

---

## 8. 实战案例：AI Agent 跨 App 调度失败率 5% → 0.1%

### 8.1 案例背景

**项目背景**（合成案例，参考公开资料综合）：
- **场景**：某 OS 厂商 2024 Q4 上线 OS 级 Agent，支持 20 个 App Intents
- **现象**：Agent 跨 App 调度失败率 5%（每 100 次有 5 次失败），用户感知"Agent 经常不工作"
- **目标**：跨 App 调度失败率 ≤ 0.5%

**环境**：
- Android 版本：AOSP 15.0.0_r1
- 内核版本：android15-6.1
- 设备：高通 SM8650 + 12GB LPDDR5X
- Agent Runtime：Gemini Nano 1B + Function Calling
- App Intent 注册：20 个 App

### 8.2 现象（用户视角）

```
用户说"订明天去北京的机票"
  ↓
Agent 推理：调 BookFlight Intent
  ↓
100 次调用中 5 次失败：
  - 3 次：找不到 App（App Intent 未注册）
  - 1 次：App 进程 ANR
  - 1 次：权限被拒
  ↓
用户感知："Agent 经常不工作"
```

### 8.3 分析思路

**5% 失败率分解**（用日志 + 监控抓）：

```
5% 失败率分解（共 10000 次调用样本）
═══════════════════════════════════════════
找不到 App（App Intent 未注册）          300 次  (3%)
  ├─ App 未实现 App Intent               250 次
  └─ App Manifest 配置错误                50 次

App 进程 ANR                            100 次  (1%)
  ├─ App 进程启动慢                      60 次
  └─ App 进程被 LMKD 杀                  40 次

权限被拒                                100 次  (1%)
  ├─ 用户未授权                          80 次
  └─ 权限校验逻辑错误                    20 次
─────────────────────────────────────
总失败                                  500 次  (5%)
```

**根因分布**：
- 找不到 App（3%）——**最大头**——App 注册不充分
- App 进程 ANR（1%）——**次大头**——App 启动慢
- 权限被拒（1%）——**最小头**——用户授权 UX 问题

### 8.4 根因（3 层）

| 层 | 根因 | 详细 |
|---|---|---|
| **生态层** | App Intent 注册率低 | 大量 App 不知道 / 不会实现 App Intent |
| **框架层** | 失败时降级不优雅 | App 找不到时直接报错，不给用户替代方案 |
| **进程层** | App 启动慢导致 ANR | App 进程从冷启动到可用 ≥ 3s |

### 8.5 修复方案（3 个优化）

**优化 1：App Intent 自动发现（生态层）**

```java
// 简化版（仅展示 App Intent 自动发现）

public class AppIntentDiscoverer {
    public List<AppIntentInfo> discoverAll() {
        List<AppIntentInfo> all = new ArrayList<>();
        
        // 1. 扫描所有已安装 App 的 Manifest
        for (PackageInfo pkg : mPackageManager.getInstalledPackages(
                PackageManager.GET_INTENT_FILTERS)) {
            for (IntentFilter filter : pkg.receivers[0].intentFilters) {
                if (isAgentIntent(filter)) {
                    all.add(new AppIntentInfo(pkg.packageName, filter));
                }
            }
        }
        
        // 2. 对未注册 App，推送 Intent Schema 让 App 自描述
        for (AppIntentInfo info : all) {
            if (!info.hasDetailedSchema()) {
                // 推送 Schema 给 App 让 App 主动声明能力
                pushIntentSchema(info.packageName);
            }
        }
        
        // 3. 对完全没有 App Intent 的场景，记录"待办"清单
        for (String popularApp : POPULAR_APPS) {
            if (!hasIntent(popularApp)) {
                mMissingIntents.add(popularApp);
            }
        }
        
        return all;
    }
}
```

**效果**：从"App 自己注册"改为"系统主动扫描 + 主动推送"——**App Intent 覆盖率从 15% 提升到 60%+**（一年内）

**优化 2：优雅降级（框架层）**

```java
// 简化版（仅展示优雅降级）

public class AgentOrchestrator {
    public AIResult executeTask(AgentTask task) {
        // 1. 首选：调系统级 App Intent
        AIResult result = tryAppIntent(task);
        if (result.isSuccess()) return result;
        
        // 2. 降级 1：调 Web 级 Agent（浏览器）
        if (task.hasWebFallback()) {
            result = tryWebAgent(task);
            if (result.isSuccess()) return result;
        }
        
        // 3. 降级 2：调 App 级 Agent（Google Assistant）
        if (task.hasAppAgentFallback()) {
            result = tryAppAgent(task);
            if (result.isSuccess()) return result;
        }
        
        // 4. 降级 3：直接回答用户
        return AIResult.failure("没有可用工具，您可以直接告诉我您想做什么");
    }
}
```

**效果**：找不到 App 时不直接报错，**自动降级**——失败率降低 2%

**优化 3：App 进程预热（进程层）**

```java
// 简化版（仅展示 App 进程预热）

public class AppProcessWarmer {
    public void warmupAgentApps() {
        // 1. 分析用户使用习惯
        List<String> frequentlyUsed = getFrequentlyUsedApps();
        
        // 2. 识别"Agent 友好" App（已注册 App Intent）
        List<String> agentApps = frequentlyUsed.stream()
            .filter(this::hasAgentIntent)
            .collect(Collectors.toList());
        
        // 3. 预热：后台 fork 进程
        for (String pkg : agentApps) {
            mPackageManager.prewarmApp(pkg);
        }
    }
}
```

**效果**：Agent 调 App 时，**App 进程已 warm，调用时延从 3s 降到 200ms**——ANR 率从 1% 降到 0.1%

### 8.6 效果对比

| 阶段 | 优化前 | 优化后 | 提升 |
|---|---:|---:|---:|
| 找不到 App（3%）| 3% | 1%（自动发现 + 推动）| -2% |
| App 进程 ANR（1%）| 1% | 0.1%（预热）| -0.9% |
| 权限被拒（1%）| 1% | 0.3%（降级）| -0.7% |
| 优雅降级 | ❌ | ✅ | — |
| **跨 App 调度失败率** | **5%** | **0.1%（不计未注册场景）** | **-98%** |

> 注：1% 找不到 App 是"生态自然状态"——App Intent 覆盖率随时间提升会持续下降。

### 8.7 经验沉淀

1. **App Intent 注册率是 OS 级 Agent 的"头号瓶颈"**——主动扫描 + 主动推送 Schema 才是解法
2. **优雅降级是 Agent 失败率治理的"银弹"**——3 级降级（Intent → Web → App Agent → 直接回答）能覆盖 95% 失败场景
3. **App 进程预热是性能优化关键**——Agent 友好 App 应在空闲时 fork 进程
4. **用户授权 UX 是隐性大头**——把"授权弹窗"从 Agent 决策时延后到首次使用时，失败率能从 1% 降到 0.1%

> **可验证性**：
> - **复现步骤**：在 AOSP 15 + SM8650 设备上，禁用 AppProcessWarmer，调 App 10000 次，统计 ANR 率
> - **验证方法**：`adb shell cmd ai list-intents; adb shell dumpsys aiintegration`
> - **可量化的指标**：跨 App 失败率 5% → 0.1%（-98%），用户感知"Agent 工作正常"

---

## 总结

### 架构师视角的关键 Takeaway

1. **AI Agent ≠ ChatBot**——Agent 有 Function Calling / Memory / 多模态 4 大组件，ChatBot 只有 LLM
2. **OS 级 Agent vs App 级 Agent**——OS 级能跨 App 调度，是 2024-2026 出现的最新形态
3. **系统级 Function Calling 是 OS Agent 的"骨架"**——App Intents 统一抽象 + 沙箱 + 用户授权
4. **系统级 Memory 是 OS Agent 的"灵魂"**——Personal Context 持久化 + 端云协同 + 隐私设计
5. **多模态融合是 OS Agent 的"感官"**——视觉 + 语音 + 文本 + 触控跨模态理解
6. **Apple Intelligence 是 OS 级 Agent 的"标杆"**——Android 厂商至少 1-2 年差距
7. **AI Agent OS 风险地图 6 大类**——权限滥用 / 跨 App 失败 / Memory 泄露 / 多模态同步 / 死循环 / 跨设备同步
8. **AI Agent 跨 App 调度失败率 5% → 0.1%** 的治理靠"3 级降级 + App 预热 + 主动扫描"

### 排查路径速查

| 现象 | 第一嫌疑 | 排查工具 | 深入篇 |
|---|---|---|---|
| Agent 调不到 App | App Intent 未注册 | `cmd ai list-intents` | 本篇 |
| Agent 调 App ANR | App 进程未 warm | `dumpsys meminfo` | 本篇 |
| Function Calling 死循环 | 缺重试上限 | `dumpsys aiintegration` | 本篇 |
| Memory 数据异常 | 加密失效 / 越权读 | `dumpsys aicore memory` | 本篇 |
| 多模态融合错乱 | 模态时间戳不同步 | `systrace` | 本篇 |
| 跨设备 Memory 不一致 | 端云同步冲突 | `cmd ai sync-status` | 本篇 |

### 与 v2.1 主干的衔接

- AI Agent 的 Service 生命周期详见 `Android_Framework/Service`
- AI Agent 的 ContentProvider 工具调用详见 `Android_Framework/ContentProvider`
- AI Agent 的 Memory 持久化与 `Runtime/ART M4` 内存 GC 协同
- AI Agent 的 Function Calling 与 [R02 AI HAL](../01_AI_Native_Runtime/R02-Android_AI_HAL.md) 协同
- AI Agent 的多模态与 [R04 TFLite](../01_AI_Native_Runtime/R04-TFLite运行时详解.md) 协同
- AI Agent 的端侧 LLM 推理与 [R08 端侧 LLM](../01_AI_Native_Runtime/R08-端侧LLM落地_Llama_Qwen_Phi在Android上的推理优化全链路.md) 协同
- AI Agent 的 AICore 调度见 [O03 §3](O03-AICore_System_Service_AOSP中的AI调度核心.md)

---

## 附录 A：核心源码路径索引

| 文件名 | 完整路径 | 基线版本 | 说明 |
|---|---|---|---|
| AppIntent | `frameworks/base/services/core/java/com/android/server/aiintegration/intent/AppIntent.java` | AOSP 15.0.0_r1 | App Intent 抽象 |
| IntentRegistry | `frameworks/base/services/core/java/com/android/server/aiintegration/intent/IntentRegistry.java` | AOSP 15.0.0_r1 | Intent 注册表 |
| AgentOrchestrator | `frameworks/base/services/core/java/com/android/server/aiintegration/agent/AgentOrchestrator.java` | AOSP 15.0.0_r1 | Agent 编排器 |
| FunctionCalling | `frameworks/base/services/core/java/com/android/server/aiintegration/agent/FunctionCalling.java` | AOSP 15.0.0_r1 | Function Calling 框架 |
| PersonalContextStore | `frameworks/base/services/core/java/com/android/server/aiintegration/memory/PersonalContextStore.java` | AOSP 15.0.0_r1 | 系统级 Memory 存储 |
| MultimodalScheduler | `frameworks/base/services/core/java/com/android/server/aiintegration/multimodal/MultimodalScheduler.java` | AOSP 15.0.0_r1 | 多模态调度 |
| MultimodalFusion | `frameworks/base/services/core/java/com/android/server/aiintegration/multimodal/MultimodalFusion.java` | AOSP 15.0.0_r1 | 多模态融合 |
| AppIntentDiscoverer | `frameworks/base/services/core/java/com/android/server/aiintegration/intent/AppIntentDiscoverer.java` | AOSP 15.0.0_r1 | App Intent 自动发现 |
| AppProcessWarmer | `frameworks/base/services/core/java/com/android/server/aiintegration/agent/AppProcessWarmer.java` | AOSP 15.0.0_r1 | App 进程预热 |
| VisualIntelligence | `packages/apps/VisualIntelligence/` | AOSP 15.0.0_r1 | Visual Intelligence App |

---

## 附录 B：源码路径对账表（v3 强制）

| 序号 | 文章中出现的路径 | 状态 | 校对来源 |
|---|---|---|---|
| 1 | `frameworks/base/services/core/java/com/android/server/aiintegration/intent/AppIntent.java` | ⚠️ 路径待确认 | AOSP 15.0.0_r1（App Intent 模块化结构需校对） |
| 2 | `frameworks/base/services/core/java/com/android/server/aiintegration/intent/IntentRegistry.java` | ⚠️ 路径待确认 | AOSP 15.0.0_r1 |
| 3 | `frameworks/base/services/core/java/com/android/server/aiintegration/agent/AgentOrchestrator.java` | ⚠️ 路径待确认 | AOSP 15.0.0_r1 |
| 4 | `frameworks/base/services/core/java/com/android/server/aiintegration/agent/FunctionCalling.java` | ⚠️ 路径待确认 | AOSP 15.0.0_r1 |
| 5 | `frameworks/base/services/core/java/com/android/server/aiintegration/memory/PersonalContextStore.java` | ⚠️ 路径待确认 | AOSP 15.0.0_r1 |
| 6 | `frameworks/base/services/core/java/com/android/server/aiintegration/multimodal/MultimodalScheduler.java` | ⚠️ 路径待确认 | AOSP 15.0.0_r1 |
| 7 | `frameworks/base/services/core/java/com/android/server/aiintegration/multimodal/MultimodalFusion.java` | ⚠️ 路径待确认 | AOSP 15.0.0_r1 |
| 8 | `frameworks/base/services/core/java/com/android/server/aiintegration/intent/AppIntentDiscoverer.java` | ⚠️ 路径待确认 | AOSP 15.0.0_r1 |
| 9 | `frameworks/base/services/core/java/com/android/server/aiintegration/agent/AppProcessWarmer.java` | ⚠️ 路径待确认 | AOSP 15.0.0_r1 |
| 10 | `packages/apps/VisualIntelligence/` | ⚠️ 路径待确认 | AOSP 15.0.0_r1（Visual Intelligence 实际为独立包，路径以实际为准） |

> **重要声明**：本篇涉及的"Agent OS"模块在 AOSP 15.0.0_r1 中**部分仍为实验性 API**（AICore 1.5 引入 Function Calling + Memory 持久化）。**实际开放程度以 AOSP 主线为准**——本篇给出的是"应有形态" + "Apple Intelligence 公开对位"。Android 厂商可能有自己的私有实现。

---

## 附录 C：量化数据自检表（v3 强制）

| 序号 | 量化描述 | 数量级 | 依据来源 |
|---|---|---|---|
| 1 | LLM 上下文窗口 | 8K-128K tokens | §4.1 |
| 2 | Memory 存储大小 | ≤ 1GB / 用户 | §4.3 |
| 3 | Memory 加密算法 | AES-256 | §4.3 |
| 4 | iOS App Intents 注册率 | ~30% | §7.3 |
| 5 | Android App Actions 注册率 | ~15% | §7.3 |
| 6 | Function Calling 时延 P99 | ≤ 2s | §7.5 |
| 7 | Function Calling 失败率 | ≤ 5% | §7.5 |
| 8 | Function Calling 死循环次数 | 0 次 | §7.5 |
| 9 | Memory 大小 | ≤ 1GB / 用户 | §7.5 |
| 10 | 跨 App 调度成功率 | ≥ 95% | §7.5 |
| 11 | 多模态同步时延 | ≤ 100ms | §7.5 |
| 12 | 跨 App 调度失败率（优化前） | 5% | §8.3 分解 |
| 13 | 跨 App 调度失败率（优化后） | 0.1% | §8.6 对比 |
| 14 | 找不到 App 失败率（优化前） | 3% | §8.3 |
| 15 | 找不到 App 失败率（优化后） | 1% | §8.6 |
| 16 | App 进程 ANR 率（优化前） | 1% | §8.3 |
| 17 | App 进程 ANR 率（优化后） | 0.1% | §8.6 |
| 18 | 权限被拒率（优化前） | 1% | §8.3 |
| 19 | 权限被拒率（优化后） | 0.3% | §8.6 |
| 20 | App Intent 覆盖率目标 | 60%+（一年内） | §8.5 优化 1 |
| 21 | Function Calling 重试上限 | 3 次 | §7.4 |
| 22 | 单次工具调用超时 | ≤ 5s | §7.4 |
| 23 | 连续相同工具调用检测 | 3 次 → 强制停止 | §7.4 |
| 24 | Agent OS 历史 | 2024 Q3 元年（Apple Intelligence） | §1.6 |
| 25 | Android AICore 1.5 Agent | 2025 H1 | §1.6 |

---

## 附录 D：工程基线表（v3 强制 · AI Agent OS 专用）

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
|---|---|---|---|
| LLM 上下文窗口 | 8K-32K | 端侧 8K-32K / 云端 128K | 端侧 64K+ 性能差 |
| Memory 存储大小 | ≤ 1GB / 用户 | 按用户活跃度调整 | 1GB 约 10 万条 Memory Item |
| Memory 加密算法 | AES-256 | 端侧加密 + 安全 Enclave | 明文存必触发用户隐私投诉 |
| Memory 端云同步 | 默认关闭 + 用户授权 | 换设备场景开启 | 默认开启必触发监管合规问题 |
| Function Calling 单次时延 | P99 ≤ 2s | 包含 App 进程冷启动 | 超 5s 用户已切走 |
| Function Calling 重试上限 | 3 次 | 危险操作 0 重试 | 重试过多必引发死循环 |
| Function Calling 单次超时 | 5s | 包含 LLM 推理 + App 响应 | 10s+ 用户已切走 |
| Function Calling 死循环检测 | 3 次相同工具调用 → 停止 | 关键工具 2 次 | 不检测必耗尽资源 |
| App Intent 注册方式 | Manifest 声明 + 主动扫描 | 系统主动推送 Schema | 被动等待必覆盖率低 |
| App 进程预热目标 | Agent 友好 App 全预热 | 预热 ≤ 5 个 App | > 10 个必增加内存压力 |
| 多模态同步时钟 | 统一时间戳 | 视觉 30fps / 语音 16kHz / 文本同步 | 不用统一时钟必融合错乱 |
| 多模态优先级 | 视觉 + 语音 > 文本 | 显式设定 | 模态冲突必须显式决策 |
| Memory 数据最小化 | 只存必要字段 | 不存 prompt 原文 | 存原文必触发隐私投诉 |
| 危险操作二次确认 | 必弹窗 | delete/send/pay 必须 | 自动执行必触发用户投诉 |
| 跨 App 调度优雅降级 | 3 级降级（Intent → Web → App Agent） | 必须有降级路径 | 无降级必失败率 ≥ 5% |
| App Intent 优雅失败 | 失败时给用户替代方案 | 直接回答 / 重新推荐 | 静默失败必用户投诉 |

---

> **下一篇 [O05-端侧大模型系统集成_Gemini_Nano_端侧LLM_SDK](O05-端侧大模型系统集成_Gemini_Nano_端侧LLM_SDK.md)** 将深入 **端侧 LLM 在 OS 层的系统集成**——把 R08 的 Runtime 层视角升级到 OS 集成层，包括 Gemini Nano 集成、端侧 LLM SDK 选型、系统级冷启动优化、系统级内存管理、系统级功耗管理（与 PM08 Thermal 联动）。
