"""过载章拆分脚本：
- 13 章 70 篇 → 13.A Android 四大组件 (36) + 13.B 进程生命周期 (32) + 13.C 签名 (5) + 父章保留 README (7)
- 20 章 24 篇 → 20.A ART 基础 (4) + 20.B 编译执行 (3) + 20.C GC (11) + 20.D 信号/Hook (3) + 20.E 启动 (1) + 父章保留 (2)
"""
import subprocess
from pathlib import Path

REPO = Path(r'C:\Users\deepLife\Documents\GitHub\smc-pub')

# 第 13 章拆分映射：filename prefix → sub-dir
CH13_MAP = {
    '13.A-Android四大组件': [
        '01_Activity_Overview.md', '02_Activity_Start_SourceCode.md', '03_Activity_Lifecycle.md',
        '04_Activity_LaunchMode_Task.md', '05_Activity_Intent_Resolve.md', '06_Activity_ConfigChange.md',
        '07_Activity_Launch_ANR.md', '08_Activity_Jump_Latency.md', '09_Activity_Memory_Governance.md',
        'B01_Broadcast_Overview.md', 'B02_Broadcast_Register.md', 'B03_Broadcast_Send.md',
        'B04_Broadcast_Ordered.md', 'B05_Broadcast_Sticky_Evolution.md', 'B06_Broadcast_LocalBroadcast_Alternative.md',
        'B07_Broadcast_BackgroundRestriction.md', 'B08_Broadcast_ANR_Landscape.md', 'B09_Broadcast_SystemBoot.md',
        'C01_ContentProvider_Overview.md', 'C02_ContentProvider_Init.md', 'C03_ContentProvider_CRUD.md',
        'C04_ContentProvider_CrossProcess.md', 'C05_ContentProvider_Observer.md', 'C06_ContentProvider_PackageVisibility.md',
        'C07_ContentProvider_Binder_ANR.md', 'C08_ContentProvider_Cases.md', 'C09_ContentProvider_Optimize_Monitor.md',
        '01_Service_Overview.md', '02_Service_StartService_Path.md', '03_Service_BindService_Path.md',
        '04_Service_FGS_TypeRestricted.md', '05_Service_WorkManager_Evolution.md', '06_Service_MultiClient_Death.md',
        '07_Service_ANR_Landscape.md', '08_Service_ProcessKeepAlive_TrimMemory.md', '09_Service_BinderLimit_ServiceCap.md',
    ],
    '13.B-进程生命周期': [
        '01-进程总览：从点图标看app进程的诞生消亡与全栈抽象.md', '02-AMS-冷启动判定与进程启动链路.md',
        '03-Zygote-Android进程工厂.md', '04-应用进程首生-fork到ActivityThread.md',
        '05-ART进程内世界：JIT-AOT与GC.md', '06-Framework视角的Kernel进程接口_procfs_cgroup_pidfd.md',
        '07-调度与资源：CFS与进程生死.md', '08-进程稳定性风险全景与跨层治理.md',
        '09-杀进程慢的根因定位实战.md',
        '01-杀进程全链路：从AMS触发到进程完全退出.md', '02-do_exit内部9个sub-step深潜.md',
        '03-杀进程慢的真正根因：诱因-根因-证伪.md', '04-杀进程监控与治理：ftrace-perfetto-告警-治理.md',
        '01-进程子系统全景与边界契约.md', '02-task_struct全景拆解.md', '03-进程的诞生_fork_clone_vfork.md',
        '04-进程的执行_execve与程序加载.md', '05-进程的退出_do_exit与资源回收.md', '06-调度基础架构_调度类与上下文切换.md',
        '07-CFS调度器_vruntime与红黑树.md', '08-调度扩展_RT_Deadline_Idle.md', '09-多核调度_SMP负载均衡_EAS.md',
        '10-cgroup_v2_内核里的资源控制器.md', '11-信号机制_从产生到投递.md', '12-进程间通信_pipe_fifo_shm_futex_Binder.md',
        '13-进程调试与稳定性关联.md',
        '01-cgroup的诞生与历史演进_从2006到Android17.md', '02-cgroup核心抽象_subsys_css_cftype_cgroup_file.md',
        '03-cgroup三大资源维度的统一抽象_Process_Memory_IO.md', '04-Android17_cgroup树与libprocessgroup.md',
        '05-cgroup与稳定性的核心关系_OOM_Throttle_杀进程.md', '06-cgroup可观测性全景与风险地图_实战收口.md',
    ],
    '13.C-签名与Keystore': [
        '01-签名总览：背景、发展史、现状与生态.md', '02-APK签名方案V1V2V3V4核心机制与数据结构.md',
        '03-签名校验链路：PackageInstaller到PMS.md', '04-AndroidKeyStore与硬件密钥管理.md',
        '05-签名风险全景与实战案例.md',
    ],
}

# 第 20 章拆分映射
CH20_MAP = {
    '20.A-ART基础': [
        '01-ART总览：稳定性架构师的全局视角.md', '01-Dex文件与Dalvik指令集.md',
        '01-类加载完整流程.md', '01-ART_vs_JVM设计哲学.md',
    ],
    '20.B-编译与执行': [
        '01-编译路径全景.md', '01-JNI完整解析.md', '02-Mainline与APEX.md',
    ],
    '20.C-GC系统': [
        '01-基础理论专题.md', '02-Heap与分配器专题.md', '03-CMS-GC专题.md',
        '04-CC-GC专题.md', '05-Generational-CC专题.md', '06-Reference与Finalizer专题.md',
        '07-GC调度与触发专题.md', '08-GC与其他子系统专题.md', '09-GC诊断与治理专题.md',
        '10-ART17分代GC强化专章.md', '11-实战案例合辑.md',
    ],
    '20.D-信号与Hook': [
        '01-SignalCatcher与信号机制.md', '02-ANR_Trace完整链路.md', '03-Hook框架与ART.md',
    ],
    '20.E-启动': [
        '01-从app_process到第一行Java代码.md',
    ],
}


def split_chapter(ch_name, subdirs_map):
    """ch_name = '13-进程与生命周期' or '20-ART 运行时'"""
    ch_dir = REPO / '03-卷3-核心机制' / ch_name

    # 1. 创建子目录
    for sub in subdirs_map:
        (ch_dir / sub).mkdir(parents=True, exist_ok=True)

    # 2. git mv
    moved = 0
    for sub, files in subdirs_map.items():
        for f in files:
            src = ch_dir / f
            dst = ch_dir / sub / f
            if not src.exists():
                print(f'  [SKIP-NOEXIST] {f}')
                continue
            if dst.exists():
                print(f'  [SKIP-EXISTS] {sub}/{f}')
                continue
            r = subprocess.run(
                ['git', 'mv', str(src.relative_to(REPO)), str(dst.relative_to(REPO))],
                cwd=str(REPO),
                capture_output=True,
                text=True,
                encoding='utf-8',
            )
            if r.returncode == 0:
                moved += 1
            else:
                print(f'  [ERR] {f}: {r.stderr.strip()}')

    return moved


def main():
    print('========== 第 13 章拆分 ==========')
    n13 = split_chapter('13-进程与生命周期', CH13_MAP)
    print(f'[13 章] git mv {n13} files')

    print('\n========== 第 20 章拆分 ==========')
    n20 = split_chapter('20-ART 运行时', CH20_MAP)
    print(f'[20 章] git mv {n20} files')

    # 报告 remaining in parent
    print('\n========== 父章剩余 ==========')
    for ch in ['13-进程与生命周期', '20-ART 运行时']:
        ch_dir = REPO / '03-卷3-核心机制' / ch
        files = sorted([f.name for f in ch_dir.iterdir() if f.is_file()])
        subdirs = sorted([d.name for d in ch_dir.iterdir() if d.is_dir()])
        print(f'\n[{ch}]')
        print(f'  父章文件 ({len(files)}): {files}')
        print(f'  子章目录 ({len(subdirs)}): {subdirs}')


if __name__ == '__main__':
    main()
