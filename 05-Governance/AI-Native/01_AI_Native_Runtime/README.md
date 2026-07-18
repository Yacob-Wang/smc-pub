# 01 AI_Native_Runtime（端侧 AI 基础设施）

> **AI Native X 子系列 1 / 3**
>
> **定位**：机制层——"AI 怎么在端侧跑起来"
>
> **核心技术栈**：HAL AI / NNAPI / TFLite / ONNX Runtime Mobile / GPU Delegate / NPU Driver / DSP Delegate / 端侧 LLM
>
> **篇数**：8 篇
>
> **攻破时段**：2026 H2（与 ART 主干 M1-M4 同步）

---

## 篇章列表

| 编号 | 标题 | 状态 | 与 v2.1 主干耦合 |
|---|---|---|---|
| **R01** | 端侧 AI 演进史：从 NNAPI 到 AI HAL 到端侧 LLM | 待写 | 总览 |
| **R02** | Android AI HAL：从 Hardware Abstraction 到 Vendor Extension | 待写 | HAL 系列 + ART M5 JNI |
| **R03** | NNAPI 架构深度：模型加载 → 编译 → 加速器分发 → 推理 | 待写 | ART M3 编译执行 + Power |
| **R04** | TFLite 运行时：Interpreter / Delegate / GPU/NPU 后端 | 待写 | ART M5 JNI + Process 调度 |
| **R05** | ONNX Runtime Mobile：跨平台端侧推理 | 待写 | 与 R04 对比 |
| **R06** | GPU Delegate：OpenGL ES / Vulkan / OpenCL 后端 | 待写 | GPU_Driver + ART M5 JNI |
| **R07** | NPU 驱动：从 HAL 到厂商 SDK（高通 Hexagon / 联发科 APU / 麒麟 NPU） | 待写 | Power_Management + Thermal |
| **R08** | 端侧 LLM 落地：Llama / Qwen / Phi 在 Android 上的推理优化 | 待写 | ART M4 内存 GC + Power + ART M8 启动 |

---

## 关键技术抓手

- **AI HAL 演进**：AIDL → Stable AIDL → Hardware Interface
- **NNAPI 1.0 → 2.0 → 1.3（Control Flow / Token）**
- **TFLite GPU Delegate** 的 OpenCL/Vulkan 后端原理
- **NPU 厂商 SDK 差异**：Hexagon DSP AOT 编译、APU MDLA、麒麟 NPU DaVinci
- **端侧 LLM 关键技术**：
  - 量化（INT4 / INT8 / W4A16 / SmoothQuant）
  - KV Cache 优化（PagedAttention / FlashAttention）
  - Speculative Decoding
  - 模型分片（Splitwise / PowerInfer）

---

## 与稳定性主干的耦合

| v2.1 主干/支线 | AI Runtime 关联点 |
|---|---|
| **ART M3 编译执行** | TFLite 模型本身的 AOT 编译 + 解释器/JIT |
| **ART M5 JNI 与引用** | TFLite 通过 JNI 调 Native 推理 + JNI GlobalRef 泄漏 |
| **ART M8 启动流程** | 端侧 LLM 预加载时机 + Zygote fork 影响 |
| **ART M4 内存 GC** | 端侧 LLM 内存占用（1B 模型 ≈ 1-2GB） + GC 影响 |
| **Process 调度** | AI 推理任务的 CPU/NPU 调度 + cgroup |
| **Power_Management** | NPU 推理的功耗 + Thermal throttling |
| **支线 B1 分区** | 模型文件在哪个分区（OTA 影响） |
| **支线 B3 so 加载** | TFLite / ONNX Runtime 的 .so 加载 |

---

## 简历可讲案例（项目 4）

> **某 App 端侧 AI 推理性能治理**（500ms → 80ms）：
> - **问题**：端侧 AI 推理 500ms+，功耗高、内存峰值大
> - **机制定位**：从 TFLite Runtime + GPU/NPU Delegate + 端侧 LLM 出发，识别"算子未融合 + 量化未做 + Delegate 错配"三类根因
> - **解法**：
>   - TFLite Runtime 优化：模型量化（FP32 → INT8）、算子融合、KV Cache
>   - Delegate 选型：CPU → GPU → NPU 三级 fallback
>   - 算子下沉：高频算子用 NPU 厂商 SDK 重写
>   - 内存优化：中间 tensor 复用、KV Cache 量化
> - **量化**：推理延迟 500ms → 80ms（-84%），内存峰值 1.2GB → 380MB（-68%），功耗 -45%
> - **团队动作**：**主导** 项目（**跨 3 个团队**：算法 / 端侧 SDK / 性能组）

---

## 写作顺序建议

```
R01（总览）→ R02（AI HAL）→ R03（NNAPI）→ R04（TFLite）→ R05（ONNX）→ R06（GPU Delegate）→ R07（NPU）→ R08（端侧 LLM）
```

**与 v2.1 ART 主干的衔接**：
- 写 R04 时回顾 ART M5 JNI（已在 v2.1）
- 写 R08 时回顾 ART M4 内存 GC（已有 50+ 篇素材）+ ART M8 启动流程
- 写 R07 时关联 Power_Management PM07（Thermal Aware 调度）

---

## 参考资料

- AOSP：`frameworks/ml/`、`hardware/interfaces/neuralnetworks/`、`packages/modules/NeuralNetworks/`
- TFLite：https://www.tensorflow.org/lite
- ONNX Runtime：https://onnxruntime.ai/docs/tutorials/mobile/
- 厂商 SDK：高通 Hexagon NN SDK / 联发科 NeuroPilot / 华为 HiAI
- 端侧 LLM：mlc-llm / llama.cpp / PowerInfer / TensorRT-LLM

---

> **子系列导航**：[← AI Native X 总览](../README-AI_Native_X系列.md) | [02 AI_Native_OS →](../02_AI_Native_OS/README.md) | [03 AI_for_Stability →](../03_AI_for_Stability/README.md)
