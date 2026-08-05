# 13.B 进程生命周期

> **从 fork 到死：进程诞生、调度、退出全链路**
>
> 共 32 篇 · P0 第 13 章拆分子章

## 子节导航

### 13.B.1 Framework 进程管理（9 篇）
> AMS 冷启动 / Zygote fork / ART 内世界 / Kernel 接口 / CFS 调度

### 13.B.2 杀进程专题（4 篇）
> AMS 触发到进程退出的全链路 + do_exit 9 步

### 13.B.3 Kernel 进程子系统（13 篇）
> task_struct / fork / execve / CFS / 多核调度 / cgroup_v2

### 13.B.4 cgroup 资源管理（6 篇）
> cgroup 演进 / 抽象 / 资源维度 / Android 17 树 / OOM 与杀进程

## 文件清单

- [01-cgroup的诞生与历史演进_从2006到Android17](01-cgroup的诞生与历史演进_从2006到Android17.md)
- [01-杀进程全链路：从AMS触发到进程完全退出](01-杀进程全链路：从AMS触发到进程完全退出.md)
- [01-进程子系统全景与边界契约](01-进程子系统全景与边界契约.md)
- [01-进程总览：从点图标看app进程的诞生消亡与全栈抽象](01-进程总览：从点图标看app进程的诞生消亡与全栈抽象.md)
- [02-AMS-冷启动判定与进程启动链路](02-AMS-冷启动判定与进程启动链路.md)
- [02-cgroup核心抽象_subsys_css_cftype_cgroup_file](02-cgroup核心抽象_subsys_css_cftype_cgroup_file.md)
- [02-do_exit内部9个sub-step深潜](02-do_exit内部9个sub-step深潜.md)
- [02-task_struct全景拆解](02-task_struct全景拆解.md)
- [03-Zygote-Android进程工厂](03-Zygote-Android进程工厂.md)
- [03-cgroup三大资源维度的统一抽象_Process_Memory_IO](03-cgroup三大资源维度的统一抽象_Process_Memory_IO.md)
- [03-杀进程慢的真正根因：诱因-根因-证伪](03-杀进程慢的真正根因：诱因-根因-证伪.md)
- [03-进程的诞生_fork_clone_vfork](03-进程的诞生_fork_clone_vfork.md)
- [04-Android17_cgroup树与libprocessgroup](04-Android17_cgroup树与libprocessgroup.md)
- [04-应用进程首生-fork到ActivityThread](04-应用进程首生-fork到ActivityThread.md)
- [04-杀进程监控与治理：ftrace-perfetto-告警-治理](04-杀进程监控与治理：ftrace-perfetto-告警-治理.md)
- [04-进程的执行_execve与程序加载](04-进程的执行_execve与程序加载.md)
- [05-ART进程内世界：JIT-AOT与GC](05-ART进程内世界：JIT-AOT与GC.md)
- [05-cgroup与稳定性的核心关系_OOM_Throttle_杀进程](05-cgroup与稳定性的核心关系_OOM_Throttle_杀进程.md)
- [05-进程的退出_do_exit与资源回收](05-进程的退出_do_exit与资源回收.md)
- [06-Framework视角的Kernel进程接口_procfs_cgroup_pidfd](06-Framework视角的Kernel进程接口_procfs_cgroup_pidfd.md)
- [06-cgroup可观测性全景与风险地图_实战收口](06-cgroup可观测性全景与风险地图_实战收口.md)
- [06-调度基础架构_调度类与上下文切换](06-调度基础架构_调度类与上下文切换.md)
- [07-CFS调度器_vruntime与红黑树](07-CFS调度器_vruntime与红黑树.md)
- [07-调度与资源：CFS与进程生死](07-调度与资源：CFS与进程生死.md)
- [08-调度扩展_RT_Deadline_Idle](08-调度扩展_RT_Deadline_Idle.md)
- [08-进程稳定性风险全景与跨层治理](08-进程稳定性风险全景与跨层治理.md)
- [09-多核调度_SMP负载均衡_EAS](09-多核调度_SMP负载均衡_EAS.md)
- [09-杀进程慢的根因定位实战](09-杀进程慢的根因定位实战.md)
- [10-cgroup_v2_内核里的资源控制器](10-cgroup_v2_内核里的资源控制器.md)
- [11-信号机制_从产生到投递](11-信号机制_从产生到投递.md)
- [12-进程间通信_pipe_fifo_shm_futex_Binder](12-进程间通信_pipe_fifo_shm_futex_Binder.md)
- [13-进程调试与稳定性关联](13-进程调试与稳定性关联.md)

---

**返回**：[第 13 章 进程与生命周期](../index.md)
