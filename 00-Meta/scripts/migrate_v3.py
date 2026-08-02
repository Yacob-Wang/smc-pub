"""卷 3 核心机制迁移脚本：按 章节-素材映射表-v1.md 把 01-Mechanism 全部迁到 03-卷3-核心机制/ 各章。

策略：
1. 不递归改文件内容（链接修复由 link_repair_v3.py 单独跑）
2. 用 git mv 触发 rename 检测
3. 目标目录如不存在先创建
4. 按章节输出 git mv 报告
"""
import subprocess
import os
from pathlib import Path

REPO = Path(r"C:\Users\deepLife\Documents\GitHub\smc-pub")
V3 = "03-卷3-核心机制"

# 路径映射：(src_relpath, dest_dir)
# src 是 01-Mechanism 或 06-Foundation 下的 .md 文件
# dest_dir 是 03-卷3-核心机制/下的章节目录
MIGRATIONS = {
    "第12章-Binder IPC 深度": {
        "dest": f"{V3}/12-Binder IPC 深度",
        "files": [
            "01-Mechanism/Kernel/Binder/01-Binder总览.md",
            "01-Mechanism/Kernel/Binder/02-Binder驱动.md",
            "01-Mechanism/Kernel/Binder/03-一次Binder调用的完整旅程.md",
            "01-Mechanism/Kernel/Binder/04-Binder内存模型.md",
            "01-Mechanism/Kernel/Binder/05-Binder线程模型.md",
            "01-Mechanism/Kernel/Binder/06-Binder对象生命周期.md",
            "01-Mechanism/Kernel/Binder/07-Binder稳定性风险全景.md",
            "01-Mechanism/Kernel/Binder/08-Binder诊断工具与治理体系.md",
            "01-Mechanism/Kernel/Binder/09-Binder-debugfs日志解读实战.md",
            "01-Mechanism/Kernel/Binder/10-Binder-oneway限流与防护方案.md",
            "01-Mechanism/Kernel/Binder/11-Binder厂商预防与治理方案调研报告.md",
            "01-Mechanism/Kernel/Binder/12-Binder节点文件全景与问题实战.md",
            "01-Mechanism/Kernel/Binder/13-Rust Binder专题.md",
            "01-Mechanism/Kernel/Binder/README-Binder系列.md",
        ],
    },
    "第13章-进程与生命周期": {
        "dest": f"{V3}/13-进程与生命周期",
        "files": [
            # 01-Mechanism/Framework/Process + Process_Exit
            "01-Mechanism/Framework/Process/01-进程总览：从点图标看app进程的诞生消亡与全栈抽象.md",
            "01-Mechanism/Framework/Process/02-AMS-冷启动判定与进程启动链路.md",
            "01-Mechanism/Framework/Process/03-Zygote-Android进程工厂.md",
            "01-Mechanism/Framework/Process/04-应用进程首生-fork到ActivityThread.md",
            "01-Mechanism/Framework/Process/05-ART进程内世界：JIT-AOT与GC.md",
            "01-Mechanism/Framework/Process/06-Framework视角的Kernel进程接口_procfs_cgroup_pidfd.md",
            "01-Mechanism/Framework/Process/07-调度与资源：CFS与进程生死.md",
            "01-Mechanism/Framework/Process/08-进程稳定性风险全景与跨层治理.md",
            "01-Mechanism/Framework/Process/09-杀进程慢的根因定位实战.md",
            "01-Mechanism/Framework/Process/README-进程架构演进系列.md",
            "01-Mechanism/Framework/Process_Exit/01-杀进程全链路：从AMS触发到进程完全退出.md",
            "01-Mechanism/Framework/Process_Exit/02-do_exit内部9个sub-step深潜.md",
            "01-Mechanism/Framework/Process_Exit/03-杀进程慢的真正根因：诱因-根因-证伪.md",
            "01-Mechanism/Framework/Process_Exit/04-杀进程监控与治理：ftrace-perfetto-告警-治理.md",
            "01-Mechanism/Framework/Process_Exit/README-杀进程系列.md",
            # 01-Mechanism/Framework/{Activity,Broadcast,ContentProvider,Service,Signing}
            "01-Mechanism/Framework/Activity/01_Activity_Overview.md",
            "01-Mechanism/Framework/Activity/02_Activity_Start_SourceCode.md",
            "01-Mechanism/Framework/Activity/03_Activity_Lifecycle.md",
            "01-Mechanism/Framework/Activity/04_Activity_LaunchMode_Task.md",
            "01-Mechanism/Framework/Activity/05_Activity_Intent_Resolve.md",
            "01-Mechanism/Framework/Activity/06_Activity_ConfigChange.md",
            "01-Mechanism/Framework/Activity/07_Activity_Launch_ANR.md",
            "01-Mechanism/Framework/Activity/08_Activity_Jump_Latency.md",
            "01-Mechanism/Framework/Activity/09_Activity_Memory_Governance.md",
            "01-Mechanism/Framework/Activity/README.md",
            "01-Mechanism/Framework/Broadcast/B01_Broadcast_Overview.md",
            "01-Mechanism/Framework/Broadcast/B02_Broadcast_Register.md",
            "01-Mechanism/Framework/Broadcast/B03_Broadcast_Send.md",
            "01-Mechanism/Framework/Broadcast/B04_Broadcast_Ordered.md",
            "01-Mechanism/Framework/Broadcast/B05_Broadcast_Sticky_Evolution.md",
            "01-Mechanism/Framework/Broadcast/B06_Broadcast_LocalBroadcast_Alternative.md",
            "01-Mechanism/Framework/Broadcast/B07_Broadcast_BackgroundRestriction.md",
            "01-Mechanism/Framework/Broadcast/B08_Broadcast_ANR_Landscape.md",
            "01-Mechanism/Framework/Broadcast/B09_Broadcast_SystemBoot.md",
            "01-Mechanism/Framework/Broadcast/README.md",
            "01-Mechanism/Framework/ContentProvider/C01_ContentProvider_Overview.md",
            "01-Mechanism/Framework/ContentProvider/C02_ContentProvider_Init.md",
            "01-Mechanism/Framework/ContentProvider/C03_ContentProvider_CRUD.md",
            "01-Mechanism/Framework/ContentProvider/C04_ContentProvider_CrossProcess.md",
            "01-Mechanism/Framework/ContentProvider/C05_ContentProvider_Observer.md",
            "01-Mechanism/Framework/ContentProvider/C06_ContentProvider_PackageVisibility.md",
            "01-Mechanism/Framework/ContentProvider/C07_ContentProvider_Binder_ANR.md",
            "01-Mechanism/Framework/ContentProvider/C08_ContentProvider_Cases.md",
            "01-Mechanism/Framework/ContentProvider/C09_ContentProvider_Optimize_Monitor.md",
            "01-Mechanism/Framework/ContentProvider/README.md",
            "01-Mechanism/Framework/Service/01_Service_Overview.md",
            "01-Mechanism/Framework/Service/02_Service_StartService_Path.md",
            "01-Mechanism/Framework/Service/03_Service_BindService_Path.md",
            "01-Mechanism/Framework/Service/04_Service_FGS_TypeRestricted.md",
            "01-Mechanism/Framework/Service/05_Service_WorkManager_Evolution.md",
            "01-Mechanism/Framework/Service/06_Service_MultiClient_Death.md",
            "01-Mechanism/Framework/Service/07_Service_ANR_Landscape.md",
            "01-Mechanism/Framework/Service/08_Service_ProcessKeepAlive_TrimMemory.md",
            "01-Mechanism/Framework/Service/09_Service_BinderLimit_ServiceCap.md",
            "01-Mechanism/Framework/Service/README.md",
            "01-Mechanism/Framework/Signing/01-签名总览：背景、发展史、现状与生态.md",
            "01-Mechanism/Framework/Signing/02-APK签名方案V1V2V3V4核心机制与数据结构.md",
            "01-Mechanism/Framework/Signing/03-签名校验链路：PackageInstaller到PMS.md",
            "01-Mechanism/Framework/Signing/04-AndroidKeyStore与硬件密钥管理.md",
            "01-Mechanism/Framework/Signing/05-签名风险全景与实战案例.md",
            "01-Mechanism/Framework/Signing/README-签名系统系列.md",
            # 01-Mechanism/Kernel/Process + cgroup
            "01-Mechanism/Kernel/Process/01-进程子系统全景与边界契约.md",
            "01-Mechanism/Kernel/Process/02-task_struct全景拆解.md",
            "01-Mechanism/Kernel/Process/03-进程的诞生_fork_clone_vfork.md",
            "01-Mechanism/Kernel/Process/04-进程的执行_execve与程序加载.md",
            "01-Mechanism/Kernel/Process/05-进程的退出_do_exit与资源回收.md",
            "01-Mechanism/Kernel/Process/06-调度基础架构_调度类与上下文切换.md",
            "01-Mechanism/Kernel/Process/07-CFS调度器_vruntime与红黑树.md",
            "01-Mechanism/Kernel/Process/08-调度扩展_RT_Deadline_Idle.md",
            "01-Mechanism/Kernel/Process/09-多核调度_SMP负载均衡_EAS.md",
            "01-Mechanism/Kernel/Process/10-cgroup_v2_内核里的资源控制器.md",
            "01-Mechanism/Kernel/Process/11-信号机制_从产生到投递.md",
            "01-Mechanism/Kernel/Process/12-进程间通信_pipe_fifo_shm_futex_Binder.md",
            "01-Mechanism/Kernel/Process/13-进程调试与稳定性关联.md",
            "01-Mechanism/Kernel/Process/README.md",
            "01-Mechanism/Kernel/Process/Stability_README.md",
            "01-Mechanism/Kernel/cgroup/01-cgroup的诞生与历史演进_从2006到Android17.md",
            "01-Mechanism/Kernel/cgroup/02-cgroup核心抽象_subsys_css_cftype_cgroup_file.md",
            "01-Mechanism/Kernel/cgroup/03-cgroup三大资源维度的统一抽象_Process_Memory_IO.md",
            "01-Mechanism/Kernel/cgroup/04-Android17_cgroup树与libprocessgroup.md",
            "01-Mechanism/Kernel/cgroup/05-cgroup与稳定性的核心关系_OOM_Throttle_杀进程.md",
            "01-Mechanism/Kernel/cgroup/06-cgroup可观测性全景与风险地图_实战收口.md",
            "01-Mechanism/Kernel/cgroup/README-cgroup系列.md",
        ],
    },
    "第14章-线程与Handler": {
        "dest": f"{V3}/14-线程与 Handler 消息机制",
        "files": [
            "01-Mechanism/App/Handler-MessageQueue-Looper/Handler_MessageQueue_Looper/01-Handler消息机制总览.md",
            "01-Mechanism/App/Handler-MessageQueue-Looper/Handler_MessageQueue_Looper/02-Looper与线程模型.md",
            "01-Mechanism/App/Handler-MessageQueue-Looper/Handler_MessageQueue_Looper/03-MessageQueue与Native层.md",
            "01-Mechanism/App/Handler-MessageQueue-Looper/Handler_MessageQueue_Looper/04-Message生命周期.md",
            "01-Mechanism/App/Handler-MessageQueue-Looper/Handler_MessageQueue_Looper/05-同步屏障与异步消息.md",
            "01-Mechanism/App/Handler-MessageQueue-Looper/Handler_MessageQueue_Looper/06-Handler与ANR.md",
            "01-Mechanism/App/Handler-MessageQueue-Looper/Handler_MessageQueue_Looper/07-Handler稳定性风险全景.md",
            "01-Mechanism/App/Handler-MessageQueue-Looper/Handler_MessageQueue_Looper/08-消息机制诊断工具与监控体系.md",
            "01-Mechanism/App/Handler-MessageQueue-Looper/Handler_MessageQueue_Looper/HandlerThread泄露分析与防治.md",
            "01-Mechanism/App/Handler-MessageQueue-Looper/Handler_MessageQueue_Looper/LooperPrinter是否需要监控？.md",
            "01-Mechanism/App/Handler-MessageQueue-Looper/Handler_MessageQueue_Looper/README-Handler系列.md",
            "01-Mechanism/App/Handler-MessageQueue-Looper/Handler_MessageQueue_Looper/handler阅读笔记.md",
            "01-Mechanism/App/Hook/01-OEM-Hook全景图-本质与战场.md",
            "01-Mechanism/App/Hook/02-Kernel层Hook-Vendor_Hook与eBPF.md",
            "01-Mechanism/App/Hook/03-HAL层Hook-PowerHAL与触控优化.md",
            "01-Mechanism/App/Hook/04-Native层Hook-Bionic与Skia渲染拦截.md",
            "01-Mechanism/App/Hook/05-ART层Hook-ArtMethod替换与deopt.md",
            "01-Mechanism/App/Hook/06-Framework-Binder层Hook-ServiceManager代理与AMS_WMS_PMS插桩.md",
            "01-Mechanism/App/Hook/07-App-UI层Hook-RRO与Instrumentation替换.md",
            "01-Mechanism/App/Hook/08-场景1-隐私保护-空白通行证与假数据.md",
            "01-Mechanism/App/Hook/09-场景2-后台治理-cgroup_freezer与启动拦截.md",
            "01-Mechanism/App/Hook/10-场景3-应用双开-UserHandle多用户魔改.md",
            "01-Mechanism/App/Hook/11-场景4-游戏调度-Vendor_Hook与PowerHAL.md",
            "01-Mechanism/App/Hook/12-场景5-折叠屏适配-平行视界与TaskFragment.md",
            "01-Mechanism/App/Hook/13-五大OEM风格对比-华为小米OPPO_vivo_三星.md",
            "01-Mechanism/App/Hook/14-OEM_Hook演进-从运行时到编译期.md",
            "01-Mechanism/App/Hook/15-Bootloop与兼容性速查.md",
            "01-Mechanism/App/Hook/README-OEM_Hook系列.md",
        ],
    },
    "第15章-内存管理全链路": {
        "dest": f"{V3}/15-内存管理全链路",
        "files": [
            # 01-Mechanism/Framework/Memory_Management
            "01-Mechanism/Framework/Memory_Management/01-FWK内存管理全景：从onTrimMemory看5大机制与全栈抽象.md",
            "01-Mechanism/Framework/Memory_Management/02-ComponentCallbacks2-onTrimMemory-7等级的设计动机.md",
            "01-Mechanism/Framework/Memory_Management/03-AMS内存决策链：何时调trimMemory何时更新adj何时杀进程.md",
            "01-Mechanism/Framework/Memory_Management/04-onTrimMemory派发机制-从ProcessList到Application-Activity调用链.md",
            "01-Mechanism/Framework/Memory_Management/05-ProcessRecord内存账本深入-ART-Native拆分与跨层对账.md",
            "01-Mechanism/Framework/Memory_Management/06-dumpsys-meminfo解读-从输出反推FWK内存账本.md",
            "01-Mechanism/Framework/Memory_Management/07-内存压力检测-Kernel-PSI-memcg到AMS-App全链路.md",
            "01-Mechanism/Framework/Memory_Management/08-App侧资源释放最佳实践-Glide-OkHttp-Bitmap-Handler.md",
            "01-Mechanism/Framework/Memory_Management/09-跨层协作-一次trimMemory派发的5层剧本.md",
            "01-Mechanism/Framework/Memory_Management/10-杀进程时序-从trimMemory-80到lmkd-kill的FWK视角.md",
            "01-Mechanism/Framework/Memory_Management/11-收口+治理-FWK视角的10大内存问题与监控.md",
            # 01-Mechanism/Kernel/Memory_Management
            "01-Mechanism/Kernel/Memory_Management/01-Android内存分类学：5大管理职责与全景.md",
            "01-Mechanism/Kernel/Memory_Management/02-一个byte的双重视角：加载与运行的融会贯通.md",
            "01-Mechanism/Kernel/Memory_Management/03-ART堆与GC的设计动机：为什么这样设计.md",
            "01-Mechanism/Kernel/Memory_Management/04-Native堆与分配器的设计动机：bionic-scudo的取舍.md",
            "01-Mechanism/Kernel/Memory_Management/05-进程虚拟地址子系统：mmap-VMA-缺页的设计哲学.md",
            "01-Mechanism/Kernel/Memory_Management/06-物理内存组织与伙伴系统：Node-Zone-Page的设计.md",
            "01-Mechanism/Kernel/Memory_Management/07-内存回收子系统：LRU-MGLRU-kswapd-的演进逻辑.md",
            "01-Mechanism/Kernel/Memory_Management/09-杀进程决策子系统：LMKD-MemoryLimiter-的协同.md",
            "01-Mechanism/Kernel/Memory_Management/10-Framework层内存账本：ProcessRecord-5维14字段的设计.md",
            "01-Mechanism/Kernel/Memory_Management/11-一次page-fault的5层协作：跨层架构全景.md",
            "01-Mechanism/Kernel/Memory_Management/12-分配与回收的设计权衡：ART堆-Native堆-mmap的隔离边界.md",
            "01-Mechanism/Kernel/Memory_Management/13-保护与释放的协同：adj体系与4大释放源.md",
            "01-Mechanism/Kernel/Memory_Management/14-20年演进史：从内核LMK到MemoryLimiter的设计哲学.md",
            "01-Mechanism/Kernel/Memory_Management/15-未来方向：基于真实信息的6大演进路径.md",
            "01-Mechanism/Kernel/Memory_Management/README.md",
        ],
    },
    "第16章-IO与存储": {
        "dest": f"{V3}/16-IO 与存储",
        "files": [
            "01-Mechanism/Kernel/FileSystem/01-文件系统是什么+12 类类型.md",
            "01-Mechanism/Kernel/FileSystem/02-Android 设备分区与 FS 选型.md",
            "01-Mechanism/Kernel/FileSystem/03-Android 文件树全貌 完整挂载点表.md",
            "01-Mechanism/Kernel/FileSystem/04-5 大管理职责 × 4 层物理架构矩阵.md",
            "01-Mechanism/Kernel/FileSystem/05-一个文件的双重视角：open,read 时序走查.md",
            "01-Mechanism/Kernel/FileSystem/06-Android FS 演进史：从 ext4 到 FUSE passthrough 的 20 年设计哲学.md",
            "01-Mechanism/Kernel/FileSystem/07-VFS 核心数据结构：super_block, inode, dentry, file 的设计动机.md",
            "01-Mechanism/Kernel/FileSystem/08-file_operations 多态分发机制（不是 hook）.md",
            "01-Mechanism/Kernel/FileSystem/09-路径解析与挂载机制：path_lookup, mount namespace, overlay.md",
            "01-Mechanism/Kernel/FileSystem/10-页缓存机制：Page Cache, address_space, 脏页回写.md",
            "01-Mechanism/Kernel/FileSystem/11-内存映射文件机制：mmap, 缺页处理, Android 应用.md",
            "01-Mechanism/Kernel/FileSystem/12-ext4 文件系统架构：磁盘布局, extent, journaling.md",
            "01-Mechanism/Kernel/FileSystem/13-f2fs 文件系统特性：闪存友好, 日志结构, GC.md",
            "01-Mechanism/Kernel/FileSystem/14-erofs 与只读压缩：LZ4, LZMA, Android system 分区.md",
            "01-Mechanism/Kernel/FileSystem/15-块设备层与 FS 交互：submit_bio, IO 调度影响.md",
            "01-Mechanism/Kernel/FileSystem/16-动态分区与 APEX super 分区详解：Android 现代化分区设计.md",
            "01-Mechanism/Kernel/FileSystem/17-StorageManager + Vold 守护进程链路：从 init.rc 到 Binder 跨进程.md",
            "01-Mechanism/Kernel/FileSystem/18-Scoped Storage 与文件访问：MediaStore, SAF, DocumentsProvider.md",
            "01-Mechanism/Kernel/FileSystem/19-FUSE 在 Android 中的应用：sdcardfs 迁移到 FUSE passthrough.md",
            "01-Mechanism/Kernel/FileSystem/20-FUSE 死锁全景：4 类锁等待链与用户态 daemon 状态机.md",
            "01-Mechanism/Kernel/FileSystem/21-Vold + MountService 跨进程故障模式.md",
            "01-Mechanism/Kernel/FileSystem/22-F2FS GC 与 Checkpoint 抖动：f2fs_gc_thread 延迟源.md",
            "01-Mechanism/Kernel/FileSystem/23-ext4 journal 满与 jbd2 阻塞：transaction 等待.md",
            "01-Mechanism/Kernel/FileSystem/24-FBE 文件级加密启动慢 + 三大资源耗尽（FD,inode,配额）.md",
            "01-Mechanism/Kernel/FileSystem/25-FS 稳定性诊断工具链 + 5 件套案例库 + AOSP 18,19 路径（不臆想）.md",
            "01-Mechanism/Kernel/FileSystem/AUDIT_REPORT.md",
            "01-Mechanism/Kernel/FileSystem/README.md",
            "01-Mechanism/Kernel/IO/01-IO子系统总览：从进程read、write到磁盘的完整链路.md",
            "01-Mechanism/Kernel/IO/02-IO调度器与多队列架构.md",
            "01-Mechanism/Kernel/IO/03-Block层核心机制：bio-request-plug-merge-throttle.md",
            "01-Mechanism/Kernel/IO/04-IO优先级与cgroup-IO控制器.md",
            "01-Mechanism/Kernel/IO/05-IO与内存的深度耦合：Page-Cache脏页回写、回收路径、swap-IO.md",
            "01-Mechanism/Kernel/IO/06-IO与进程的深度耦合：D状态、iowait、IO-hang、进程阻塞.md",
            "01-Mechanism/Kernel/IO/07-程序加载与链接的IO路径：从execve到AOT文件mmap.md",
            "01-Mechanism/Kernel/IO/08-Android存储栈：从FUSE、sdcardfs、StorageManager到块设备.md",
            "01-Mechanism/Kernel/IO/09-存储设备与IO性能：UFS、eMMC、NVMe命令队列与延迟特性.md",
            "01-Mechanism/Kernel/IO/10-IO稳定性风险全景与诊断工具链.md",
            "01-Mechanism/Kernel/IO/11-eBPF在IO性能分析中的实战：从bpftrace到Android落地.md",
            "01-Mechanism/Kernel/IO/README.md",
        ],
    },
    "第17章-网络与连接": {
        "dest": f"{V3}/17-网络与连接",
        "files": [
            "01-Mechanism/Kernel/socket/01-Socket总览.md",
            "01-Mechanism/Kernel/socket/02-Socket内核API与数据结构.md",
            "01-Mechanism/Kernel/socket/03-Socket连接生命周期.md",
            "01-Mechanism/Kernel/socket/04-Socket缓冲区与数据收发.md",
            "01-Mechanism/Kernel/socket/05-listen_backlog与连接队列.md",
            "01-Mechanism/Kernel/socket/06-Unix_Domain_Socket与Android使用.md",
            "01-Mechanism/Kernel/socket/07-Socket稳定性风险全景.md",
            "01-Mechanism/Kernel/socket/08-Socket诊断工具与治理体系.md",
            "01-Mechanism/Kernel/socket/README-Socket系列.md",
            "01-Mechanism/Kernel/socket/bridge/01-socket与epoll的关系.md",
            "06-Foundation/Network/01-网络栈总览：从app-socket到网卡的全链路.md",
            "06-Foundation/Network/02-TCP-IP协议栈：SYN-ACK-FIN-RST状态机.md",
            "06-Foundation/Network/03-DNS-DHCP：从解析到连接的5秒流程.md",
            "06-Foundation/Network/04-ConnectivityService：网络选路-评分-切换.md",
            "06-Foundation/Network/05-netd-NetworkManagementService：网络策略.md",
            "06-Foundation/Network/06-WiFi协议栈：wpa-supplicant-HAL-连接.md",
            "06-Foundation/Network/07-Mobile-Data：RIL-数据业务-漫游.md",
            "06-Foundation/Network/08-网络栈诊断工具：tcpdump-ss-netstat-ping.md",
        ],
    },
    "第18章-显示与渲染": {
        "dest": f"{V3}/18-显示与渲染",
        "files": [
            "01-Mechanism/Framework/Window/01-Window系统总览.md",
            "01-Mechanism/Framework/Window/02-Window的创建与添加.md",
            "01-Mechanism/Framework/Window/03-WindowContainer层级体系与窗口组织.md",
            "01-Mechanism/Framework/Window/04-窗口布局与Insets计算.md",
            "01-Mechanism/Framework/Window/05-Surface管理与SurfaceFlinger交互.md",
            "01-Mechanism/Framework/Window/06-窗口动画与转场.md",
            "01-Mechanism/Framework/Window/07-WMS与Input焦点管理.md",
            "01-Mechanism/Framework/Window/08-窗口显示性能：TTID、TTFD与启动优化.md",
            "01-Mechanism/Framework/Window/09-Window稳定性风险全景.md",
            "01-Mechanism/Framework/Window/10-WMS锁竞争与Watchdog.md",
            "01-Mechanism/Framework/Window/11-Window诊断工具与治理体系.md",
            "01-Mechanism/Framework/Window/README-Window系列.md",
            "06-Foundation/Graphics/01-图形栈总览：app-WindowManager-SurfaceFlinger-HWC-Display.md",
            "06-Foundation/Graphics/02-SurfaceFlinger内部：合成-VSync-Layer树.md",
            "06-Foundation/Graphics/03-BufferQueue：跨进程图形缓冲机制.md",
            "06-Foundation/Graphics/04-HWUI-RenderThread：硬件加速渲染.md",
            "06-Foundation/Graphics/05-Choreographer-VSync：UI节奏协调.md",
            "06-Foundation/Graphics/06-HWC（Hardware-Composer）：display-HAL抽象.md",
            "06-Foundation/Graphics/07-卡顿-jank实战：trace+logcat5分钟定位.md",
        ],
    },
    "第19章-电源与续航": {
        "dest": f"{V3}/19-电源与续航",
        "files": [
            "01-Mechanism/Kernel/Interrupt/IO劣化检测设计SOP.md",
            "01-Mechanism/Kernel/Interrupt/Linux 内核中断机制深度剖析：从上下文借用到 DoS 防御.md",
            "01-Mechanism/Kernel/Interrupt/readme.md",
            "01-Mechanism/Kernel/Interrupt/traceflag.md",
            "01-Mechanism/Kernel/Interrupt/《整机 IO 性能劣化分析标准作业程序 (SOP)》.md",
            "01-Mechanism/Kernel/Interrupt/中断理解1.md",
            "01-Mechanism/Kernel/Interrupt/深度解密：中断的“上半部”与“下半部” (Hard IRQ vs SoftIRQ).md",
            "06-Foundation/Power/01-PowerManager概览：Doze-Standby-唤醒机制全景.md",
            "06-Foundation/Power/02-唤醒锁WakeLock：类型-获取-释放-实战.md",
            "06-Foundation/Power/03-Doze-App-Standby：后台冻结机制.md",
            "06-Foundation/Power/04-耗电-wakeup风暴实战：trace+logcat5分钟定位.md",
        ],
    },
    "第20章-ART运行时": {
        "dest": f"{V3}/20-ART 运行时",
        "files": [
            "01-Mechanism/Runtime/ART/00-总览/01-ART总览：稳定性架构师的全局视角.md",
            "01-Mechanism/Runtime/ART/00-总览/README.md",
            "01-Mechanism/Runtime/ART/01-字节码与指令集/01-Dex文件与Dalvik指令集.md",
            "01-Mechanism/Runtime/ART/01-字节码与指令集/README.md",
            "01-Mechanism/Runtime/ART/02-编译与执行/01-编译路径全景.md",
            "01-Mechanism/Runtime/ART/02-编译与执行/README.md",
            "01-Mechanism/Runtime/ART/03-GC系统/01-基础理论专题.md",
            "01-Mechanism/Runtime/ART/03-GC系统/02-Heap与分配器专题.md",
            "01-Mechanism/Runtime/ART/03-GC系统/03-CMS-GC专题.md",
            "01-Mechanism/Runtime/ART/03-GC系统/04-CC-GC专题.md",
            "01-Mechanism/Runtime/ART/03-GC系统/05-Generational-CC专题.md",
            "01-Mechanism/Runtime/ART/03-GC系统/06-Reference与Finalizer专题.md",
            "01-Mechanism/Runtime/ART/03-GC系统/07-GC调度与触发专题.md",
            "01-Mechanism/Runtime/ART/03-GC系统/08-GC与其他子系统专题.md",
            "01-Mechanism/Runtime/ART/03-GC系统/09-GC诊断与治理专题.md",
            "01-Mechanism/Runtime/ART/03-GC系统/10-ART17分代GC强化专章.md",
            "01-Mechanism/Runtime/ART/03-GC系统/11-实战案例合辑.md",
            "01-Mechanism/Runtime/ART/03-GC系统/README.md",
            "01-Mechanism/Runtime/ART/03-类加载与链接/01-类加载完整流程.md",
            "01-Mechanism/Runtime/ART/03-类加载与链接/README.md",
            "01-Mechanism/Runtime/ART/05-JNI/01-JNI完整解析.md",
            "01-Mechanism/Runtime/ART/05-JNI/README.md",
            "01-Mechanism/Runtime/ART/06-信号与ANR-Trace/01-SignalCatcher与信号机制.md",
            "01-Mechanism/Runtime/ART/06-信号与ANR-Trace/02-ANR_Trace完整链路.md",
            "01-Mechanism/Runtime/ART/06-信号与ANR-Trace/README.md",
            "01-Mechanism/Runtime/ART/07-启动流程/01-从app_process到第一行Java代码.md",
            "01-Mechanism/Runtime/ART/07-启动流程/README.md",
            "01-Mechanism/Runtime/ART/08-对比与演进/01-ART_vs_JVM设计哲学.md",
            "01-Mechanism/Runtime/ART/08-对比与演进/02-Mainline与APEX.md",
            "01-Mechanism/Runtime/ART/08-对比与演进/03-Hook框架与ART.md",
        ],
    },
}


def main():
    # 1. 校验源文件都存在
    missing = []
    for chapter, info in MIGRATIONS.items():
        for f in info["files"]:
            p = REPO / f
            if not p.exists():
                missing.append(f)
    if missing:
        print(f"[FAIL] {len(missing)} source files missing:")
        for f in missing[:20]:
            print(f"  {f}")
        if len(missing) > 20:
            print(f"  ... +{len(missing)-20} more")
        return

    print(f"[OK] All {sum(len(info['files']) for info in MIGRATIONS.values())} source files exist")

    # 2. 创建目标目录
    for chapter, info in MIGRATIONS.items():
        d = REPO / info["dest"]
        d.mkdir(parents=True, exist_ok=True)
        print(f"  [DIR] {info['dest']}")

    # 3. git mv
    total_mv = 0
    for chapter, info in MIGRATIONS.items():
        for f in info["files"]:
            src = REPO / f
            dst = REPO / info["dest"] / Path(f).name
            if dst.exists():
                print(f"  [SKIP] {f} (target exists)")
                continue
            rel_src = f.replace("/", os.sep)
            rel_dst = (info["dest"] + "/" + Path(f).name).replace("/", os.sep)
            result = subprocess.run(
                ["git", "mv", rel_src, rel_dst],
                cwd=str(REPO),
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if result.returncode == 0:
                total_mv += 1
            else:
                print(f"  [ERR] {f} -> {info['dest']}/{Path(f).name}: {result.stderr.strip()}")

    print(f"\n[OK] git mv {total_mv} files")

    # 4. 报告
    print("\n[SUMMARY]")
    for chapter, info in MIGRATIONS.items():
        print(f"  {chapter}: {len(info['files'])} files -> {info['dest']}")


if __name__ == "__main__":
    main()
