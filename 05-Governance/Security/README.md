# Security · 安全 + 稳定性

> **状态**：🟡 占位（计划 2026-09 启动 P2）
> **目标读者**：安全工程师 / 稳定性架构师
> **版本基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`

## 计划内容（5-7 篇）

1. PAC-BTI 防护对性能影响
2. MTE 内存标签扩展（Memory Tagging Extension）
3. SELinux 与稳定性的相互作用
4. 漏洞利用导致的崩溃（提权崩溃 / ROP 链）
5. Rust 化对安全 + 稳定性的双重收益
6. AOSP 17 eBPF 签名验证

## 跨系列引用

- 上游：[01-Mechanism/Kernel/GKI](../../01-Mechanism/Kernel/GKI/) 通用内核
- 上游：[01-Mechanism/Kernel/Memory_Management](../../01-Mechanism/Kernel/Memory_Management/) 内存保护
- 上游：[03-Forensics/F05-KE](../../03-Forensics/F05-KE/) KE 取证
- 配套：[05-Governance/AI-Native/01_AI_Native_Runtime](../AI-Native/01_AI_Native_Runtime/) Rust 化趋势
