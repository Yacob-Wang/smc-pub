"""为拆分的子章写 index.md + 更新父章 index.md"""
from pathlib import Path
import re

REPO = Path(r'C:\Users\deepLife\Documents\GitHub\smc-pub')

# 13 章子章 index
CH13_INDEX = {
    '13.A-Android四大组件': {
        'title': '13.A Android 四大组件',
        'subdir_rel': '13.A-Android四大组件',
        'subtitle': 'Activity / Broadcast / ContentProvider / Service — 4 大组件的全栈机制',
        'count': 36,
        'sections': [
            ('13.A.1 Activity', '10 篇', 'Activity 启动 / 生命周期 / 启动模式 / 跳转延迟 / 内存管理'),
            ('13.A.2 Broadcast', '9 篇', '注册 / 发送 / 有序广播 / 粘性广播 / 后台限制'),
            ('13.A.3 ContentProvider', '9 篇', '初始化 / CRUD / 跨进程 / Observer / Scoped Storage'),
            ('13.A.4 Service', '9 篇', 'StartService / BindService / 前台服务 / WorkManager / 多客户端'),
        ],
    },
    '13.B-进程生命周期': {
        'title': '13.B 进程生命周期',
        'subdir_rel': '13.B-进程生命周期',
        'subtitle': '从 fork 到死：进程诞生、调度、退出全链路',
        'count': 32,
        'sections': [
            ('13.B.1 Framework 进程管理', '9 篇', 'AMS 冷启动 / Zygote fork / ART 内世界 / Kernel 接口 / CFS 调度'),
            ('13.B.2 杀进程专题', '4 篇', 'AMS 触发到进程退出的全链路 + do_exit 9 步'),
            ('13.B.3 Kernel 进程子系统', '13 篇', 'task_struct / fork / execve / CFS / 多核调度 / cgroup_v2'),
            ('13.B.4 cgroup 资源管理', '6 篇', 'cgroup 演进 / 抽象 / 资源维度 / Android 17 树 / OOM 与杀进程'),
        ],
    },
    '13.C-签名与Keystore': {
        'title': '13.C 签名与 Keystore',
        'subdir_rel': '13.C-签名与Keystore',
        'subtitle': 'APK 签名 + AndroidKeyStore 硬件密钥 — 安全与稳定性的边界',
        'count': 5,
        'sections': [
            ('13.C.1 签名体系', '3 篇', '签名方案 V1/V2/V3/V4 + 校验链路 + Keystore'),
            ('13.C.2 实战案例', '2 篇', '签名风险全景 + 实战案例'),
        ],
    },
}

CH20_INDEX = {
    '20.A-ART基础': {
        'title': '20.A ART 基础',
        'subdir_rel': '20.A-ART基础',
        'count': 4,
        'sections': [
            ('20.A.1 ART 总览与设计哲学', '2 篇', 'ART 全局视角 + ART vs JVM 设计哲学'),
            ('20.A.2 字节码与类加载', '2 篇', 'Dex/Dalvik 指令集 + 类加载完整流程'),
        ],
    },
    '20.B-编译与执行': {
        'title': '20.B 编译与执行',
        'subdir_rel': '20.B-编译与执行',
        'count': 3,
        'sections': [
            ('20.B.1 编译路径全景', '1 篇', 'AOT/JIT/dex2oat 全景'),
            ('20.B.2 JNI 完整解析', '1 篇', 'Java ↔ Native 桥接'),
            ('20.B.3 Mainline 与 APEX', '1 篇', 'ART 模块化演进'),
        ],
    },
    '20.C-GC系统': {
        'title': '20.C GC 系统',
        'subdir_rel': '20.C-GC系统',
        'count': 11,
        'sections': [
            ('20.C.1 GC 基础理论', '2 篇', '基础理论 + Heap 与分配器'),
            ('20.C.2 GC 算法专题', '4 篇', 'CMS / CC / Generational CC / Reference 与 Finalizer'),
            ('20.C.3 GC 调度与诊断', '4 篇', 'GC 调度 / GC 与其他子系统 / GC 诊断 / ART17 分代强化'),
            ('20.C.4 实战案例', '1 篇', 'GC 实战案例合辑'),
        ],
    },
    '20.D-信号与Hook': {
        'title': '20.D 信号 / ANR / Hook',
        'subdir_rel': '20.D-信号与Hook',
        'count': 3,
        'sections': [
            ('20.D.1 信号机制', '1 篇', 'SignalCatcher 与 ART 信号处理'),
            ('20.D.2 ANR Trace 链路', '1 篇', 'ANR 完整 trace 抓取链路'),
            ('20.D.3 Hook 框架与 ART', '1 篇', 'ART 层的 Hook 实现'),
        ],
    },
    '20.E-启动': {
        'title': '20.E 启动',
        'subdir_rel': '20.E-启动',
        'count': 1,
        'sections': [
            ('20.E.1 启动链路', '1 篇', '从 app_process 到第一行 Java 代码'),
        ],
    },
}


def write_sub_index(ch_dir: Path, info: dict):
    """写子章 index.md"""
    sub = info['subdir_rel']
    title = info['title']
    count = info.get('count', 0)
    sections = info.get('sections', [])

    # 找子章文件列表
    sub_path = ch_dir / sub
    files = sorted([f.name for f in sub_path.iterdir() if f.is_file() and f.name != 'index.md'])
    file_count = len(files)

    md_lines = [
        f'# {title}',
        '',
    ]
    if 'subtitle' in info:
        md_lines.append(f'> **{info["subtitle"]}**')
        md_lines.append(f'>')
        md_lines.append(f'> 共 {file_count} 篇 · P0 第 13 章拆分子章')
    else:
        md_lines.append(f'> 共 {file_count} 篇 · P0 第 20 章拆分子章')
    md_lines.append('')
    md_lines.append('## 子节导航')
    md_lines.append('')
    for sec_name, sec_count, sec_desc in sections:
        md_lines.append(f'### {sec_name}（{sec_count}）')
        md_lines.append(f'> {sec_desc}')
        md_lines.append('')

    md_lines.append('## 文件清单')
    md_lines.append('')
    for f in files:
        md_lines.append(f'- [{f[:-3]}]({f})')
    md_lines.append('')
    md_lines.append('---')
    md_lines.append('')
    md_lines.append(f'**返回**：[第 13 章 进程与生命周期](../index.md)')
    md_lines.append('')

    out = sub_path / 'index.md'
    out.write_text('\n'.join(md_lines), encoding='utf-8')
    print(f'  [WROTE] {out.relative_to(REPO)} ({file_count} files listed)')


def update_ch_index(ch_dir: Path, ch_title: str, subdirs: list, description: str):
    """更新父章 index.md（链接到子章）"""
    md_lines = [
        f'# {ch_title}',
        '',
        f'> **{description}**',
        '',
        f'> 本章已拆分为 {len(subdirs)} 个子章，原文件已迁移。',
        '',
        '## 子章导航',
        '',
    ]
    for sub in subdirs:
        info_path = ch_dir / sub / 'index.md'
        if not info_path.exists():
            md_lines.append(f'### {sub}')
            md_lines.append(f'(待生成 index.md)')
            md_lines.append('')
            continue
        # 读子章 index.md 拿标题 + count
        content = info_path.read_text(encoding='utf-8')
        # 提取 # 标题
        m = re.search(r'^# (.+)$', content, re.MULTILINE)
        title = m.group(1) if m else sub
        # 提取文件数（从 "共 X 篇"）
        m2 = re.search(r'共 (\d+) 篇', content)
        count = m2.group(1) if m2 else '?'
        # 提取 subtitle
        m3 = re.search(r'> \*\*(.+?)\*\*', content)
        subtitle = m3.group(1) if m3 else ''
        md_lines.append(f'### [{title}]({sub}/)')
        md_lines.append(f'> {count} 篇 · {subtitle}')
        md_lines.append('')

    md_lines.append('## 父章保留文件')
    md_lines.append('')
    parent_files = sorted([f.name for f in ch_dir.iterdir() if f.is_file() and f.name != 'index.md'])
    for f in parent_files:
        md_lines.append(f'- [{f[:-3]}]({f})')
    md_lines.append('')
    md_lines.append('---')
    md_lines.append('')
    md_lines.append('**返回**：[卷 3 核心机制](../../index.md)')

    out = ch_dir / 'index.md'
    out.write_text('\n'.join(md_lines), encoding='utf-8')
    print(f'  [WROTE] {out.relative_to(REPO)}')


def main():
    # 13 章
    print('========== 第 13 章子章 index.md ==========')
    ch13 = REPO / '03-卷3-核心机制' / '13-进程与生命周期'
    for sub, info in CH13_INDEX.items():
        write_sub_index(ch13, info)
    update_ch_index(
        ch13,
        '第 13 章 进程与生命周期',
        list(CH13_INDEX.keys()),
        '从 fork 到死：进程诞生、调度、退出、组件全栈机制'
    )

    # 20 章
    print('\n========== 第 20 章子章 index.md ==========')
    ch20 = REPO / '03-卷3-核心机制' / '20-ART 运行时'
    for sub, info in CH20_INDEX.items():
        write_sub_index(ch20, info)
    update_ch_index(
        ch20,
        '第 20 章 ART 运行时',
        list(CH20_INDEX.keys()),
        'Android Runtime 全栈：基础、编译、GC、信号、启动'
    )

    print('\n[OK] 全部子章 + 父章 index.md 写完')


if __name__ == '__main__':
    main()
