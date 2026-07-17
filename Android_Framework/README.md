# 02_Java_API_Framework（Java API框架层）

## 📋 目录说明

本目录专注于 **Android Java API框架层**的稳定性机制和问题分析。Framework层是Android系统的核心，提供了应用程序开发的标准API，并实现了各种系统服务。

## 🎯 学习目标

- 深入理解Framework层的稳定性机制（ANR检测、Watchdog等）
- 掌握Framework层源码分析和问题定位方法
- 理解Framework层与Kernel层的交互机制

## 📚 目录结构

```
02_Java_API_Framework/
├── ANR_Detection/    # ANR检测机制（ActivityManagerService）
├── Watchdog/         # Watchdog系统挂死监控
├── Service/          # Service ANR机制
├── Broadcast/        # Broadcast ANR机制
├── Input/            # Input事件分发系统
└── Window/           # Window窗口系统
```

## 🔗 关键组件

### ANR_Detection
- ActivityManagerService中的ANR检测机制
- Input、Broadcast、Service三种ANR类型的检测
- traces.txt生成机制

### Watchdog
- SystemServer Watchdog机制
- HandlerChecker监控机制
- Binder线程池阻塞分析

### Service
- Service ANR超时机制
- Service生命周期与ANR的关系
- Service启动和绑定流程

### Broadcast
- BroadcastReceiver ANR机制
- 有序广播和无序广播的处理
- BroadcastQueue管理机制

### Input
- Input事件分发机制
- InputDispatcher和InputChannel
- Input超时与ANR的关系

### Window
- Window窗口系统架构
- WindowManager和WindowManagerService
- Surface和SurfaceFlinger
- 窗口与输入系统的交互

## 📖 学习建议

1. 重点阅读AOSP源码，理解Framework层的实现细节
2. 结合实际问题，分析Framework层的稳定性机制
3. 理解Framework层如何与Kernel层交互

---

**对应Android架构**：Java API Framework 层
